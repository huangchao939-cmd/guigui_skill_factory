"""Run protocol tests and generate two clearly synthetic, executed sample packages."""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import unittest
from orchestration import FileJournal, digest, new_run, require, transition
from self_test import ProtocolTests, example_workflow, output_for, review_for
from validate_v2 import dependency_graph, validate


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_sample(root, parallel):
    workflow = example_workflow(parallel)
    root.mkdir()
    save_json(root / "workflow.json", workflow)
    for role in workflow["roles"]:
        path = root / role["prompt"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Synthetic {role['kind']}\n\n模拟脚本替代此角色，没有启动真实 Agent。\n", encoding="utf-8")
    (root / "sample-input.json").write_text("[2, 2]\n", encoding="utf-8")
    (root / "README.md").write_text("# 已执行的本地模拟样例\n\n仅标准库确定性求和与协议演练，没有真实模型/Agent/平台。\n"
                                   "示例角色仅是模拟标识，不是可直接启动业务的项目提示词。\n", encoding="utf-8")
    diagrams = root / "diagrams"
    diagrams.mkdir()
    header = "%% workflow_revision: " + workflow["workflow_revision"] + "\n"
    (diagrams / "architecture.mmd").write_text(header + "flowchart TD\n    U[User] --> O[Orchestrator]\n    O --> W[Workers]\n    O --> R[Reviewer]\n    O --> I[Integrator]\n    O --> S[(Journal and Run)]\n    W --> A[(Artifacts)]\n    R --> A\n    I --> A\n", encoding="utf-8")
    edges = ("    Start --> T01\n    Start --> T02\n    V01 -->|pass| J{Both passed}\n    V02 -->|pass| J\n    J --> T03\n"
             if parallel else "    Start --> T01\n    V01 -->|pass| T02\n    V02 -->|pass| T03\n")
    gates = ""
    for tid in ("T01", "T02", "T03"):
        gate = "V" + tid[1:]
        gates += (f"    {tid} --> {gate}{{Review {tid}}}\n    {gate} -->|fail| F{tid}[Repair within budget]\n"
                  f"    F{tid} --> {tid}\n    F{tid} -->|exhausted| H[Stop and report]\n"
                  f"    {tid} -->|timeout| U{tid}[Keep resource and reconcile]\n    U{tid} -->|confirmed stopped| F{tid}\n")
    (diagrams / "workflow.mmd").write_text(header + "flowchart TD\n" + edges + gates + "    V03 -->|pass| D[Complete]\n", encoding="utf-8")
    (diagrams / "dependencies.mmd").write_text(dependency_graph(workflow), encoding="utf-8")
    run_dir = root / "runs/synthetic-run"
    state = new_run(workflow, "synthetic-run")
    journal = FileJournal(run_dir)
    journal.append(state, "initialized")

    def step(action, tid=None, **payload):
        nonlocal state
        updated = transition(workflow, state, action, tid, **payload)
        if updated["revision"] != state["revision"]:
            journal.append(updated, action + (":" + tid if tid else ""))
        state = updated

    def deliver(tid):
        value = sum(json.loads((root / "sample-input.json").read_text(encoding="utf-8")))
        require(value == 4, "synthetic calculation failed")
        output = output_for(state, tid)
        output["artifact_revision"] = "sha256:" + digest({"sum": value})
        save_json(run_dir / output["report"], output)
        evidence = {"mode": "synthetic", "method": "sum([2, 2]) == 4", "actual": value, "passed": value == 4}
        save_json(run_dir / f"evidence/{tid}-{output['attempt']}.json", evidence)
        step("submit", tid, output=output)
        review = review_for(state, tid)
        save_json(run_dir / review["report"], review)
        step("review", tid, review=review)

    if parallel:
        step("dispatch", "T01")
        step("dispatch", "T02")
        deliver("T01")
        deliver("T02")
        step("dispatch", "T03")
        deliver("T03")
    else:
        for tid in ("T01", "T02", "T03"):
            step("dispatch", tid)
            deliver(tid)
    step("complete")
    require(not validate(root), "generated sample failed saved-state validation")
    return {"path": str(root), "mode": "synthetic", "status": state["status"], "saved_state_checks": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), "output must not exist; no overwrite")
    output.mkdir(parents=True)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProtocolTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (output / "test-output.txt").write_text(stream.getvalue(), encoding="utf-8")
    samples = []
    if result.wasSuccessful():
        samples = [build_sample(output / "serial", False), build_sample(output / "parallel", True)]
    save_json(output / "validation.json", {"date": datetime.now(timezone.utc).isoformat(), "mode": "synthetic_local",
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "samples": samples,
              "real_platform": "not_run", "visual_rendering": "not_run", "external_idempotency": "mock_adapter_only"})
    print(stream.getvalue())
    print("Synthetic evidence:", output)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
