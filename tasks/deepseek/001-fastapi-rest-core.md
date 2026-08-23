# DeepSeek 任务 001：FastAPI 与 REST 输入卡核心

## 你的角色

你是 AIFS 项目的实现工程师。本任务只建设语言无关的领域后端基础，不开发 Agent、Harness 插件、推荐排序、RAG 或计算执行器。

开始前完整阅读：

1. `/Users/chenlz/Sii/code/202608/harness/AIFS/AGENTS.md`
2. `/Users/chenlz/Sii/code/202608/harness/AIFS-DeepSeek-Harness-开发规划.md`
3. `/Users/chenlz/Sii/code/202608/harness/AIFS-DeepSeek-Harness-完整架构规格.md`
4. REST 官方说明：https://gitee.com/restgroup/rest/blob/master/README.md

工作目录：

```text
/Users/chenlz/Sii/code/202608/harness/AIFS
```

## Git 要求

开始前确认：

```bash
git status --short
git -C ../deepseek-harness status --short
```

两条命令都必须无输出。然后创建分支：

```bash
git switch -c deepseek/fastapi-rest-core
```

不得在 `main` 直接开发。

## 允许修改

```text
backend/**
tasks/deepseek/001-fastapi-rest-core.md   # 只允许勾选进度或记录实测结果
```

## 禁止修改

```text
../deepseek-harness/**
prototype-v0/**
dsh-plugin-aifs/**
profiles/**
scripts/**
../AIFS-DeepSeek-Harness-开发规划.md
../DeepSeek-Harness-开发方式与AIFS产品化路线.md
../AIFS-DeepSeek-Harness-完整架构规格.md
README.md
AGENTS.md
.gitignore
```

禁止安装或写入全局依赖。禁止提交 `.env`、API key、缓存、虚拟环境或构建产物。

## 任务目标

交付一个可以独立运行和测试的 FastAPI 后端核心，支持：

1. 健康检查；
2. 结构化 REST 输入卡请求；
3. REST TOML 输入卡生成；
4. 独立 REST/TOML 校验；
5. 方法、基组、色散和关键词目录；
6. 明确区分领域校验失败和基础设施失败。

本任务不调用 DeepSeek API，不推荐哪个泛函最好。

## 技术栈

- Python `>=3.11`
- FastAPI
- Pydantic v2
- pydantic-settings
- pytest
- FastAPI TestClient/httpx
- ruff
- mypy
- Python 标准库 `tomllib` 用于独立解析校验

## 必须创建的结构

```text
backend/
├── .env.example
├── pyproject.toml
├── README.md
├── src/aifs/
│   ├── __init__.py
│   ├── api.py
│   ├── config.py
│   ├── models.py
│   └── rest/
│       ├── __init__.py
│       ├── catalogs.py
│       ├── renderer.py
│       └── validator.py
└── tests/
    ├── test_api.py
    ├── test_models.py
    ├── test_renderer.py
    └── test_validator.py
```

可以增加职责单一的 JSON 数据文件，但不要创建空壳 service、repository 或 provider。

## 数据模型

在 `backend/src/aifs/models.py` 中实现并禁止额外字段：

### `RestInputRequest`

- `system_name: str`：去除首尾空格后非空，最长 120 字符。
- `position: str`：XYZ 风格多行文本，去除首尾空白后非空，最大 200,000 字符。
- `job_type: Literal["energy", "opt", "force", "numerical dipole"]`。
- `xc: str`：必须由方法目录规范化和校验。
- `basis: str | None`：空值时按方法类别选择默认值。
- `basis_set_pool: str`：部署配置传入的基组根路径，非空。
- `charge: float = 0.0`。
- `spin: int = 1`：必须大于等于 1。
- `spin_polarization: bool | None = None`：空值时由 `spin` 推导。
- `empirical_dispersion: Literal["d3", "d3bj", "d4"] | None = None`。
- `print_level: int = 1`：必须大于等于 0。
- `num_threads: int = 10`：必须大于等于 1。
- `outputs: list[str] = []`：只允许 REST 官方支持的输出项子集。

### `RestInputResponse`

- `rest_input: str`
- `effective_settings: dict[str, object]`
- `defaults_applied: list[str]`
- `warnings: list[str]`

### `ValidationIssue`

- `code: str`
- `message: str`
- `section: str | None`
- `field: str | None`
- `line: int | None`

### `ValidateInputRequest`

- `rest_input: str`：非空，最大 500,000 字符。

### `ValidateInputResponse`

- `valid: bool`
- `errors: list[ValidationIssue]`
- `warnings: list[ValidationIssue]`
- `parsed_sections: list[str]`

## REST 方法目录

目录至少覆盖 REST README 中以下方法类别，并对大小写进行规范化：

### 自洽场方法，默认基组 `def2-TZVPP`

```text
HF, LDA, BLYP, PBE, xPBE, XLYP, SCAN, M06-L, MN15-L, TPSS,
B3LYP, X3LYP, PBE0, M05, M05-2X, M06, M06-2X, SCAN0, MN15
```

### 后自洽场方法，默认基组 `def2-QZVPP`

```text
MP2, XYG3, XYGJOS, XYG7, xDH-PBE0, sBGE2, ZRPS, scsRPA,
R-xDH7, RPA@PBE, RPA@B3LYP
```

