"""Single-writer protocol helpers, not an agent runtime or security sandbox."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import uuid


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def safe_path(value):
    require(isinstance(value, str) and bool(value), "empty path")
    require("\\" not in value and "//" not in value and not re.search(r"[:*?\[\]\x00-\x1f]", value), "invalid path")
    parts = PurePosixPath(value).parts
    segments = value.rstrip("/").split("/")
    require(not value.startswith("/") and bool(parts) and not any(p in {"..", ".", ""} for p in segments), "unsafe path")
    return value.casefold()


def local_file(root, value):
    safe_path(value)
    root = Path(root).resolve()
    path = (root / value).resolve()
    require(path.is_relative_to(root) and path.is_file(), "missing or escaping file: " + value)
    return path


def scopes_overlap(left, right):
    for a in left:
        a = safe_path(a)
        for b in right:
            b = safe_path(b)
            if a.rstrip("/") == b.rstrip("/") or (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b)):
                return True
    return False


def validate_definition(workflow, root=None):
    require(isinstance(workflow, dict) and workflow.get("schema_version") == 2, "expected schema_version 2")
    require(workflow.get("coordination") == "orchestration", "expected orchestration")
    require(workflow.get("mode") == "development_harness", "helpers support development_harness only")
    require(isinstance(workflow.get("workflow_revision"), str) and re.fullmatch(r"[A-Za-z0-9._-]+", workflow["workflow_revision"]), "invalid workflow_revision")
    policy = workflow.get("policy")
    require(isinstance(policy, dict), "missing policy")
    for key in ("max_parallel_workers", "max_dispatches_per_task", "max_execution_retries", "max_quality_repairs"):
        minimum = 1 if key in {"max_parallel_workers", "max_dispatches_per_task"} else 0
        require(type(policy.get(key)) is int and policy[key] >= minimum, "invalid policy: " + key)
    budget = policy.get("budget")
    require(isinstance(budget, dict) and budget.get("status") in {"unset", "configured"}, "invalid budget")
    for key in ("wall_time_seconds", "cost_limit"):
        value = budget.get(key)
        require(value is None or (type(value) in {int, float} and math.isfinite(value) and value > 0), "invalid budget limit")
    if budget["status"] == "configured":
        require(any(budget.get(k) is not None for k in ("wall_time_seconds", "cost_limit")), "configured budget has no limits")
    roles = {}
    require(isinstance(workflow.get("roles"), list), "roles must be list")
    for role in workflow["roles"]:
        require(isinstance(role, dict), "invalid role")
        rid = role.get("id")
        require(isinstance(rid, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", rid) and rid not in roles, "invalid/duplicate role")
        require(role.get("kind") in {"orchestrator", "worker", "reviewer", "integrator"}, "invalid role kind")
        safe_path(role.get("prompt"))
        if root is not None:
            local_file(root, role["prompt"])
        roles[rid] = role
    require(policy.get("state_owner") in roles and roles[policy["state_owner"]]["kind"] == "orchestrator", "invalid state owner")
    require(sum(r["kind"] == "orchestrator" for r in roles.values()) == 1, "one orchestrator required")
    require(isinstance(workflow.get("tasks"), list) and workflow["tasks"], "tasks must be nonempty list")
    tasks = {}
    for task in workflow["tasks"]:
        require(isinstance(task, dict), "invalid task")
        tid = task.get("id")
        require(isinstance(tid, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", tid) and tid not in tasks, "invalid/duplicate task ID")
        require(isinstance(task.get("title"), str) and task["title"], "missing task title")
        require(task.get("owner") in roles and roles[task["owner"]]["kind"] in {"worker", "integrator"}, "invalid owner")
        require(task.get("reviewer") in roles and roles[task["reviewer"]]["kind"] == "reviewer", "invalid reviewer")
        require(task.get("join") == "all_required", "unsupported join")
        for key in ("depends_on", "write_scope", "acceptance"):
            require(isinstance(task.get(key), list) and all(isinstance(v, str) and v for v in task[key]), "invalid task list: " + key)
            require(len(task[key]) == len(set(task[key])), "duplicate task values: " + key)
        require(bool(task["acceptance"]), "empty acceptance")
        for scope in task["write_scope"]:
            safe_path(scope)
        refs = task.get("input_refs")
        require(isinstance(refs, dict) and all(isinstance(v, str) and v for v in refs.values()), "invalid input refs")
        for ref in refs:
            safe_path(ref)
        require(type(task.get("requires_approval")) is bool, "invalid approval flag")
        require(task.get("side_effect") in {"local", "external"}, "invalid side effect")
        require(task["side_effect"] != "external" or task["requires_approval"], "external task needs approval")
        tasks[tid] = task
    visiting, visited = set(), set()

    def visit(tid):
        require(tid not in visiting, "dependency cycle")
        if tid in visited:
            return
        visiting.add(tid)
        for dep in tasks[tid]["depends_on"]:
            require(dep in tasks, "unknown dependency: " + dep)
            visit(dep)
        visiting.remove(tid)
        visited.add(tid)

    for tid in tasks:
        visit(tid)
    return tasks


def new_run(workflow, run_id):
    tasks = validate_definition(workflow)
    require(isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", run_id), "invalid run_id")
    return {"schema_version": 2, "run_id": run_id, "workflow_revision": workflow["workflow_revision"], "definition_digest": digest(workflow),
            "revision": 0, "status": "running", "usage": {"elapsed_seconds": 0, "cost": 0},
            "tasks": {tid: {"status": "pending", "attempt": 0, "dispatch_id": None,
                            "runtime_handle": None, "input_versions": {}, "artifact_revision": None,
                            "result_digest": None, "review_digest": None, "report": None, "review": None, "reserved": False,
                            "retry_count": 0, "repair_count": 0, "recovery_count": 0,
                            "approval": None, "reason": None, "inputs_invalidated": False}
                      for tid in tasks}}


def inputs_for(task, run):
    return {"refs": task["input_refs"], "dependencies": {dep: run["tasks"][dep]["artifact_revision"] for dep in task["depends_on"]}}


def envelope(run, tid):
    item = run["tasks"][tid]
    return {"run_id": run["run_id"], "task_id": tid, "dispatch_id": item["dispatch_id"],
            "attempt": item["attempt"], "input_versions": copy.deepcopy(item["input_versions"]),
            "artifact_revision": item["artifact_revision"]}


def validate_envelope(run, tid, payload, inputs):
    expected = envelope(run, tid)
    for key in ("run_id", "task_id", "dispatch_id", "attempt", "input_versions"):
        require(payload.get(key) == expected[key], "stale/mismatched " + key)
    require(payload["input_versions"] == inputs, "input versions invalidated")
    require(isinstance(payload.get("artifact_revision"), str) and payload["artifact_revision"], "missing artifact revision")


def transition(workflow, run, action, tid=None, **payload):
    """Pure validated transition. Caller persists before doing platform side effects."""
    definitions = validate_definition(workflow)
    require(run.get("workflow_revision") == workflow["workflow_revision"], "workflow revision mismatch")
    require(run.get("definition_digest") == digest(workflow), "definition changed without explicit new run/migration")
    require(set(run["tasks"]) == set(definitions), "run task mismatch")
    result = copy.deepcopy(run)
    item = result["tasks"].get(tid)
    task = definitions.get(tid)
    policy = workflow["policy"]
    if action not in {"usage", "complete"}:
        require(task is not None, "unknown task")
    if action == "dispatch":
        require(result["status"] in {"running", "waiting_approval"}, "run not dispatchable")
        budget = policy["budget"]
        require(not ((budget.get("wall_time_seconds") is not None and result["usage"]["elapsed_seconds"] >= budget["wall_time_seconds"])
                     or (budget.get("cost_limit") is not None and result["usage"]["cost"] >= budget["cost_limit"])), "budget exhausted")
        require(item["status"] in {"pending", "ready", "retry_wait", "changes_requested", "needs_revalidation"}, "task not dispatchable")
        require(not item["reserved"], "old execution not stopped")
        require(all(result["tasks"][d]["status"] == "passed" for d in task["depends_on"]), "dependency not passed")
        require(item["attempt"] < policy["max_dispatches_per_task"], "dispatch limit")
        active = [t for t, state in result["tasks"].items() if state["reserved"]]
        require(len(active) < policy["max_parallel_workers"], "capacity exceeded")
        require(not any(scopes_overlap(task["write_scope"], definitions[t]["write_scope"]) for t in active), "write conflict")
        versions = inputs_for(task, result)
        if task["requires_approval"]:
            require(item["approval"] == {"workflow_revision": workflow["workflow_revision"], "input_versions": versions}, "approval missing/stale")
        require(task["side_effect"] == "local", "external dispatch needs a real operation/approval adapter")
        item.update(status="running", attempt=item["attempt"] + 1, dispatch_id=uuid.uuid4().hex,
                    runtime_handle=None, input_versions=copy.deepcopy(versions), artifact_revision=None,
                    result_digest=None, review_digest=None, report=None, review=None, reserved=True, reason=None, inputs_invalidated=False)
    elif action == "handle":
        require(item["status"] == "running" and payload.get("dispatch_id") == item["dispatch_id"], "invalid handle association")
        require(isinstance(payload.get("handle"), str) and payload["handle"], "missing handle")
        require(item["runtime_handle"] is None, "handle already assigned")
        item["runtime_handle"] = payload["handle"]
    elif action == "submit":
        output = payload["output"]
        require(isinstance(output, dict), "invalid output")
        validate_envelope(result, tid, output, inputs_for(task, result))
        require(not item["inputs_invalidated"], "input invalidation pending")
        key = digest(output)
        if item["result_digest"] == key and item["status"] in {"reviewing", "passed"}:
            return result  # Exact duplicate is a no-op, not a second completion.
        require(item["status"] in {"running", "outcome_unknown"}, "result not acceptable")
        require(output.get("worker_stopped") is True and output.get("side_effects_reconciled") is True, "execution outcome unknown")
        safe_path(output.get("report"))
        item.update(status="reviewing", artifact_revision=output["artifact_revision"],
                    result_digest=key, report=output["report"], reason=None)
    elif action == "review":
        review = payload["review"]
        require(item["status"] == "reviewing" and isinstance(review, dict), "not reviewing")
        validate_envelope(result, tid, review, inputs_for(task, result))
        require(review["artifact_revision"] == item["artifact_revision"], "stale review artifact")
        safe_path(review.get("report"))
        require(review.get("decision") in {"PASS", "FAIL", "NOT_RUN"}, "invalid review decision")
        if review["decision"] == "PASS":
            checks = review.get("checks")
            require(isinstance(checks, list), "missing checks")
            for criterion in task["acceptance"]:
                matches = [c for c in checks if isinstance(c, dict) and c.get("criterion") == criterion and c.get("status") == "passed"]
                require(bool(matches) and isinstance(matches[0].get("evidence"), list) and matches[0]["evidence"], "missing acceptance evidence")
                for ref in matches[0]["evidence"]:
                    safe_path(ref)
            item["status"] = "passed"
        elif review["decision"] == "FAIL":
            item["repair_count"] += 1
            item["status"] = "changes_requested" if item["repair_count"] <= policy["max_quality_repairs"] else "failed"
        else:
            item["status"] = "blocked"
        item.update(reserved=False, review=review["report"], review_digest=digest(review), reason=review["decision"])
    elif action == "timeout":
        require(item["status"] == "running", "not running")
        item.update(status="outcome_unknown", reason="timeout")
    elif action == "cancel":
        require(item["status"] != "passed", "accepted artifact requires explicit invalidation")
        item.update(status="cancelling" if item["reserved"] else "cancelled", reason="cancel_requested")
    elif action == "stopped":
        require(item["status"] in {"cancelling", "outcome_unknown", "needs_revalidation"}, "not awaiting reconciliation")
        require(payload.get("confirmed") is True and payload.get("side_effects_reconciled") is True, "stop/side effects unconfirmed")
        if item["status"] == "cancelling":
            item["status"] = "cancelled"
        elif item["status"] == "outcome_unknown":
            item["status"] = "ready"
            item["recovery_count"] += 1
        item.update(reserved=False, reason="reconciled")
    elif action == "failure":
        require(item["status"] == "running", "not running")
        require(payload.get("confirmed_stopped") is True and payload.get("side_effects_reconciled") is True, "failure outcome unknown")
        error = payload.get("error_class")
        require(error in {"transient", "permission", "permanent", "contract"}, "unknown error class")
        if error == "transient":
            item["retry_count"] += 1
            item["status"] = "retry_wait" if item["retry_count"] <= policy["max_execution_retries"] else "failed"
        else:
            item["status"] = "blocked" if error == "permission" else "failed"
        item.update(reserved=False, reason=error)
    elif action == "approve":
        require(not item["reserved"] and item["status"] in {"pending", "ready", "needs_revalidation", "changes_requested"}, "approval requires idle task")
        item["approval"] = {"workflow_revision": workflow["workflow_revision"], "input_versions": copy.deepcopy(inputs_for(task, result))}
    elif action == "invalidate":
        affected = {tid}
        while True:
            next_set = affected | {t for t, definition in definitions.items() if set(definition["depends_on"]) & affected}
            if next_set == affected:
                break
            affected = next_set
        for t in affected:
            state = result["tasks"][t]
            state.update(status="needs_revalidation", artifact_revision=None, result_digest=None, review_digest=None, report=None,
                         review=None, approval=None, inputs_invalidated=True, reason="upstream_or_artifact_changed")
        if result["status"] == "completed":
            result["status"] = "running"
    elif action == "usage":
        for key in ("elapsed_seconds", "cost"):
            value = payload.get(key, result["usage"][key])
            require(type(value) in {int, float} and math.isfinite(value) and value >= result["usage"][key], "usage must be monotonic")
            result["usage"][key] = value
        limits = policy["budget"]
        if ((limits.get("wall_time_seconds") is not None and result["usage"]["elapsed_seconds"] >= limits["wall_time_seconds"])
                or (limits.get("cost_limit") is not None and result["usage"]["cost"] >= limits["cost_limit"])):
            result["status"] = "budget_stopped"
    elif action == "complete":
        require(all(s["status"] == "passed" and not s["reserved"] for s in result["tasks"].values()), "unfinished tasks")
        result["status"] = "completed"
    else:
        raise ContractError("unknown action: " + action)
    result["revision"] += 1
    return result


class FileJournal:
    """Single writer only; torn journal tail fails closed. No external atomicity."""

    def __init__(self, directory):
        self.root = Path(directory)

    def read(self):
        path = self.root / "events.jsonl"
        require(path.is_file(), "journal missing")
        previous, ids = None, set()
        with path.open("rb") as stream:
            for line in stream:
                require(line.endswith(b"\n"), "incomplete journal tail; reconcile before repair")
                event = json.loads(line)
                require(isinstance(event, dict), "invalid event")
                claimed = event.pop("checksum", None)
                require(claimed == digest(event), "journal checksum mismatch")
                state = event["state"]
                require(event["event_id"] not in ids, "duplicate event ID")
                require(event["prev_revision"] == (None if previous is None else previous["revision"]), "journal revision gap")
                require(state["revision"] == (0 if previous is None else previous["revision"] + 1), "state revision gap")
                if previous is not None:
                    require(state["run_id"] == previous["run_id"] and state["workflow_revision"] == previous["workflow_revision"], "journal identity changed")
                ids.add(event["event_id"])
                previous = state
        require(previous is not None, "empty journal")
        return previous

    def snapshot(self, state):
        temp = self.root / ("run." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.root / "run.json")
        finally:
            if temp.exists():
                temp.unlink()

    def append(self, state, action, event_id=None):
        path = self.root / "events.jsonl"
        previous = self.read() if path.exists() else None
        expected = 0 if previous is None else previous["revision"] + 1
        require(state["revision"] == expected, "stale state revision")
        if previous is not None:
            require(state["run_id"] == previous["run_id"] and state["workflow_revision"] == previous["workflow_revision"], "identity changed")
        event = {"event_id": event_id or uuid.uuid4().hex,
                 "created_at": datetime.now(timezone.utc).isoformat(), "action": action,
                 "prev_revision": None if previous is None else previous["revision"], "state": state}
        if path.exists():
            with path.open(encoding="utf-8") as stream:
                require(all(json.loads(line)["event_id"] != event["event_id"] for line in stream), "duplicate event ID")
        event["checksum"] = digest(event)
        self.root.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as stream:
            stream.write((json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        self.snapshot(state)

    def recover(self):
        state = self.read()
        self.snapshot(state)
        return state
