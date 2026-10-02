---
name: multi-agent-framework-builder
description: 根据项目需求先绘图，再生成以中央 Orchestration 为默认模式的多 Agent 开发工作包，包含角色、依赖、版本化交接、质量门禁和恢复协议。用于项目专属开发协作框架；不默认启动业务开发或构建托管 Agent 服务。
---

# 多 Agent Orchestration 框架生成器 · v2

将需求变成有图、有协议、可启动、可验证、可恢复的项目专属工作包。按可独立交付的成果拆分，角色和人数按需选择；小任务可建议单 Agent。

## 范围与读取

默认生成框架和无外部副作用的模拟演练，不启动真实子 Agent、业务开发、部署或付费调用。用户同时要求试跑/开发时才在相应授权内执行；工具可用不等于授权。产品内托管服务另需 API、租户、事务存储与部署实现，不以提示词冒充服务。

设计时完整读取 [设计与绘图流程](references/design-workflow.md) 和 [编排协议](references/protocol.md)。生成角色时读取并适配 [编排器](assets/orchestrator.md)、[执行者](assets/worker.md)、[审查者](assets/reviewer.md)；并行整合需要时再读 [整合者](assets/integrator.md)。
验证时读取 [验证标准](references/validation.md)；升级旧项目先读 [迁移说明](references/migration.md)。[模拟样例](references/examples.md) 是设计起点，不是固定项目内容。

## 生成步骤

1. 阅读需求、仓库规范、代码和环境，记录事实、决定、假设、待定项及执行范围。继承用户技术栈和模型，不固化品牌或机器路径。
2. 先约定接口，再划分任务、输入版本、验收、所有者及汇合规则。默认 Orchestrator 纯调度，Worker 执行，Reviewer 独立验证，Integrator 按需整合。
3. **先画图**：架构图表示控制权、角色、状态/产物与审批；流程图表示依赖、并行汇合、门禁与异常出口。小项目可合图。排除无主任务/资源和无出口失败后再生成框架。重大权限/成本/架构选择询问用户，其余记录假设继续。
4. 生成工作包、角色、机器定义、运行适配、门禁和恢复规则。定义落地后生成依赖图，人工补充业务异常；核对图、配置与角色一致。保留现有 AGENTS.md。
5. 核查实际启动、等待、消息、取消、句柄与隔离能力；未知标 unsupported/unverified。不假造 API，提示词边界不能声明强隔离。
6. 模拟串行、并行、修复、重复/晚到结果、输入失效、超时、取消、重启、审批和预算停止。真实适配器试跑单独授权与记录。
7. 交付入口、图、协议和证据；分别报告结构、模拟、真实平台验证，列明未验证项。

## 不变量

- Orchestrator 唯一拥有调度、计划与状态写入权。Worker 不自行派发，不改全局状态；Reviewer 不改实现。兼任角色必须声明 scope。
- 派发绑定 run_id、task_id、dispatch_id、attempt、输入版本；交接检查结构、语义、质量。上游更新使相关下游失效，不继续使用旧 PASS。
- 共享资源单所有者。超时/取消不等于已停止；未确认停止或隔离前保留资源，禁止冲突重派。
- 执行重试、质量修复、恢复接管、计划修订分别处理，均受总预算约束。权限拒绝和预算耗尽不重试，不降低门禁。
- 外部结果未知先核对；幂等键绑定业务操作，不随尝试变化。Checkpoint 不撤销外部副作用；不可逆动作需当前版本审批。
- 只保存可核查操作、决定与证据，不保存隐式思考、秘密或不必要敏感数据。报告不盲信 PASS，事件发生后才记录。
- 提示词不保证会话结束后后台持续运行；平台缺少 cancel/resume 时明确降级与停止条件。

## 工具

Python 标准库，无网络/模型调用。辅助工具不是生产调度服务或沙箱。

```text
python <skill目录>/scripts/validate_framework.py <工作包目录>
python <skill目录>/scripts/render_workflow.py <工作包目录>
python <skill目录>/scripts/simulate_framework.py --output <不存在的演练目录>
python <skill目录>/scripts/migrate_v1.py <旧工作包> --output <不存在的新目录>
```

检查器保留 v1 读取，不静默升级。v2 破坏性变更需另存、核对、重新验收。模拟不能证明真实 Agent、业务正确性、OS 隔离、审批身份或外部幂等性。
