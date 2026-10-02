"""Synthetic contract checks; no models, network or real agent dispatch."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/multi-agent-framework-builder/scripts/validate_framework.py"
spec = importlib.util.spec_from_file_location("framework_validator", SCRIPT)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "role.md").write_text("test role", encoding="utf-8")
        (self.root / "evidence.txt").write_text("synthetic evidence", encoding="utf-8")
        self.data = {"policy": {"state_owner": "main", "max_parallel_workers": 2, "max_attempts_per_task": 3},
                     "roles": [{"id": "main", "prompt": "role.md"}, {"id": "worker", "prompt": "role.md"},
                               {"id": "reviewer", "prompt": "role.md"}], "tasks": []}

    def task(self, tid="T1", **changes):
        value = {"id": tid, "owner": "worker", "reviewer": "reviewer", "depends_on": [],
                 "write_scope": [f"src/{tid}.py"], "acceptance": ["demo check"], "status": "pending", "attempt": 0}
        value.update(changes)
        self.data["tasks"].append(value)
        return value

    def check(self):
        (self.root / "framework.json").write_text(json.dumps(self.data), encoding="utf-8")
        return validator.validate(self.root)

    def passed_task(self):
        task = self.task(status="passed", attempt=1, artifact_revision="revision-1", report="report.json", review="review.json")
        report = {"task_id": "T1", "attempt": 1, "artifact_revision": "revision-1"}
        review = dict(report, decision="PASS", checks=[{"criterion": "demo check", "status": "passed", "evidence": ["evidence.txt"]}])
        (self.root / "report.json").write_text(json.dumps(report), encoding="utf-8")
        (self.root / "review.json").write_text(json.dumps(review), encoding="utf-8")
        return task

    def test_pending(self):
        self.task()
        self.assertEqual(self.check(), [])

    def test_current_evidence(self):
        self.passed_task()
        self.assertEqual(self.check(), [])

    def test_cycle(self):
        self.task("T1", depends_on=["T2"])
        self.task("T2", depends_on=["T1"])
        self.assertTrue(any("cycle" in e for e in self.check()))

    def test_write_conflict(self):
        self.task("T1", status="running", attempt=1, write_scope=["src/"])
        self.task("T2", status="running", attempt=1, write_scope=["src/api.py"])
        self.assertTrue(any("write conflict" in e for e in self.check()))

    def test_stale_revision(self):
        self.passed_task()["artifact_revision"] = "revision-2"
        self.assertTrue(any("stale" in e for e in self.check()))

    def test_fake_pass(self):
        self.task(status="passed", attempt=3, artifact_revision="demo")
        self.assertTrue(any("report" in e for e in self.check()))

    def test_unpassed_dependency(self):
        self.task("T1")
        self.task("T2", depends_on=["T1"], status="ready")
        self.assertTrue(any("dependency not passed" in e for e in self.check()))


if __name__ == "__main__":
    unittest.main()
