# AIFS DeepSeek Harness Plugin

Cordis 函数插件，向 `ctx.tools` 注册工具，通过 HTTP 调用 `../backend/`：

| 工具 | HTTP | 领域失败 | 基础设施失败 |
|---|---|---|---|
| `generate_rest_input` | `POST /v1/rest-inputs` | 结构化 `{ ok: false, error: { code, message } }` | 抛出工具错误 |
| `validate_rest_input` | `POST /v1/rest-inputs/validate` | `valid=false` 是 200 结构化结果 | 抛出工具错误 |
| `retrieve_functional_evidence` | `POST /v1/evidence/search` | 返回带 DOI/页码的证据包 | 抛出工具错误 |
| `get_rest_capabilities` | `GET /v1/rest-capabilities` | 查询输入覆盖、方法、区块字段与单位 | 抛出工具错误 |
| `create_aifs_plan` / `revise_aifs_plan` | `POST /v1/plans` / `PUT /v1/plans/{id}` | 返回后端校验错误 | 抛出工具错误 |
| `list_aifs_plans` / `get_aifs_plan` | `GET /v1/plans` / `GET /v1/plans/{id}` | 未找到计划返回结构化错误 | 抛出工具错误 |
| `generate_aifs_task_card` / `get_aifs_card` | 任务出卡 / 已存卡读取 | 缺输入或不支持时返回阻碍原因 | 抛出工具错误 |

插件不实现硬规则泛函推荐或 REST 计算执行。对每项计算任务的方法决策，AIFS 提示词先引导模型用 DSH 的 `web_search` 找来源，再用 `web_fetch` 阅读要引用的网页；`retrieve_functional_evidence` 补充本地已导入的记录。计划把网页引用保存为未整理的 `web` 证据，带 URL、标题、具体说明与 `claim_type`，并保留相反证据及不确定性。网页检索不会自动写入本地证据库；两个 DSH 网页工具也不是本插件自行实现的。

## 契约

- 导出 Cordis 函数插件契约 `name` / `inject` / `Config` / `apply`，无 default export。
- `inject: ['tools', 'systemPrompt']`；`apply` 用 `ctx.tools.register(defineTool(...))` 注册工具，并注册稳定的 AIFS 工作流提示词；所有 disposer 都收进 `ctx.effect`，上下文销毁时注销。
- 工具只接受声明字段，不接受任意 TOML 片段；`exec.signal` 传递给 HTTP 请求（与超时信号融合）。
- managed 模式启用时即注册十个工具，启动或故障不撤销工具目录。每次调用解析所属后端的当前地址；启动等待受请求超时/取消约束，失败返回原因，不回退到 external 地址或自动反复启动。重试由状态页触发。
- `Config`（均为显式配置）：`baseUrl`（默认 `http://127.0.0.1:8000`）、`requestTimeoutMs`（默认 30000）、`maxResponseBytes`（默认 1048576）；非法配置在加载时直接抛错（fail loud）。
- 错误分类：网络失败、超时、响应超限、非 JSON、5xx 以及 422 `request_validation_error`（插件/后端 Schema 不一致）一律抛错；只有后端 422 领域错误信封（`generate`）与 200 `valid=false`（`validate`）是结构化结果。

## 开发与测试（独立目录）

本目录在 deepseek-harness workspace 之外独立开发。单元测试使用隔离的类型声明和测试替身；桌面构建使用真实包的辅助模块：

- `src/vendor/*.d.ts`：`@deepseek-ai/cordis` / `@deepseek-ai/dsh-tools` / `@deepseek-ai/schemastery` 所用 API 子集的类型声明（仅类型）。
- `tests/fixtures/schemastery.ts`：仅用于单元测试的 Config 解析替身，通过 vitest alias 使用，不进入分发包。
- `tests/fixtures/dsh-tools.ts`：`defineTool` 测试替身，把声明 Schema 编译为 JSON Schema 并校验参数与规范输出值（与真实 registry 行为一致），使 Schema 测试真实可执行。