经验色散只允许 `D3`、`D3BJ`、`D4`。对 REST README 明确不需要经验色散的双杂化/RPA 类方法，若请求包含 `empirical_dispersion`，必须返回结构化领域错误，不能静默删除。

目录必须记录来源 URL 和读取日期 `2026-08-23`，但运行时错误信息不依赖网络。

## Renderer 行为

在 `backend/src/aifs/rest/renderer.py` 中提供：

```python
def render_rest_input(request: RestInputRequest) -> RestInputResponse:
    ...
```

生成结果必须：

- 是可由 `tomllib.loads` 解析的 TOML；
- 包含 `[ctrl]` 和 `[geom]`；
- 在 `[ctrl]` 中输出 `xc`、`basis_path`、`print_level`、`num_threads`、`job_type`、`charge`、`spin`、`spin_polarization`；
- 仅在用户要求时输出 `empirical_dispersion`；
- 仅在非空时输出 `outputs`；
- 在 `[geom]` 中使用 `name` 和 `position`；
- `position` 使用 TOML 三双引号多行字符串，不能使用三单引号；
- 对 TOML 字符串中的双引号和反斜杠进行正确处理；
- `basis_path` 使用 `basis_set_pool` 与最终基组拼接，不硬编码本机路径；
- 记录自动基组和自动 `spin_polarization` 到 `defaults_applied`；
- 保持稳定字段顺序，确保快照式断言可靠。

禁止接受或拼接任意用户提供的 TOML 键值片段。

## Validator 行为

在 `backend/src/aifs/rest/validator.py` 中提供：

```python
def validate_rest_input(rest_input: str) -> ValidateInputResponse:
    ...
```

必须独立于 renderer 执行以下检查：

- TOML 语法；
- `[ctrl]`、`[geom]` 必须存在；
- 必需字段必须存在；
- `spin`、`charge`、`spin_polarization` 不得出现在 `[geom]`；
- `position` 不得出现在 `[ctrl]`；
- 拒绝 `method`、`coord`、`molecule` 等伪造关键词；
- `xc` 必须属于方法目录；
- `job_type` 必须属于允许值；
- `basis_path` 必须是非空字符串；
- `spin >= 1`、`num_threads >= 1`、`print_level >= 0`；
- `spin == 1` 且未显式要求 ROHF 时，`spin_polarization` 应为 `false`；
- `spin > 1` 默认 `spin_polarization` 应为 `true`，显式 `false` 时给出 ROHF 高自旋限制 warning；
- `empirical_dispersion` 只允许 `d3`、`d3bj`、`d4`；
- 禁止给不需要经验色散的双杂化/RPA 方法添加色散；
- `position` 至少包含一行形如 `Element x y z` 的坐标，坐标必须能转换为浮点数。

错误按稳定顺序返回。TOML 无法解析时，只返回语法错误，不继续伪造区块错误。

## FastAPI 接口

在 `backend/src/aifs/api.py` 中创建应用：

```python
app = FastAPI(title="AIFS API", version="0.1.0")
```

接口：

- `GET /health` 返回 `{"status": "ok", "service": "aifs-api", "version": "0.1.0"}`。
- `POST /v1/rest-inputs` 调用 renderer；成功返回 200；领域设置不兼容返回 422 和稳定 JSON 错误。
- `POST /v1/rest-inputs/validate` 调用独立 validator；即使 `valid=false` 也返回 200。

不要添加 `/v1/recommendations`；推荐器由后续任务实现。

## 测试要求

先写失败测试，再写实现。至少覆盖：

1. 健康接口；
2. Pydantic 拒绝额外字段；
3. `spin=0`、`num_threads=0`、空坐标被拒绝；
4. B3LYP 自动使用 `def2-TZVPP`；
5. XYG3 自动使用 `def2-QZVPP`；
6. D3BJ 输出为独立 `empirical_dispersion = "d3bj"`；
7. 双杂化/RPA 加色散被拒绝；
8. 生成卡可被 `tomllib` 解析；
9. 生成卡包含正确区块和字段位置；
10. 默认 `num_threads = 10`；
11. `spin=1` 自动得到 `spin_polarization=false`；
12. `spin>1` 自动得到 `spin_polarization=true`；
13. validator 拒绝缺失区块；
14. validator 拒绝 `method`、`coord`、`molecule`；
15. validator 拒绝错误字段位置；
16. validator 对 TOML 语法错误只返回语法问题；
17. validator 接受 renderer 生成的有效卡；
18. API 的领域验证失败和输入 Schema 失败均具有稳定 JSON。

测试不得访问网络或调用真实 DeepSeek API。

## 必须通过的命令

从 AIFS 根目录运行：

```bash
python -m pip install -e './backend[dev]'
pytest backend/tests -q
python -m ruff check backend
python -m mypy backend/src
python -m pytest prototype-v0/tests -q
git -C ../deepseek-harness status --short
```

最后两条用于证明没有破坏旧原型和上游仓库。

## 提交要求

实现过程中至少提交两个 commit：

```text
feat: scaffold AIFS FastAPI domain models
feat: add REST input renderer and validator
```

完成时 `git status --short` 必须无输出。

## 最终回复格式

请严格按以下结构回复：

```text
分支：
Commits：
实现内容：
修改文件：
测试命令与结果：
REST 规则来源：
已知限制：
需要 Codex 重点复核：
```

不要继续实现 Harness 插件或推荐算法。完成本任务后停止。
