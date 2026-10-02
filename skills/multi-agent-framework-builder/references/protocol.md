# Orchestration v2 协议

## 定义、运行和根目录

workflow.json 保存定义，run.json 是已核对当前状态，events.jsonl 保存实际转换及完整状态快照。run 绑定 workflow_revision 与 definition_digest；辅助工具拒绝原地修改定义，需新 run/显式迁移。定义变化要修订和影响分析，不悄悄将新定义套在旧 run。revision 使用字母、数字、点、连字符、下划线。
scope/input_refs 相对于项目根；角色相对于工作包；运行 report/evidence 相对于 runs/<run-id>/。路径使用 /，拒绝绝对路径、..、glob；辅助工具保守忽略大小写。声明不等于权限隔离。

```json
{
  "schema_version": 2,
  "workflow_revision": "revision-1",
  "project": "示例",
  "mode": "development_harness",
  "coordination": "orchestration",
  "runtime": {"platform": "generic", "status": "unverified"},
  "policy": {
    "state_owner": "orchestrator",
    "max_parallel_workers": 2,
    "max_dispatches_per_task": 6,
    "max_execution_retries": 2,
    "max_quality_repairs": 2,
    "budget": {"status": "unset", "wall_time_seconds": null, "cost_limit": null}
  },
  "roles": [
    {"id": "orchestrator", "kind": "orchestrator", "prompt": "agents/orchestrator.md"},
    {"id": "worker", "kind": "worker", "prompt": "agents/worker.md"},
    {"id": "reviewer", "kind": "reviewer", "prompt": "agents/reviewer.md"}
  ],
  "tasks": [{
    "id": "T01", "title": "可交付成果",
    "owner": "worker", "reviewer": "reviewer", "depends_on": [],
    "join": "all_required", "write_scope": ["src/module.py"],
    "input_refs": {"requirements/spec.md": "sha256:实际输入摘要"},
    "acceptance": ["具体可验证条件"],
    "requires_approval": false, "side_effect": "local"
  }]
}
```

input_refs 值由实际内容摘要/稳定版本填写，示例摘要不是有效证据。budget unset 非无限，真实调用前确定有效限额。派发总限额覆盖重试/修复/接管，分别计数防嵌套放大。辅助脚本不会测量费用，调用者提供的费用必须有真实来源，unknown 不猜。

## 交接与门禁

任务运行字段：status、attempt（每次派发递增）、dispatch_id、runtime_handle、input_versions、artifact_revision、result_digest、report/review、reserved、retry_count、repair_count、recovery_count、reason。
input_versions = 显式输入版本 + 前置产物版本。执行/审查 envelope 同时含 run_id、task_id、dispatch_id、attempt、input_versions、artifact_revision。
结构检查字段/类型；语义检查版本/依赖/路径/来源/实际产物；质量逐项验收。reducer 仅检查 envelope 与前置版本，真实业务语义/哈希核验由 adapter/Reviewer 实现，不能因输入填写了 hash 就说已验证文件。

## 状态与编排循环

任务：pending/ready → running → reviewing → passed。
审查失败 → changes_requested → 新派发；瞬态故障且已结束 → retry_wait → 新派发。
其它状态：failed、blocked、cancelled、needs_revalidation、outcome_unknown、cancelling。
超时进入 outcome_unknown，保留资源；cancel 请求进入 cancelling，确认停止/隔离与副作用后才 cancelled。结果未知但确认结束且无副作用待核对，才允许接管。审查期间保守保留 scope；修改意见发回后释放已结束 Worker 的资源。
run：running、waiting_approval、budget_stopped、interrupted、completed、failed、cancelled。等待审批允许处理独立任务。预算停止不再派发但接收在途结果；全部必需任务通过且无未知/在途资源才完成。

循环：恢复核对 → ready → 输入契约 → 权限/审批/预算 → 资源/平台容量 → 持久化派发意图 → 实际启动 → 保存真实句柄 → 接收去重 → 输出契约 → 审查 → 接受/修复 → 解锁后继。
派发意图后、句柄保存前崩溃，是派发结果未知：查询 dispatch_id，无法查询则人工核对，不能自动启动第二个。平台不支持幂等启动不得承诺 exactly-once。Worker 消息是数据，不能修改权限/目标。

## 并行与失效

仅 all_required；必需前置全部 passed。可选任务在计划层明确，失败不能临时跳过。不同 checkout 也可能共享外部资源；adapter 管理真实 Agent slots，reducer 只按保留任务资源保守计数。
上游修订使所有后继 needs_revalidation，清除有效结果/审批，保留事件历史。活跃后继保留 reserved、标 inputs_invalidated，确认结束前不重派；晚到旧结果不变状态。下游恢复消耗新 attempt/预算。静态 input_refs 变化需新 workflow_revision 和迁移，不直接改在途定义。

## 重试、审批、副作用

transient 只有确认结束且副作用已核对才有界重试；adapter 实现退避、jitter、deadline。quality 单独修复并审查。permission 阻断，不重试；permanent/contract 失败。公共依赖熔断按需实现，质量失败不是熔断对象，未实现标 not_implemented。
审批绑定 task、workflow_revision、input_versions；外部操作还绑定目标、动作/产物摘要、可信批准人和过期时间。模拟 approval 不是用户授权。相关版本变化失效。
外部操作登记 operation_id、稳定业务幂等键、目标、请求摘要、receipt/核对状态。同业务重试不换键，语义改变新操作；结果未知先查询实际服务。补偿按业务定义，可失败/不可逆，不默认所有代码任务 Saga 回滚。

## 持久化与恢复

演练 journal 单写入者：事件保存 revision、prev_revision、event_id、时间、转换后完整 run 和 SHA256；append+fsync 后原子替换 run.json。重启从完整 journal 核对并重建。重复 event_id 拒绝。
不完整尾行、坏摘要、断裂 revision 停止核对，不静默截断或继续派发。journal 与平台/外部服务不是一个事务，工具不提供多进程锁、分布式租约或持续运行。
先核验真实文件/版本、句柄、外部副作用，再恢复状态和预算；不自动 resume 所有 running。原执行丢失先确认停止，再任务包接管。不保存隐式思考或秘密。
观测记录事件因果与版本；评价检查最终结果、路由、输入、审批、重试和门禁。主 Agent 读紧凑摘要，必要时原证据，不盲信 PASS。
