"""File-backed v2 samples, integrity checks and explicit migration behavior."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/multi-agent-framework-builder/scripts"
sys.path.insert(0, str(SCRIPTS))
from orchestration import ContractError
from migrate_v1 import migrate
from simulate_framework import build_sample
from validate_v2 import validate


class V2FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def sample(self):
        root = self.root / "sample"
        build_sample(root, True)
        return root

    def test_executed_sample_valid(self):
        self.assertEqual(validate(self.sample()), [])

    def test_missing_evidence_rejected(self):
        root = self.sample()
        (root / "runs/synthetic-run/evidence/T01-1.json").unlink()
        self.assertTrue(any("missing" in error for error in validate(root)))

    def test_changed_review_rejected(self):
        root = self.sample()
        path = root / "runs/synthetic-run/reports/T01-1-review.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["checks"][0]["evidence"] = ["evidence/T02-1.json"]
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("review report changed" in error for error in validate(root)))

    def test_changed_execution_report_rejected(self):
        root = self.sample()
        path = root / "runs/synthetic-run/reports/T01-1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["extra"] = "modified after acceptance"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("execution report changed" in error for error in validate(root)))

    def test_dependency_graph_drift(self):
        root = self.sample()
        path = root / "diagrams/dependencies.mmd"
        path.write_text(path.read_text(encoding="utf-8").replace("T02 --> T03", "T03 --> T02"), encoding="utf-8")
        self.assertTrue(any("dependency graph" in error for error in validate(root)))

    def test_snapshot_drift(self):
        root = self.sample()
        path = root / "runs/synthetic-run/run.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "failed"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("snapshot differs" in error for error in validate(root)))

    def old_package(self):
        source = self.root / "old"
        source.mkdir()
        (source / "role.md").write_text("legacy role", encoding="utf-8")
        old = {"schema_version": 1, "project": "legacy",
               "policy": {"state_owner": "main", "max_parallel_workers": 2, "max_attempts_per_task": 3},
               "roles": [{"id": rid, "prompt": "role.md"} for rid in ("main", "worker", "reviewer")],
               "tasks": [{"id": "T01", "title": "Legacy task", "owner": "worker", "reviewer": "reviewer",
                          "status": "pending", "attempt": 0, "depends_on": [], "write_scope": ["src/a.py"], "acceptance": ["actual test"]}]}
        (source / "framework.json").write_text(json.dumps(old), encoding="utf-8")
        return source, old

    def test_migration_preserves_source_and_requires_diagram_review(self):
        source, old = self.old_package()
        before = (source / "framework.json").read_bytes()
        output = migrate(source, self.root / "new")
        self.assertEqual((source / "framework.json").read_bytes(), before)
        self.assertFalse((output / "runs").exists())
        self.assertTrue(validate(output))  # Hand-authored diagrams deliberately not fabricated.
        self.assertEqual(json.loads((output / "workflow.json").read_text(encoding="utf-8"))["schema_version"], 2)
        with self.assertRaises(ContractError):
            migrate(source, output)

    def test_migration_refuses_inflight(self):
        source, old = self.old_package()
        old["tasks"][0].update(status="running", attempt=1, runtime_handle="real-associated-handle")
        (source / "framework.json").write_text(json.dumps(old), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "in-flight"):
            migrate(source, self.root / "new")
        self.assertFalse((self.root / "new").exists())

    def test_migration_does_not_guess_mixed_roles(self):
        source, old = self.old_package()
        old["tasks"][0]["reviewer"] = "worker"
        (source / "framework.json").write_text(json.dumps(old), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "role mapping"):
            migrate(source, self.root / "new")


if __name__ == "__main__":
    unittest.main()
