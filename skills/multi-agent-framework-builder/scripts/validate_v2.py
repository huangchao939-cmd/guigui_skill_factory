"""Read-only v2 definition, saved run, evidence references and generated graph checks."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("orchestration", Path(__file__).with_name("orchestration.py"))
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


def dependency_graph(workflow):
    lines = ["%% generated from workflow_revision: " + workflow["workflow_revision"], "flowchart TD"]
    for task in workflow["tasks"]:
        # IDs are schema-validated; labels deliberately use IDs, not untrusted Mermaid text.
        lines.append(f'    {task["id"]}["{task["id"]}"]')
    for task in workflow["tasks"]:
        for dep in task["depends_on"]:
            lines.append(f'    {dep} --> {task["id"]}')
    return "\n".join(lines) + "\n"


def validate(root):
    root = Path(root).resolve()
    errors = []
    try:
        workflow = json.loads((root / "workflow.json").read_text(encoding="utf-8-sig"))
        tasks = rules.validate_definition(workflow, root)
        for name in ("architecture.mmd", "workflow.mmd"):
            content = rules.local_file(root, "diagrams/" + name).read_text(encoding="utf-8")
            rules.require("workflow_revision: " + workflow["workflow_revision"] in content, "manual diagram revision mismatch: " + name)
        graph = rules.local_file(root, "diagrams/dependencies.mmd").read_text(encoding="utf-8")
        rules.require(graph == dependency_graph(workflow), "generated dependency graph differs from definition")
        runs = root / "runs"
        for run_dir in sorted(runs.iterdir()) if runs.exists() else []:
            rules.require(run_dir.resolve().is_relative_to(root) and run_dir.is_dir(), "unsafe run directory")
            run = json.loads((run_dir / "run.json").read_text(encoding="utf-8-sig"))
            rules.require(run["schema_version"] == 2 and run["workflow_revision"] == workflow["workflow_revision"], "run schema/revision mismatch")
            rules.require(run.get("definition_digest") == rules.digest(workflow), "definition digest mismatch")
            rules.require(run["run_id"] == run_dir.name and set(run["tasks"]) == set(tasks), "run identity/task mismatch")
            rules.require(rules.digest(run) == rules.digest(rules.FileJournal(run_dir).read()), "run snapshot differs from journal; reconcile")
            active = [tid for tid, state in run["tasks"].items() if state["reserved"]]
            rules.require(len(active) <= workflow["policy"]["max_parallel_workers"], "run capacity exceeded")
            for index, tid in enumerate(active):
                for other in active[index + 1:]:
                    rules.require(not rules.scopes_overlap(tasks[tid]["write_scope"], tasks[other]["write_scope"]), "run write conflict")
            for tid, state in run["tasks"].items():
                rules.require(state["status"] in {"pending", "ready", "running", "reviewing", "passed", "retry_wait", "changes_requested", "failed", "blocked", "cancelled", "needs_revalidation", "outcome_unknown", "cancelling"}, "unknown task status")
                rules.require(type(state["attempt"]) is int and 0 <= state["attempt"] <= workflow["policy"]["max_dispatches_per_task"], "invalid attempt")
                if state["status"] != "passed":
                    continue
                rules.require(state["attempt"] > 0 and not state["reserved"] and not state["inputs_invalidated"], "invalid passed state")
                rules.require(all(run["tasks"][d]["status"] == "passed" for d in tasks[tid]["depends_on"]), "passed without passed dependencies")
                for field in ("report", "review"):
                    report = json.loads(rules.local_file(run_dir, state[field]).read_text(encoding="utf-8-sig"))
                    rules.validate_envelope(run, tid, report, rules.inputs_for(tasks[tid], run))
                    rules.require(report["artifact_revision"] == state["artifact_revision"], "stale artifact evidence")
                    if field == "report":
                        rules.require(report.get("worker_stopped") is True and report.get("side_effects_reconciled") is True, "unconfirmed outcome")
                        rules.require(rules.digest(report) == state["result_digest"], "execution report changed")
                    else:
                        rules.require(rules.digest(report) == state.get("review_digest"), "review report changed")
                        rules.require(report.get("decision") == "PASS", "non-PASS review")
                        for criterion in tasks[tid]["acceptance"]:
                            matches = [c for c in report.get("checks", []) if isinstance(c, dict) and c.get("criterion") == criterion and c.get("status") == "passed"]
                            rules.require(bool(matches) and isinstance(matches[0].get("evidence"), list) and matches[0]["evidence"], "missing acceptance evidence")
                            for evidence in matches[0]["evidence"]:
                                rules.local_file(run_dir, evidence)
            if run["status"] == "completed":
                rules.require(all(s["status"] == "passed" and not s["reserved"] for s in run["tasks"].values()), "false completion")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(str(exc))
    return errors
