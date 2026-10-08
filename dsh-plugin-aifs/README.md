# AIFS DSH 插件

TypeScript 插件负责注册十个工具，通过 HTTP 调用 Python 后端，并管理桌面后端的启动、退出和状态页。不运行 REST。用户安装见 [仓库 README](../README.md)。

## 工具与 HTTP

| 工具 | 后端接口 |
| --- | --- |
| `generate_rest_input` | `POST /v1/rest-inputs/prepare` |
| `validate_rest_input` | `POST /v1/rest-inputs/validate` |
| `retrieve_functional_evidence` | `POST /v1/evidence/search` |
| `get_rest_capabilities` | `GET /v1/rest-capabilities` |
| `create_aifs_plan` | `POST /v1/plans` |
| `revise_aifs_plan` | `PUT /v1/plans/{plan_id}` |
| `list_aifs_plans` | `GET /v1/plans` |
| `get_aifs_plan` | `GET /v1/plans/{plan_id}` |
| `generate_aifs_task_card` | `POST /v1/plans/{plan_id}/tasks/{task_id}/cards` |
| `get_aifs_card` | `GET /v1/plans/{plan_id}/cards/{card_id}` |

独立计算直接生成并校验；多步由模型首次提交完整任务图，后续用 patch。create/revise/get 默认向模型返回摘要；`get_aifs_plan` 的 `task_id` 读取单任务详情，`view=full` 读取完整内容。原 HTTP 完整响应保持兼容。

出卡返回 `export_relative_path`，模型用 DSH 文件工具把原文写到工作区的该路径。路径由后端确定，按计算、计划和任务分目录；已有文件内容不同时提示冲突。后端不访问用户工作区。

字段合并和结果失效规则见 [后端修订接口](../backend/README.md#局部修订计划)。旧卡能否继续用看 `is_applicable_to_current_plan`，不是只看生成版本。

## 插件与服务

- Cordis 导出：`name`、`inject`、`Config`、`apply`，没有 default export。
- 注入 `tools` 和 `systemPrompt`；通过 `ctx.tools.register` 注册，通过 `ctx.effect` 清理。
- 桌面包默认 `managed`：启用即注册工具，附带后端使用随机本机端口。调用等待服务启动；失败保留工具并报错，状态页可重试。
- 源码默认 `external`，保留旧开发接口；默认地址 `http://127.0.0.1:8000`。普通桌面用户不用此模式。
- 默认请求超时 30000 ms，最大响应 1048576 字节；取消信号传到 HTTP 请求。
- 模型设置和 API Key 由 DSH 管理，插件不改提供商配置。

| 文件 | 用途 |
| --- | --- |
| `src/index.ts` | 注册工具、系统提示、服务生命周期 |
| `src/tools.ts`、`client.ts` | 工具输入输出与 HTTP 客户端 |
| `src/generated/backend.ts` | Python 模型生成的字段结构，不手改 |
| `src/plan-schema.ts`、`schema-descriptions.ts` | 结构装饰与面向模型的说明 |
| `src/desktop/runtime.ts` | 启动后端，检查摘要、ready 消息和服务版本 |
| `src/desktop/skill.ts` | 注册包内 Skill |
| `src/desktop/routes.ts`、`ui.ts` | 状态页与重试路由 |

## 错误处理

网络失败、超时、响应超限、非 JSON、5xx 和 `request_validation_error` 抛工具错误。已知领域失败、计划不存在、版本冲突返回结构化错误；独立校验 `valid=false` 是正常返回。

DSH 先解析模型 JSON，插件收到有效参数才调用后端。损坏的模型 JSON 不由本插件修复。来源字段也是模型提交，不能独立证明用户确认或文献已核验。

## 开发检查

在本目录执行：

```bash
npm ci
npm test
npm run typecheck
```

接口字段从 Python 生成，修改后按 [契约命令](../scripts/README.md#接口与任务维护) 更新并提交生成文件。

单元测试使用 `src/vendor/*.d.ts` 类型声明和 `tests/fixtures/` 替身，不进入运行包。实际产物导入和 DSH 服务由 `verify-desktop-import.mjs`、`verify-desktop-host.mjs` 检查。UI 使用 DSH 通用工具卡；没有自定义 `presentCall`／`presentResult`。打包与真实对话验收见 [脚本文档](../scripts/README.md) 和 [验收表](../packaging/local-acceptance.md)。
