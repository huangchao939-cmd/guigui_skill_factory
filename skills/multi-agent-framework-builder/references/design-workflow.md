# 需求、绘图与工作包生成

## 输入与范围

从需求和仓库提取目标、使用者、交付物、非目标、技术栈、运行平台、授权/成本/时长、共享接口和验收证据。记录事实、决定、假设、待定项；无 API 开发不索要密钥。
明确生成框架、模拟演练、真实试跑、业务开发哪些已授权；产品内运行服务另行设计，不自动添加队列/数据库或外部调用。

## 角色与图先行

中央 Orchestration 是默认模式。角色是职责不是固定人数：Orchestrator 规划/调度/状态/审批，Worker 实现自测，Reviewer 独立检查，Integrator 按需整合。角色可服务多个任务，兼任声明范围；高风险实现与验收保持独立。

先绘 diagrams/architecture.mmd：用户审批、控制平面、执行/验证/整合、状态和产物边界、真实平台。控制与数据箭头区分，Worker 不直接派发下游；未知适配标未验证。
再绘 diagrams/workflow.mmd：实际任务 ID、依赖、并行、汇合、门禁与失败出口。小项目可合图，但保留上述语义。Mermaid 是来源，非保证渲染过的图片。
图门禁：无无主任务/文件、隐式依赖、未定义汇合、无验收或异常出口。重大权限/成本/不可逆选择请用户确定，普通假设记录后继续。

配置落地用 render_workflow.py 生成 diagrams/dependencies.mmd，其中依赖以 workflow.json 为唯一来源。人工架构/流程图记录 workflow_revision；修改角色、依赖或失败策略时同步图。脚本只验证自动依赖图，人工语义需 Agent 检查，不宣称图全部机器验证。

## 任务与整合

按可验收成果拆分，先确立跨模块契约。每项含需求锚点、非目标、输入版本、owner/reviewer、scope、验收和证据；依赖未通过不派发。新增依赖修订 workflow 并失效受影响下游。
初版 join 仅 all_required：必需前置全部通过才整合。可选功能在需求阶段明确，不将失败必需分支临时改可选。整合者独占共享接口；分支通过后合并版本仍需集成门禁。
scope 为项目根相对路径，目录尾随 /，不用 glob。报告/evidence 是运行根相对路径。审查期间保守保留实现资源；未确认旧执行停止/隔离不得释放。测试缓存、输出也有所有者。
并发受实际平台槽位、预算和资源上限共同约束；确认槽位是否包含主 Agent/Reviewer。模拟按 reserved 任务槽保守计数，不代替实际 Agent 容量管理。

## 工作包

```text
.agent-framework/
  README.md
  project-brief.md
  framework-design.md
  runtime.md
  quality-gates.md
  recovery.md
  diagrams/               # 架构/流程/生成依赖图
  workflow.json           # 静态定义与版本
  agents/                 # 项目专属角色
  tasks/T01/task.md        # 持久化交接
  runs/<run-id>/          # 真实执行或显式模拟后创建
    run.json
    events.jsonl
    reports/
    evidence/
    approvals/
```

journal 保存关键快照，独立 snapshots/ 仅需导出时创建。代码在原项目位置，以 hash/commit/manifest 引用，不复制全仓库；不制造假日志/evidence。初始化 run 不等于派发过任务。
已有 AGENTS.md 与文件保留；README 只摘要，不另一套手工状态。

## 平台适配

runtime.md 映射 spawn、wait/query、message、wake、resume、cancel、确认停止、隔离、句柄、成本统计。真实工具返回才是句柄来源，不猜全局最新文件。unsupported/unverified 配降级措施。
默认宿主主 Agent 调用真实平台，辅助脚本检查协议与模拟；模型做规划判断，规则检查依赖/版本/状态/scope/预算。脚本未连接 adapter 不宣称后台调度。
缺少 resume 可任务包接管，先确认旧执行不再写同资源。取消不确认则阻断。多调度进程才使用事务存储、租约和 fencing，不能用 JSON 冒充进程锁。
