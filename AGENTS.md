# AIFS Agent Instructions

本文件适用于 AIFS 独立仓库。`../deepseek-harness/` 是同级的官方上游仓库，其内部 `AGENTS.md` 仅在明确获准修改上游时适用。

## 必读资料

开始实现前依次阅读：

1. `../AIFS-DeepSeek-Harness-开发规划.md`
2. `../DeepSeek-Harness-开发方式与AIFS产品化路线.md`
3. `../AIFS-DeepSeek-Harness-完整架构规格.md`
4. 当前任务文件

## 目录所有权

- `backend/`：Python/FastAPI 领域后端。
- `dsh-plugin-aifs/`：TypeScript Harness 适配插件。
- `profiles/`：AIFS profile 和 patch。
- `scripts/`：启动、验证和运维脚本。
- `tasks/`：交接任务，不放运行时代码。
- `prototype-v0/`：旧原型，只读参考。
- `../deepseek-harness/`：同级的官方上游 Git 仓库，默认禁止修改。

## 强制规则

- 只修改当前任务明确允许的文件。
- 不修改、移动、删除或提交 `../deepseek-harness/` 中的文件。
- 不修改 `prototype-v0/`；复用逻辑时在新目录重新实现并测试。
- 不提交 API key、访问令牌、真实服务器地址或用户数据。
- 不伪造文献、Benchmark 数值、REST 关键词或计算结果。
- 优先写失败测试，再写最小实现。
- 每个跨进程接口使用结构化 JSON 和显式 Schema。
- REST 输入卡声称可用前必须通过独立 validator。
- 没有知识图谱证据时使用 `model_only` 或 `rule_supported`，不能使用 `retrieved`。
- 每项任务完成后提交 Git commit，保持工作区干净。

## 交接格式

最终回答必须包含：

- commit hash 和标题；
- 修改文件清单；
- 实际运行的测试/检查命令；
- 每条命令的结果；
- 已知限制；
- 建议由 Codex 复核的风险点。
