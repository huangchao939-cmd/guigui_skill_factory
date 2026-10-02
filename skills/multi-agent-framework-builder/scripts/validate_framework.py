"""Check saved framework contract, dependencies and current review evidence."""
import argparse
import json
from pathlib import Path

STATUSES = {"pending", "ready", "running", "reviewing", "passed", "changes_requested",
            "failed", "blocked", "paused", "cancelled"}


def validate(root):
    root = Path(root).resolve()
    errors = []

    def load(path):
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def local(value):
        if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
            raise ValueError("must be a relative nonempty path")
        result = (root / value).resolve()
        if not result.is_relative_to(root):
            raise ValueError("path escapes framework root")
        return result

    try:
        data = load(root / "framework.json")
        if not isinstance(data, dict):
            raise ValueError("framework.json must be an object")
    except (OSError, ValueError) as exc:
        return [str(exc)]
    policy = data.get("policy", {})
    if not isinstance(policy, dict):
        return ["policy must be an object"]
    for key in ("max_parallel_workers", "max_attempts_per_task"):
        if type(policy.get(key)) is not int or policy[key] < 1:
            errors.append(f"Invalid policy: {key}")
    roles = {}
    raw_roles = data.get("roles", [])
    if not isinstance(raw_roles, list):
        return errors + ["roles must be a list"]
    for role in raw_roles:
        if not isinstance(role, dict) or not isinstance(role.get("id"), str) or not role["id"]:
            errors.append("Invalid role")
            continue
        rid = role["id"]
        if rid in roles:
            errors.append(f"Duplicate role: {rid}")
        roles[rid] = role
        try:
            if not local(role.get("prompt")).is_file():
                raise ValueError("prompt file missing")
        except ValueError as exc:
            errors.append(f"Role {rid}: {exc}")
    if policy.get("state_owner") not in roles:
        errors.append("Unknown state_owner")
    raw_tasks = data.get("tasks", [])
    if not isinstance(raw_tasks, list):
        return errors + ["tasks must be a list"]
    tasks = {}
    for task in raw_tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task["id"]:
            errors.append("Invalid task")
            continue
        tid = task["id"]
        if tid in tasks:
            errors.append(f"Duplicate task: {tid}")
        tasks[tid] = task
        if task.get("status") not in STATUSES:
            errors.append(f"{tid}: unknown status")
        if task.get("owner") not in roles or task.get("reviewer") not in roles:
            errors.append(f"{tid}: unknown owner/reviewer")
        if type(task.get("attempt")) is not int or task["attempt"] < 0:
            errors.append(f"{tid}: invalid attempt")
        for key in ("depends_on", "write_scope", "acceptance"):
            if not isinstance(task.get(key), list) or not all(isinstance(v, str) and v for v in task[key]):
                errors.append(f"{tid}: invalid {key}")
                task = dict(task, **{key: []})
                tasks[tid] = task
        if not task.get("acceptance"):
            errors.append(f"{tid}: acceptance is empty")
        for scope in task.get("write_scope", []):
            if Path(scope).is_absolute() or ".." in Path(scope).parts or any(c in scope for c in "*?["):
                errors.append(f"{tid}: invalid write scope")
    active = [task for task in tasks.values() if task.get("status") == "running"]
    limit = policy.get("max_parallel_workers")
    if type(limit) is int and len(active) > limit:
        errors.append("Active tasks exceed max_parallel_workers")
    for i, left in enumerate(active):
        for right in active[i + 1:]:
            for a in left.get("write_scope", []):
                for b in right.get("write_scope", []):
                    if a == b or (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b)):
                        errors.append(f"Concurrent write conflict: {left['id']} / {right['id']}")
    visiting, done = set(), set()

    def visit(tid):
        if tid in visiting:
            errors.append(f"Dependency cycle: {tid}")
            return
        if tid in done:
            return
        visiting.add(tid)
        for dep in tasks[tid].get("depends_on", []):
            if dep not in tasks:
                errors.append(f"{tid}: unknown dependency {dep}")
                continue
            visit(dep)
            if tasks[tid].get("status") in {"ready", "running", "reviewing", "passed"} and tasks[dep].get("status") != "passed":
                errors.append(f"{tid}: dependency not passed: {dep}")
        visiting.remove(tid)
        done.add(tid)

    for tid in tasks:
        visit(tid)
    for tid, task in tasks.items():
        if task.get("status") != "passed":
            continue
        if not task.get("artifact_revision") or not task.get("attempt"):
            errors.append(f"{tid}: passed without artifact revision/attempt")
        for field in ("report", "review"):
            try:
                report = load(local(task.get(field)))
                if not isinstance(report, dict):
                    raise ValueError("report must be an object")
                for key, expected in (("task_id", tid), ("attempt", task.get("attempt")),
                                      ("artifact_revision", task.get("artifact_revision"))):
                    if report.get(key) != expected:
                        raise ValueError(f"stale or mismatched {key}")
                if field == "review":
                    if report.get("decision") != "PASS":
                        raise ValueError("review decision is not PASS")
                    checks = report.get("checks", [])
                    if not isinstance(checks, list):
                        raise ValueError("checks must be a list")
                    for criterion in task.get("acceptance", []):
                        matching = [c for c in checks if isinstance(c, dict) and c.get("criterion") == criterion and c.get("status") == "passed"]
                        if not matching:
                            raise ValueError(f"missing passed criterion: {criterion}")
                        evidence = matching[0].get("evidence")
                        if not isinstance(evidence, list) or not evidence:
                            raise ValueError("evidence list missing")
                        for ref in evidence:
                            if not local(ref).is_file():
                                raise ValueError("evidence file missing")
            except (OSError, ValueError) as exc:
                errors.append(f"{tid}/{field}: {exc}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    errors = validate(args.root)
    for error in errors:
        print(f"ERROR: {error}")
    print("CONTRACT FAILED" if errors else "CONTRACT PASSED")
    print("Saved-state checks do not prove business correctness, runtime isolation or real agent execution.")
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
