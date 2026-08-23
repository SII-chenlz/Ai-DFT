# AIFS Backend

该目录是新的 Python 3.11+ FastAPI 领域后端，负责需求数据模型、REST 方法目录、TOML renderer、独立 validator、推荐约束以及未来 EvidenceProvider/CalculationExecutor。

当前禁止把 Harness 会话循环、Web UI 或 TypeScript 插件逻辑写入此目录。旧原型位于 `../prototype-v0/`，只能作为只读参考。
