"""Explicit v1-to-v2 definition migration; preserves source, discards no live work."""
import argparse
import json
from pathlib import Path
import shutil
from orchestration import local_file, require, validate_definition
from validate_v2 import dependency_graph
from validate_framework import validate_v1


def migrate(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    require(not output.exists() and not output.is_relative_to(source), "output must be new and outside source")
    errors = validate_v1(source)
    require(not errors, "v1 validation failed: " + "; ".join(errors))
    old = json.loads((source / "framework.json").read_text(encoding="utf-8-sig"))
    require(old.get("tasks"), "no tasks to migrate")
    require(not any(t["status"] in {"running", "reviewing"} or t.get("runtime_handle") for t in old["tasks"]), "in-flight/associated execution: reconcile before migration")
    owner = old["policy"]["state_owner"]
    workers = {t["owner"] for t in old["tasks"]}
    reviewers = {t["reviewer"] for t in old["tasks"]}
    require(not (workers & reviewers or owner in workers | reviewers), "v2 requires explicit separate role mapping")
    require(all(r["id"] in workers | reviewers | {owner} for r in old["roles"]), "unmapped extra role; map manually")
    roles = [dict(r, kind="orchestrator" if r["id"] == owner else "reviewer" if r["id"] in reviewers else "worker") for r in old["roles"]]
    workflow = {"schema_version": 2, "workflow_revision": "migration-1", "project": old.get("project", "migrated-project"),
                "mode": "development_harness", "coordination": "orchestration",
                "runtime": {"platform": old.get("runtime", {}).get("platform", "generic"), "status": "unverified"},
                "policy": {"state_owner": owner, "max_parallel_workers": old["policy"]["max_parallel_workers"],
                           "max_dispatches_per_task": old["policy"]["max_attempts_per_task"], "max_execution_retries": 0,
                           "max_quality_repairs": 0, "budget": {"status": "unset", "wall_time_seconds": None, "cost_limit": None}},
                "roles": roles, "tasks": []}
    for task in old["tasks"]:
        workflow["tasks"].append({"id": task["id"], "title": task.get("title", task["id"]),
                                  "owner": task["owner"], "reviewer": task["reviewer"], "depends_on": task["depends_on"],
                                  "join": "all_required", "write_scope": [p.replace("\\", "/") for p in task["write_scope"]],
                                  "input_refs": {}, "acceptance": task["acceptance"], "requires_approval": False, "side_effect": "local"})
    validate_definition(workflow)
    # Resolve every copied file before creating the destination; no implicit symlink copying.
    copies = []
    for role in roles:
        relative = role["prompt"]
        require(relative not in {"workflow.json", "MIGRATION-REVIEW.md"}
                and not relative.startswith(("legacy/", "diagrams/", "runs/")), "prompt collides with generated migration files")
        copies.append((relative, local_file(source, relative)))
    output.mkdir(parents=True)
    (output / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for relative, original in copies:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    (output / "legacy").mkdir()
    shutil.copyfile(source / "framework.json", output / "legacy/framework-v1.json")
    (output / "diagrams").mkdir()
    (output / "diagrams/dependencies.mmd").write_text(dependency_graph(workflow), encoding="utf-8")
    (output / "MIGRATION-REVIEW.md").write_text(
        "# 迁移待审，不可直接启动\n\n原目录未改。旧 PASS 未继承；所有新任务尚未执行。\n"
        "旧报告/证据留在原目录；legacy 仅保存旧定义。补齐实际输入版本、授权、副作用、预算、任务/运行说明。\n"
        "旧提示词仅复制，必须按 v2 重写。绘制架构/流程图并绑定 migration-1，核对 scope 根和真实适配，完成结构与模拟验收后才启动。\n"
        "当前故意不创建 run 或虚构手工图；validate_framework 会报告缺少图，直至完成迁移审查。\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(migrate(args.source, args.output))


if __name__ == "__main__":
    main()
