# 协作契约、质量门禁与恢复

## 任务状态

`pending → ready → running → reviewing → passed`。
未通过审查：`reviewing → changes_requested → ready`，每次重新执行增加 attempt。
还允许 `failed`（确实失败）、`blocked`（有具体依赖/权限/环境阻碍）、`paused`（预算或用户暂停）、`cancelled`。
原因为重试耗尽时保持失败/等待，不强制通过。允许在范围内继续独立任务；有失败任务不能宣称整体完成。
如果用户明确接受缺陷，记录豁免与接受者和理由；不得把 waived 写成测试 passed。

## framework.json

这是本技能的文件协议，不代表运行时调度服务。按项目实际填写，可增加兼容字段：

```json
{
  "schema_version": 1,
  "project": "项目名称",
  "mode": "development_harness",
  "runtime": {"platform": "generic", "status": "unverified"},
  "policy": {
    "max_parallel_workers": 1,
    "max_attempts_per_task": 3,
    "budget": {"status": "unset", "wall_time_minutes": null, "cost_limit": null},
    "state_owner": "orchestrator"
  },
  "roles": [
    {"id": "orchestrator", "prompt": "agents/orchestrator.md"},
    {"id": "worker", "prompt": "agents/worker.md"},
    {"id": "reviewer", "prompt": "agents/reviewer.md"}
  ],
  "tasks": []
}
```

初版任务不得为空：根据用户需求填写实际任务，至少有一个代表任务及其验收项；纯角色设计请求可明确用空任务清单并注明尚未分解业务。
默认重试数 3 是可修改的保守选择，不是行业标准。预算 unset 不表示无限预算；真实运行前确认用户预算/平台限制并以其中更严格者为准。

单个任务字段：

```json
{
  "id": "T01",
  "title": "实际任务标题",
  "owner": "worker",
  "reviewer": "reviewer",
  "depends_on": [],
  "write_scope": ["src/example.py"],
  "acceptance": ["具体可验证条件"],
  "status": "pending",
  "attempt": 0,
  "artifact_revision": null,
  "runtime_handle": null,
  "report": null,
  "review": null
}
```

write_scope 采用明确路径或目录，目录后缀 `/`，不用模糊 glob；相交写范围只能串行或隔离 checkout。
根路径相对于目标项目/框架，并在设计中明确定义，不用文件协议自身假装提供 OS 沙箱。
attempt 是该次开发执行编号，启动时增加；artifact_revision 使用 commit、产物 manifest hash 或明确内容摘要版本。
不能用文件修改时间充当足以证明全部内容一致的版本。

## 报告与当前证据

执行报告包含 task_id、attempt、artifact_revision、修改路径、结果摘要、自测命令与结果、未完成项和副作用。
验证报告包含相同关联字段、实际执行的验收项、判定、问题优先级、证据路径、未执行检查及原因。
当前任务必须核对 report/review 的三个关联字段，超时通知、旧报告或旧截图不能验收当前版本。

passed 必须同时满足：依赖已通过、当前产物存在、每项必需验收有实际证据、无未解决阻断问题、审查关联版本一致。
不同任务可以使用不同门禁；对 UI 保存当前版本截图，对 API 保存真实请求结果，对内容保存来源覆盖，对持久化行为验证重复执行。
用 role 提示词“测试通过”不是验收证据。没有平台环境时记录 not_run，不判平台验收通过。

## 所有权与事件

主 Agent 是任务状态单个写入者。执行者各写自己的任务目录，验证者各写自己的报告/evidence。
经验条目由角色提出，主 Agent 或指定整合者归并，避免所有角色并发修改一个 lessons-learned.md。
events.jsonl 记录实际事件时间（ISO 8601 含时区）、task_id、attempt、actor、类型、artifact_revision、摘要和证据引用。
不要求保存全部模型隐式思考；日志保存可核查操作、决定和结果，不保存密钥或不必要敏感数据。
主 Agent 以 compact summary 管理上下文；冲突、严重问题和质量争议时查看原证据，不只 grep 一个 PASS。

## 中断恢复

1. 读取项目目标、frame state、当前 checkpoint 和最近有关事件，恢复本轮约束。
2. 核验实际文件/版本，识别在途工作与句柄有效性；不要重复派给仍在运行的执行者。
3. 若句柄存在，按实际平台能力查询/等待或续作；若失效，带任务交接包恢复新执行者。
4. 若任务写入过但事件缺失，先检查副作用；外部写入要求业务幂等键或人工核对，不盲重试。
5. 重新确认依赖、资源所有者和预算，过期报告不用于当前验收。
6. 记录恢复事件与旧/新 attempt 关系，再继续。

checkpoint 记录目标摘要、最新任务 revision、剩余工作、在途句柄、预算消耗与关键决定索引。
有限任务使用 JSON/Markdown 和单个状态写入者即可；多调度进程或产品服务才考虑事务数据库、锁和队列，并说明理由。

## 失败策略

| 失败 | 处理 |
|---|---|
| 稳定可复现的测试失败 | 明确问题后修复，当前版本重新验证 |
| 环境/网络短暂失败 | 有界重试，检查是否有副作用；不重试权限拒绝 |
| 缺少权限/预算/必要需求 | 保存阻碍及已完成部分，停止依赖操作 |
| 共享文件冲突 | 停止冲突写入并由整合者处理，必要时重验 |
| Agent 无法恢复 | 交接包恢复等效执行者，不冒用句柄 |
| 旧结果晚到 | 记录为过期，不能改变新版本状态 |
| 重试或预算耗尽 | 停派并标明 remaining work，不降低门禁 |
