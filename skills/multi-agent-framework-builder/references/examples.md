# 两种低风险模拟样例

运行 simulate_framework.py --output <不存在的目录>，得到可检查的真实模拟事件与证据。所有 Agent 由本地确定性函数替代，绝不把样例当真实多 Agent 或集成代码测试。

## 串行

T01 → T02 → T03 → 集成门禁 → 完成。每步消费显式前置版本并经过审查。求和任务计算 [2,2]，证据记录实际值 4。适用于起步时验证派发/交接/验收关联。

## 并行与整合

T01 与 T02 分别声明独立 scope，均 passed 后才派发 Integrator 的 T03。模拟同时保留两个任务资源，不启动两个真实进程；实际并发能力未测。合并代码正确性需要项目真实集成测试，样例只验证 all_required 调度语义。

生成 architecture.mmd、workflow.mmd、dependencies.mmd、workflow.json、模拟角色、输入、run/journal/report/evidence。样例角色文本只是标识，不是生产提示词。真实项目由 Agent 适配 assets 中模板并补 brief/runtime/quality-gates/recovery。

扩展到项目时优先选两个独立模块和一个集成任务，先确定接口，画图，再填真实输入版本/验收；不要机械沿用求和验收或固定三任务。静态 input_refs 改变需修订 workflow_revision，不在旧 run 上直接变更。
