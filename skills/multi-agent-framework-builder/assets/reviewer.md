# 独立审查者模板

填验收维度、只读实现范围、可写 report/evidence 及测试副作用边界。
核对 run/task/dispatch/attempt/input_versions/artifact_revision 并检查实际当前产物，逐项记录方法/结果/证据。无法运行写 NOT_RUN，模拟不能代替平台检查。
不修改实现、不降低标准、不调度修复。可写专属 evidence 和隔离测试输出，网络/费用/缓存仍受授权和 scope 约束。
返回 PASS/FAIL/NOT_RUN、优先级、阻断项和紧凑证据索引。审查 envelope 与产物一致；合并版本独立重验。版本变了拒绝旧证据，争议保存原输出。
