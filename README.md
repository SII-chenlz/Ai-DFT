# AIFS（AI 泛函智选引擎）

AIFS 是面向分子量子化学计算的对话式泛函推荐产品。当前 MVP 目标是打通：

```text
自然语言需求
→ DeepSeek Harness Agent
→ AIFS 工具
→ FastAPI
→ REST TOML 输入卡生成与校验
```

## 目录

```text
harness/                              # 普通容器目录，不是 Git 仓库
├── deepseek-harness/                  # 官方上游 Git 仓库
├── AIFS-DeepSeek-Harness-开发规划.md
├── DeepSeek-Harness-开发方式与AIFS产品化路线.md
├── AIFS-DeepSeek-Harness-完整架构规格.md
└── AIFS/                            # 本仓库：AIFS 独立产品
    ├── backend/                    # FastAPI 领域后端
    ├── dsh-plugin-aifs/            # Harness 工具插件
    ├── profiles/                   # AIFS Harness profile/patch
    ├── scripts/                    # 本地启动和检查脚本
    ├── tasks/deepseek/             # 交给 DeepSeek 的自包含任务
    └── prototype-v0/               # 只读保留的旧 VASP/QE 原型
```

## 当前开发边界

- 目标量化软件只有 REST。
- 第一阶段使用 DeepSeek Harness 自带 Web UI。
- 后端使用 Python 3.11+、FastAPI 和 Pydantic。
- Harness 通过独立 TypeScript 插件调用 FastAPI。
- 当前不实现知识图谱、文献 RAG、REST 计算执行或公网部署。
- 不修改同级目录 `../deepseek-harness/` 中的任何上游文件。

## 文档

1. [AIFS × DeepSeek Harness 开发规划](../AIFS-DeepSeek-Harness-开发规划.md)
2. [DeepSeek Harness 开发方式与 AIFS 产品化路线](../DeepSeek-Harness-开发方式与AIFS产品化路线.md)
3. [完整中文架构规格](../AIFS-DeepSeek-Harness-完整架构规格.md)

实施与交接材料：

- [DeepSeek 首批任务：FastAPI 与 REST 核心](tasks/deepseek/001-fastapi-rest-core.md)

## 开发顺序

1. DeepSeek 完成 `tasks/deepseek/001-fastapi-rest-core.md`。
2. Codex 审查 commit、接口、REST 规则和测试。
3. 审查通过后实现 AIFS Harness 插件和 Agent Prompt。
4. 端到端流程稳定后再接入知识图谱和计算执行器。

## 直接本地测试

复制 `.env.example` 为 `.env.local`，填写 `DEEPSEEK_API_KEY`，并按需要填写 `AIFS_BASIS_SET_POOL`。然后：

```bash
./scripts/check-local.sh       # 后端已启动时检查生成/校验链路
./scripts/start-local.sh       # 安装本地插件并启动 Harness Web
./scripts/verify-harness-mount.sh --require-installed
```

默认端口是 Harness `127.0.0.1:3080`、AIFS FastAPI `127.0.0.1:8000`。密钥只从环境变量读取，不能提交到 Git。

## 旧原型

`prototype-v0/` 是前期 VASP/QE 原型，仅作为 Pydantic、DeepSeek 客户端和测试风格参考。新代码不得继续扩展该目录。

验证旧原型：

```bash
pytest prototype-v0/tests -q
```