```bash
npm ci
npm test          # 版本/依赖锁检查、构建检查用例、插件测试
npm run typecheck # tsc --noEmit
```

`src/vendor/*.d.ts` 当前仍被类型检查使用。分发兼容性由 `verify-desktop-import.mjs` 和 `verify-desktop-host.mjs` 使用真实产物及 DSH 服务检查，不能用测试替身本身的断言证明官方兼容。

## 已知限制

- 结构契约及核心枚举从 Python 自动生成；只在 `schema-descriptions.ts` 单独维护模型说明。高级参数用 `rest_options` 传递，由后端契约校验；模型先用 `get_rest_capabilities` 查询具体区块。来源提交与接入范围见 [REST 能力范围](../packaging/rest-coverage.md)。
- REST 计算执行仍未实现；证据图谱与检索通过后端 `POST /v1/evidence/search` 提供。
- 未注册 `presentCall`/`presentResult`，UI 使用 generic 卡片渲染。

## 作为 Harness bundle 安装

插件现在声明了 `dsh.bundle`，可以从 AIFS 独立仓库安装到 Web profile：

```bash
cd ../deepseek-harness
export DSH_HOME=/path/to/aifs/.dsh-home
pnpm dsh plugin --profile web add /path/to/aifs/dsh-plugin-aifs
```

bundle patch 会自动插入 `aifs` 工具行；后端地址可通过 `AIFS_BACKEND_URL` 覆盖，默认是 `http://127.0.0.1:8000`。插件不改模型提供商、协议、地址或凭据；DSH 按所选模型解析这些配置，支持官方与自定义路由并存。所选模型需支持工具调用。此命令是旧 Web 开发入口；桌面用户按仓库 README 添加 `.tgz`，不需要符号链接。

## 桌面托管模式

桌面压缩包的 bundle 默认 `backendMode=managed`；插件源代码默认 external 以兼容原 Web 开发。managed 使用 DSH `subprocess` 服务，验证附带运行包摘要、ready 消息及 `/health` 的服务版本，；十个工具在启用时即注册，调用等待所属服务或返回明确失败原因。数据默认 `$DSH_HOME/aifs/`；子进程使用随机回环端口，启停由插件生命周期负责。故障不自动循环拉起，需状态页点击重试。

`src/desktop/runtime.ts` 管理进程，`skill.ts` 注册包内 Skill，`routes.ts` 使用 DSH 已认证的 `/api/aifs/status` 和 POST `/api/aifs/retry`，`ui.ts` 在插件页注册状态页面。外部模式保留 `baseUrl`，状态页面会注明服务尚待调用检查。Skill 随桌面包放进 `assets/skills/`，不依赖手工符号链接。

macOS arm64 调试包的构建与人工验收见仓库 `packaging/`。DSH 内部接口参考本地 `0.2.1-alpha.1` checkout；真实客户端安装兼容性仍需记录，不宣称所有 DSH 版本可用。

## 模型可见的单位与计划契约

`src/plan-schema.ts` 为 create/revise 工具声明完整的嵌套 PlanDraft 字段和枚举。后端仍负责条件检查、依赖与状态判定。模型无需在用户工作区寻找 Python 源码。规划 Skill 提供可验证的优化后单点能完整示例。

坐标单位在 `inputs.position_unit` 保存为 `angstrom|bohr`，出卡时对应 `[geom] unit`。未知单位阻止任务出卡；优化结果也要确认单位。插件提示词提前给出核实日期和规则，文献检索继续用于方法证据。历史卡 `position_unit_status=not_recorded` 时需说明单位未记录，并通过计划修订生成新卡。

## 接口同步

`src/generated/backend.ts` 来自 Python 模型；`src/plan-schema.ts` 装饰生成计划结构，`schema-descriptions.ts` 只加说明。参数和客户端响应类型使用生成结构及 SDK `InferValue`，不要重新手列 Python 字段。运行 `python -m aifs.contracts --write` 后提交生成文件；`npm test` 和打包会检查源码／产物摘要，CI 再用 Python 完整重生成比较。命令见 [脚本文档](../scripts/README.md#接口与任务维护)。
