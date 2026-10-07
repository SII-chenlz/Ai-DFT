# AIFS Backend

Python FastAPI 领域后端，负责 REST 量子化学软件的输入卡领域核心：

- REST 方法/基组/色散/关键词目录（版本化数据）；
- 结构化请求 → REST TOML 输入卡渲染；
- 与渲染器完全独立的 TOML 输入卡校验器；
- 健康检查与 REST 输入 API。
- Record-Builder 文献记录导入、轻量关系边和来源可追溯检索；当前不是完整的科研知识图谱。
- 独立 SQLite 工作流库：版本化任务计划、方法决策、输入卡与下载。

本目录不包含 Harness 会话循环、Web UI、TypeScript 插件、推荐算法、RAG 或计算执行器。

## 环境与安装

- 推荐 Python >= 3.11（`tomllib` 为标准库）；3.10 通过 `tomli` 兼容包运行（`pyproject.toml` 中按版本条件安装）。
- 安装：`python -m pip install -e './backend[dev]'`（开发依赖包含 pytest、httpx、ruff、mypy）。
- 需要本地语义向量时安装：`python -m pip install -e './backend[retrieval]'`，并配置 `AIFS_EMBEDDING_MODEL`。
- 配置：`AIFS_BASIS_SET_POOL` 环境变量（或 `.env`，见 `.env.example`）指向部署的 REST 基组池根目录。渲染输入卡必须配置；未配置时 `/v1/rest-inputs` 返回 500 基础设施错误。

## 运行与测试

```bash
pytest backend/tests -q          # 单元/接口测试
python -m ruff check backend     # 静态风格检查
python -m mypy backend/src       # 类型检查（在 backend/ 目录内运行时使用严格配置）
uvicorn aifs.api:app             # 启动 API（默认 127.0.0.1:8000）
```

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 服务状态与实际 AIFS 版本 |
| GET | `/v1/rest-capabilities` | 当前输入契约、方法与剩余项；`?section=thermo` 等查询字段类型与单位 |
| POST | `/v1/rest-inputs` | 渲染 REST TOML 输入卡；领域设置不兼容返回 422 与稳定 JSON 错误；部署未配置基组池返回 500（`configuration_error`） |
| POST | `/v1/rest-inputs/validate` | 独立校验完整输入卡；`valid=false` 是 200 领域结果 |
| POST | `/v1/evidence/import` | 导入 Record-Builder JSON/JSONL 到 SQLite 证据库 |
| POST | `/v1/evidence/search` | 按体系和任务召回带 DOI/页码的文献证据 |
| POST / GET | `/v1/plans` | 创建计划 / 列出已保存计划 |
| GET / PUT | `/v1/plans/{plan_id}` | 读取指定版本（省略 `version` 为最新）/ 带 `expected_version` 修订 |
| POST | `/v1/plans/{plan_id}/tasks/{task_id}/cards` | 对最新版本中已满足条件的 REST 任务生成、校验并保存卡片 |
| GET | `/v1/plans/{plan_id}/cards/{card_id}` | 读取历史卡片及其来源版本 |
| GET | `/v1/plans/{plan_id}/cards/{card_id}/download` | 下载 `.in` 文件 |

方法比较由 DSH 中的模型进行，后端保存决策及其证据。

计划库路径由 `AIFS_WORKFLOW_DB` 配置，默认 `data/aifs-workflow.sqlite3`，与 `AIFS_EVIDENCE_DB` 分开。计划状态由后端计算，草案不得提交 `status`；缺坐标、电荷、自旋、方法决策或优化结果时不会生成正式卡。每次修订保存完整新版本，旧卡保持绑定到原版本。文献决策可引用已导入的 `record_id`，也可引用带 URL 和标题的网页来源。引用可用 `claim_type=method_used|comparative_benchmark|author_recommendation|other` 区分证据性质；旧计划未填该字段仍可读取。网页引用仅保存来源，不自动导入本地知识图谱，仍需研究者核对。仅有“论文使用某方法”时，后端在决策不确定性中提示不能证明相对优选。

## 文献证据检索

配置 `AIFS_EVIDENCE_DB`（默认 `data/aifs-evidence.sqlite3`），然后导入 Record-Builder 的最终 `records.jsonl`：

```bash
python -m aifs.evidence_cli import --input /path/to/records.jsonl
python -m aifs.evidence_cli search \
  --system "open-shell nickel cluster" \
  --calculation "spin-state ordering"
```

数据库保存原始 record、evidence quote 和关系边；不复制 PDF 或 MinerU 中间产物。默认检索模式是 SQLite FTS5，API 会返回 `retrieval_mode=lexical_fallback`。设置 `AIFS_EMBEDDING_MODEL=BAAI/bge-m3` 并安装 `backend[retrieval]` 后，FAISS 负责语义近邻、FTS5 做关键词补充，返回 `retrieval_mode=hybrid`；两种模式共用同一个 Harness 接口。

## REST 规则来源

基本目录来自官方 README，扩展输入按解析代码核对：

- 来源：https://gitee.com/restgroup/rest/blob/master/README.md
- 核对日期：2026-10-04；源码提交 `6fa7f3b0b6476fa533dfc38af8b8505730713ac6`。

范围与限制见 [REST 能力范围](../packaging/rest-coverage.md)。`RestInputRequest.rest_options` 和 `PlanTask.rest_options` 按区块保存额外设置，`MethodDecision.xc_parser` 保存方法解析路径。`capabilities.py` 声明字段类型、枚举、单位及组合条件；未知字段不算校验通过。新增高级设置同样经过计划状态检查、渲染、独立校验、版本保存和下载。

运行时校验不依赖网络。

## 关键行为

