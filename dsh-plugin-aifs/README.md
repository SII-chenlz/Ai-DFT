# AIFS DeepSeek Harness Plugin

Cordis 函数插件，向 `ctx.tools` 注册两个工具，通过 HTTP 调用 `../backend/`：

| 工具 | HTTP | 领域失败 | 基础设施失败 |
|---|---|---|---|
| `generate_rest_input` | `POST /v1/rest-inputs` | 结构化 `{ ok: false, error: { code, message } }` | 抛出工具错误 |
| `validate_rest_input` | `POST /v1/rest-inputs/validate` | `valid=false` 是 200 结构化结果 | 抛出工具错误 |

插件不实现泛函推荐、知识图谱、RAG 或 REST 计算执行（`recommend_rest_strategy` 由后续任务注册）。

## 契约

- 导出 Cordis 函数插件契约 `name` / `inject` / `Config` / `apply`，无 default export。
- `inject: ['tools', 'systemPrompt']`；`apply` 用 `ctx.tools.register(defineTool(...))` 注册工具，并注册稳定的 AIFS 工作流提示词；所有 disposer 都收进 `ctx.effect`，上下文销毁时注销。
- 工具只接受声明字段，不接受任意 TOML 片段；`exec.signal` 传递给 HTTP 请求（与超时信号融合）。
- `Config`（均为显式配置）：`baseUrl`（默认 `http://127.0.0.1:8000`）、`requestTimeoutMs`（默认 30000）、`maxResponseBytes`（默认 1048576）；非法配置在加载时直接抛错（fail loud）。
- 错误分类：网络失败、超时、响应超限、非 JSON、5xx 以及 422 `request_validation_error`（插件/后端 Schema 不一致）一律抛错；只有后端 422 领域错误信封（`generate`）与 200 `valid=false`（`validate`）是结构化结果。

## 开发与测试（独立目录）

本目录在 deepseek-harness workspace 之外独立开发，harness 包在这里不可安装，因此：

- `src/vendor/*.d.ts`：`@deepseek-ai/cordis` / `@deepseek-ai/dsh-tools` / `@deepseek-ai/schemastery` 所用 API 子集的类型声明（仅类型）。
- `src/vendor/z.ts`：最小 schemastery 运行时子集，测试通过 vitest alias 使用。
- `tests/fixtures/dsh-tools.ts`：`defineTool` 测试替身，把声明 Schema 编译为 JSON Schema 并校验参数与规范输出值（与真实 registry 行为一致），使 Schema 测试真实可执行。

```bash
npm install
npm test          # vitest：插件契约 / Schema / HTTP / 注销
npm run typecheck # tsc --noEmit
```

挂载进 harness workspace 后，`peerDependencies` 声明的真实包直接解析，vendor 声明与 `z.ts` 可删除，源码无需改动。

## 已知限制

- 工具参数里的 REST 目录（`job_type`、`empirical_dispersion`、`outputs`）是后端 `aifs.rest.catalogs` 的手动镜像（2026-08-23 读取），OpenAPI 生成类型落地前需手动同步。
- `recommend_rest_strategy`、知识图谱证据、RAG 与 REST 计算执行均未实现（刻意不在本任务范围）。
- 未注册 `presentCall`/`presentResult`，UI 使用 generic 卡片渲染。

## 作为 Harness bundle 安装

插件现在声明了 `dsh.bundle`，可以从 AIFS 独立仓库安装到 Web profile：

```bash
cd ../deepseek-harness
export DSH_HOME=/path/to/aifs/.dsh-home
pnpm dsh plugin --profile web add /path/to/aifs/dsh-plugin-aifs
```

bundle patch 会自动插入 `aifs` 工具行；后端地址可通过 `AIFS_BACKEND_URL` 覆盖，默认是 `http://127.0.0.1:8000`。模型密钥仍由 Harness 的 `DEEPSEEK_API_KEY` 环境变量读取。
