# AIFS DeepSeek Harness Plugin

该目录保存独立 TypeScript/Cordis 插件。插件负责向 `ctx.tools` 注册模型工具，并通过 HTTP/OpenAPI 调用 `../backend/`。

插件不实现泛函推荐、REST 关键词规则、TOML 渲染或知识图谱检索。首批 DeepSeek 任务禁止修改该目录。
