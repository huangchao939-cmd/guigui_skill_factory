"""Synthetic protocol behavior tests. No real agents, network or payments."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from orchestration import ContractError, FileJournal, digest, envelope, new_run, scopes_overlap, transition, validate_definition


def example_workflow(parallel=False):
    workflow = {"schema_version": 2, "workflow_revision": "sample-1", "project": "synthetic-sum",
                "mode": "development_harness", "coordination": "orchestration",
                "runtime": {"platform": "synthetic", "status": "simulated"},
                "policy": {"state_owner": "main", "max_parallel_workers": 2, "max_dispatches_per_task": 6,
                           "max_execution_retries": 1, "max_quality_repairs": 1,
                           "budget": {"status": "configured", "wall_time_seconds": 60, "cost_limit": 1}},
                "roles": [{"id": "main", "kind": "orchestrator", "prompt": "agents/orchestrator.md"},
                          {"id": "worker", "kind": "worker", "prompt": "agents/worker.md"},
                          {"id": "reviewer", "kind": "reviewer", "prompt": "agents/reviewer.md"},
                          {"id": "integrator", "kind": "integrator", "prompt": "agents/integrator.md"}], "tasks": []}
    for tid, deps in (("T01", []), ("T02", [] if parallel else ["T01"]), ("T03", ["T01", "T02"] if parallel else ["T02"])):
        workflow["tasks"].append({"id": tid, "title": "Synthetic sum " + tid,
                                  "owner": "integrator" if tid == "T03" else "worker", "reviewer": "reviewer",
                                  "depends_on": deps, "join": "all_required", "write_scope": [f"src/{tid}.json"],
                                  "input_refs": {"sample-input.json": digest([2, 2])},
                                  "acceptance": ["synthetic sum equals 4"], "requires_approval": False, "side_effect": "local"})
    return workflow


def output_for(run, tid):
    output = envelope(run, tid)
    output.update(artifact_revision="sha256:" + digest({"sum": 4}),
                  report=f"reports/{tid}-{output['attempt']}.json", worker_stopped=True, side_effects_reconciled=True)
    return output


def review_for(run, tid, decision="PASS"):
    review = envelope(run, tid)
    review.update(report=f"reports/{tid}-{review['attempt']}-review.json", decision=decision,
                  checks=[{"criterion": "synthetic sum equals 4", "status": "passed",
                           "evidence": [f"evidence/{tid}-{review['attempt']}.json"]}])
    return review


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.workflow = example_workflow()
        self.run = new_run(self.workflow, "test-run")

    def step(self, action, tid=None, **payload):
        self.run = transition(self.workflow, self.run, action, tid, **payload)
        return self.run

    def pass_task(self, tid):
        self.step("dispatch", tid)
        self.step("submit", tid, output=output_for(self.run, tid))
        self.step("review", tid, review=review_for(self.run, tid))

    def test_serial_and_completion(self):
        for tid in ("T01", "T02", "T03"):
            self.pass_task(tid)
        self.step("complete")
        self.assertEqual(self.run["status"], "completed")

    def test_parallel_join_waits_for_all(self):
        self.workflow = example_workflow(True)
        self.run = new_run(self.workflow, "test-run")
        self.step("dispatch", "T01")
        self.step("dispatch", "T02")
        with self.assertRaisesRegex(ContractError, "dependency"):
            self.step("dispatch", "T03")
        for tid in ("T01", "T02"):
            self.step("submit", tid, output=output_for(self.run, tid))
            self.step("review", tid, review=review_for(self.run, tid))
        self.pass_task("T03")
        self.step("complete")

    def test_duplicate_result_is_noop(self):
        self.step("dispatch", "T01")
        output = output_for(self.run, "T01")
        self.step("submit", "T01", output=output)
        before = copy.deepcopy(self.run)
        self.step("submit", "T01", output=output)
        self.assertEqual(self.run, before)

    def test_old_attempt_rejected(self):
        self.step("dispatch", "T01")
        old = output_for(self.run, "T01")
        self.step("failure", "T01", confirmed_stopped=True, side_effects_reconciled=True, error_class="transient")
        self.step("dispatch", "T01")
        with self.assertRaisesRegex(ContractError, "dispatch_id|attempt"):
            self.step("submit", "T01", output=old)

    def test_quality_repair_and_limit(self):
        for expected in ("changes_requested", "failed"):
            self.step("dispatch", "T01")
            self.step("submit", "T01", output=output_for(self.run, "T01"))
            self.step("review", "T01", review=review_for(self.run, "T01", "FAIL"))
            self.assertEqual(self.run["tasks"]["T01"]["status"], expected)
        with self.assertRaises(ContractError):
            self.step("dispatch", "T01")

    def test_repair_can_pass_current_version(self):
        self.step("dispatch", "T01")
        self.step("submit", "T01", output=output_for(self.run, "T01"))
        self.step("review", "T01", review=review_for(self.run, "T01", "FAIL"))
        self.pass_task("T01")
        self.assertEqual(self.run["tasks"]["T01"]["attempt"], 2)
        self.assertEqual(self.run["tasks"]["T01"]["status"], "passed")

    def test_case_insensitive_directory_conflict(self):
        self.workflow = example_workflow(True)
        self.workflow["tasks"][0]["write_scope"] = ["SRC/"]
        self.run = new_run(self.workflow, "test-run")
        self.step("dispatch", "T01")
        with self.assertRaisesRegex(ContractError, "write conflict"):
            self.step("dispatch", "T02")
        self.assertFalse(scopes_overlap(["src/a/"], ["src/ab/file.py"]))

    def test_capacity(self):
        self.workflow = example_workflow(True)
        self.workflow["policy"]["max_parallel_workers"] = 1
        self.run = new_run(self.workflow, "test-run")
        self.step("dispatch", "T01")
        with self.assertRaisesRegex(ContractError, "capacity"):
            self.step("dispatch", "T02")

    def test_timeout_holds_resource_until_reconciled(self):
        self.step("dispatch", "T01")
        self.step("timeout", "T01")
        self.assertTrue(self.run["tasks"]["T01"]["reserved"])
        with self.assertRaises(ContractError):
            self.step("dispatch", "T01")
        with self.assertRaises(ContractError):
            self.step("stopped", "T01", confirmed=True, side_effects_reconciled=False)
        self.step("stopped", "T01", confirmed=True, side_effects_reconciled=True)
        self.step("dispatch", "T01")
        self.assertEqual(self.run["tasks"]["T01"]["recovery_count"], 1)

    def test_cancel_holds_resource_and_rejects_late_result(self):
        self.step("dispatch", "T01")
        old = output_for(self.run, "T01")
        self.step("cancel", "T01")
        self.assertTrue(self.run["tasks"]["T01"]["reserved"])
        self.step("stopped", "T01", confirmed=True, side_effects_reconciled=True)
        with self.assertRaises(ContractError):
            self.step("submit", "T01", output=old)
        self.assertEqual(self.run["tasks"]["T01"]["status"], "cancelled")

    def test_upstream_change_invalidates_pass_and_approval(self):
        self.workflow["tasks"][1]["requires_approval"] = True
        self.run = new_run(self.workflow, "test-run")
        self.pass_task("T01")
        self.step("approve", "T02")
        self.pass_task("T02")
        self.step("invalidate", "T01")
        self.assertEqual(self.run["tasks"]["T02"]["status"], "needs_revalidation")
        self.assertIsNone(self.run["tasks"]["T02"]["approval"])
        self.pass_task("T01")
        with self.assertRaisesRegex(ContractError, "approval"):
            self.step("dispatch", "T02")

    def test_active_descendant_not_released(self):
        self.pass_task("T01")
        self.step("dispatch", "T02")
        old = output_for(self.run, "T02")
        self.step("invalidate", "T01")
        self.assertTrue(self.run["tasks"]["T02"]["reserved"])
        with self.assertRaises(ContractError):
            self.step("submit", "T02", output=old)
        with self.assertRaises(ContractError):
            self.step("dispatch", "T02")
        self.step("stopped", "T02", confirmed=True, side_effects_reconciled=True)
        self.assertFalse(self.run["tasks"]["T02"]["reserved"])

    def test_budget_stops_dispatch_but_receives_result(self):
        self.step("dispatch", "T01")
        self.step("usage", elapsed_seconds=60)
        self.step("submit", "T01", output=output_for(self.run, "T01"))
        self.step("review", "T01", review=review_for(self.run, "T01"))
        with self.assertRaisesRegex(ContractError, "run not dispatchable"):
            self.step("dispatch", "T02")

    def test_transient_limit_and_permission_not_retried(self):
        for expected in ("retry_wait", "failed"):
            self.step("dispatch", "T01")
            self.step("failure", "T01", confirmed_stopped=True, side_effects_reconciled=True, error_class="transient")
            self.assertEqual(self.run["tasks"]["T01"]["status"], expected)
        self.run = new_run(self.workflow, "permission-run")
        self.step("dispatch", "T01")
        self.step("failure", "T01", confirmed_stopped=True, side_effects_reconciled=True, error_class="permission")
        self.assertEqual(self.run["tasks"]["T01"]["retry_count"], 0)
        self.assertEqual(self.run["tasks"]["T01"]["status"], "blocked")

    def test_fake_pass_missing_evidence(self):
        self.step("dispatch", "T01")
        self.step("submit", "T01", output=output_for(self.run, "T01"))
        review = review_for(self.run, "T01")
        review["checks"][0]["evidence"] = []
        with self.assertRaisesRegex(ContractError, "evidence"):
            self.step("review", "T01", review=review)

    def test_stale_review_and_false_completion(self):
        self.step("dispatch", "T01")
        self.step("submit", "T01", output=output_for(self.run, "T01"))
        review = review_for(self.run, "T01")
        review["artifact_revision"] = "old"
        with self.assertRaisesRegex(ContractError, "stale"):
            self.step("review", "T01", review=review)
        with self.assertRaisesRegex(ContractError, "unfinished"):
            self.step("complete")

    def test_definition_rejects_cycle_and_unsafe_paths(self):
        self.workflow["tasks"][0]["depends_on"] = ["T03"]
        with self.assertRaisesRegex(ContractError, "cycle"):
            validate_definition(self.workflow)
        self.workflow = example_workflow()
        for value in ("../outside", "C:/outside", "//host/share", "src/*.py", "src\\file.py", "src//", "src//file.py"):
            self.workflow["tasks"][0]["write_scope"] = [value]
            with self.assertRaises(ContractError):
                validate_definition(self.workflow)

    def test_external_requires_real_adapter(self):
        self.workflow["tasks"][0].update(side_effect="external", requires_approval=True)
        self.run = new_run(self.workflow, "test-run")
        self.step("approve", "T01")
        with self.assertRaisesRegex(ContractError, "real operation"):
            self.step("dispatch", "T01")

    def test_dispatch_limit_covers_recovery(self):
        self.workflow["policy"]["max_dispatches_per_task"] = 1
        self.run = new_run(self.workflow, "test-run")
        self.step("dispatch", "T01")
        self.step("timeout", "T01")
        self.step("stopped", "T01", confirmed=True, side_effects_reconciled=True)
        with self.assertRaisesRegex(ContractError, "dispatch limit"):
            self.step("dispatch", "T01")

    def test_journal_recovers_after_snapshot_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = FileJournal(directory)
            journal.append(self.run, "initialized")
            self.step("dispatch", "T01")
            journal.append(self.run, "dispatch:T01")
            (Path(directory) / "run.json").write_text("broken", encoding="utf-8")
            recovered = journal.recover()
            self.assertEqual(recovered, self.run)
            self.assertTrue(recovered["tasks"]["T01"]["reserved"])
            self.assertIsNone(recovered["tasks"]["T01"]["runtime_handle"])

    def test_definition_cannot_change_in_place(self):
        self.workflow["tasks"][0]["input_refs"]["sample-input.json"] = "changed"
        with self.assertRaisesRegex(ContractError, "definition changed"):
            self.step("dispatch", "T01")

    def test_budget_cannot_be_reset_by_artifact_invalidation(self):
        self.step("usage", cost=1)
        self.step("invalidate", "T01")
        with self.assertRaises(ContractError):
            self.step("dispatch", "T01")

    def test_journal_rejects_torn_tail_and_duplicate_event(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = FileJournal(directory)
            journal.append(self.run, "initialized", "event-1")
            self.step("dispatch", "T01")
            with self.assertRaisesRegex(ContractError, "duplicate"):
                journal.append(self.run, "dispatch", "event-1")
            with (Path(directory) / "events.jsonl").open("ab") as stream:
                stream.write(b'{"incomplete":')
            with self.assertRaisesRegex(ContractError, "incomplete"):
                journal.recover()

    def test_mock_adapter_reconciles_external_success_before_local_record(self):
        # This proves only this mock adapter's stable-key pattern, not reducer/provider guarantees.
        receipts, calls = {}, []

        def execute(key):
            if key not in receipts:
                calls.append(key)
                receipts[key] = {"operation_id": key, "status": "succeeded"}
            return receipts[key]

        key = "workflow-business-operation-1"
        execute(key)  # Simulated response lost before journal update.
        receipt = receipts.get(key)  # Query before retry.
        self.assertEqual(receipt["status"], "succeeded")
        execute(key)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