- 单卡 `/v1/rest-inputs` 保留目录中的默认基组：自洽场方法默认 `def2-TZVPP`，后自洽场方法默认 `def2-QZVPP`。任务计划出卡必须有明确的 `decision.basis`；仅选泛函、基组为 null 时等待基组决策，不自动套用默认值。方法与解析路径以 `/v1/rest-capabilities` 为准，LDA 等家族名称不能替代具体方法名。
- 经验色散仅允许 `d3`、`d3bj`、`d4`，通过独立的 `empirical_dispersion` 键输出；双杂化/RPA 类方法（XYG3、XYG7、XYGJOS、xDH-PBE0、sBGE2、ZRPS、scsRPA、R-xDH7、RPA@PBE、RPA@B3LYP）请求色散时返回结构化领域错误（code `empirical_dispersion_not_needed`），绝不静默删除。
- `spin == 1` 自动推导 `spin_polarization=false`；`spin > 1` 自动推导 `true`；推导结果记录在 `defaults_applied`。
- `num_threads` 缺省为 10；`basis_path` 由服务端配置 `AIFS_BASIS_SET_POOL` 与最终基组拼接，后端不硬编码本机路径。请求体没有 `basis_set_pool` 字段（传入即 422）；`basis` 只能是池根目录内的相对路径，绝对路径、盘符与 `.`/`..` 段被拒绝（422，code `basis_outside_pool`）。
- `position` 使用 TOML 三双引号多行字符串输出；渲染器不接受任意 TOML 键值片段。
- 校验器独立于渲染器：TOML 语法、`[ctrl]`/`[geom]` 存在性、必需字段、字段位置、伪造关键词（`method`/`coord`/`molecule`）、目录成员、数值范围、有限电荷、自旋一致性、色散兼容与坐标格式。未收录的 section 和 keyword 会报告目录缺口并拒绝通过；错误按固定顺序返回，TOML 无法解析时只返回语法错误。

## 已知限制

- REST 官方 README 未明确 MP2 是否允许经验色散：当前仅对双杂化/RPA 类方法禁止色散，MP2 + 色散被允许（目录与测试中固化此决定）。
- `[geom] unit` 接受 `angstrom|bohr`，省略时提示单位未记录。
- 校验器不检查 `basis_path` 是否真实存在于部署文件系统（输入卡校验与部署环境检查分离）。
- 桌面构建使用 Python 3.11；输入契约检查没有执行 REST，不证明数值精度、梯度完整性或计算收敛。

## 桌面后端

`aifs.desktop_launcher` 先设置绝对数据路径，再绑定 `127.0.0.1:0`，等 Uvicorn 就绪后在 stdout 输出一条 JSON ready 记录（实际 baseUrl、service、version）。日志在数据目录，父进程 stdin 管道 EOF 会请求退出。SQLite 工作流与证据库分别保存，基础包关闭语义模型加载。

`aifs.migrate_desktop` 提供显式 SQLite 迁移：先用 SQLite backup 生成快照再复制，保留源文件并拒绝覆盖。冻结可执行文件同样支持 `migrate --source ... --destination ...`。请先停止使用相关库的 AIFS 服务。

后端完整测试包含 FAISS 持久化测试，安装 `.[dev,retrieval-test]` 后运行。`retrieval-test` 只提供测试所需 FAISS 与 numpy，不要求下载 sentence-transformers 模型；桌面运行包不依赖这组组件。

## 坐标单位与历史兼容（2026-10-03）

- REST `[geom] unit` 支持 `angstrom` 和 `bohr`，来源为上述官方 README 的 geom 章节，单独核对日期见 `GEOMETRY_SOURCE_READ_DATE`。
- `TaskInputs.position_unit` 可为 null，以便先保存不完整计划；null 阻止出卡。优化结果必须带结果自身的单位。
- 新生成卡显式写入 `unit`，请求快照、有效参数和计划都保存该单位；坐标数字不换算。卡片生成元数据记录单位规则来源日期与 URL。
- `RestInputRequest.position_unit` 接受 `angstrom|bohr`。旧单卡调用省略时使用 AIFS 的 Angstrom 默认值，并在 `defaults_applied` 和 `warnings` 中报告；模型应主动提交已确认单位。
- 独立校验拒绝非法单位及非字符串单位。旧卡省略 unit 时保持格式兼容，但给出 `unit_not_recorded` 警告，不宣称物理单位已确认。
- 历史卡读取增加 `position_unit` / `position_unit_status`，直接依据原卡正文；原正文、摘要、下载及版本关联不变。旧计划不补默认单位，不修改数据库历史。

## 数据结构与历史兼容

`workflow_schema.py` 是工作流库升级与快照读取的统一入口；结构版本记录在 SQLite `user_version`，每条 `plan_versions` 记录另有快照 `schema_version`，均独立于用户修订号和软件版本。首次打开已识别的旧库时先用 SQLite backup 保留 WAL 中已提交的数据到 `schema-backups/`，再事务补充版本；失败回滚并保留备份。

历史 JSON、任务 ID、卡片正文和摘要不重写。旧空基组读取为未知，缺单位仍未知；不能自动变成已确认参数。新修订按当前格式保存。未来结构或快照格式返回明确的 409 错误，并阻止写入；写入门槛在事务内检查。`migrate` 只负责数据库搬家，结构升级在打开库时执行，两者不合并历史记录。

## 生成接口契约

`contracts.py` 从 Python 请求／响应模型导出版本化 `contracts/backend-schema.json`，生成插件 `src/generated/backend.ts`。运行 `python -m aifs.contracts --write` 更新，`--check` 只检查。插件描述单独维护，科学范围和 REST 组合仍在后端执行。详细开发命令见 [脚本文档](../scripts/README.md#接口与任务维护)。
