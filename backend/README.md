# AIFS 后端

Python FastAPI 服务负责：

- 保存计划、方法选择、引用和历史输入卡。
- 检查参数、依赖及优化结构来源。
- 生成 REST TOML 输入，调用独立校验器检查。
- 导入和检索本地文献记录；目前不是完整知识图谱。

模型负责科学方案；后端不执行 REST，也不自动计算分析公式。

## 环境与安装

- 推荐 Python >= 3.11（`tomllib` 为标准库）；3.10 通过 `tomli` 兼容包运行（`pyproject.toml` 中按版本条件安装）。
- 安装：`python -m pip install -e './backend[dev]'`（开发依赖包含 pytest、httpx、ruff、mypy）。
- 需要本地语义向量时安装：`python -m pip install -e './backend[retrieval]'`，并配置 `AIFS_EMBEDDING_MODEL`。
- 配置：`AIFS_BASIS_SET_POOL` 环境变量（或 `.env`，见 `.env.example`）指向部署的 REST 基组池根目录。渲染输入卡必须配置；未配置时 `/v1/rest-inputs` 返回 500 基础设施错误。

## 运行与测试

在仓库根目录运行 `uvicorn aifs.api:app` 可单独调试 API。桌面包由插件启动后端。完整测试与打包命令见 [脚本文档](../scripts/README.md#更新版本与检查)。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 服务状态与实际 AIFS 版本 |
| GET | `/v1/rest-capabilities` | 当前输入契约、方法与剩余项；`?section=thermo` 等查询字段类型与单位 |
| POST | `/v1/rest-inputs` | 渲染 REST TOML 输入卡；领域设置不兼容返回 422 与稳定 JSON 错误；部署未配置基组池返回 500（`configuration_error`） |
| POST | `/v1/rest-inputs/prepare` | 独立计算直接出卡：显式科学参数，生成并独立校验，返回正文、文件名和校验结果；不创建计划 |
| POST | `/v1/rest-inputs/validate` | 独立校验完整输入卡；`valid=false` 是 200 领域结果 |
| POST | `/v1/evidence/import` | 导入 Record-Builder JSON/JSONL 到 SQLite 证据库 |
| POST | `/v1/evidence/search` | 按体系和任务召回带 DOI/页码的文献证据 |
| POST / GET | `/v1/plans` | 创建计划 / 列出已保存计划 |
| GET / PUT | `/v1/plans/{plan_id}` | 读取指定版本（省略 `version` 为最新）/ 带 `expected_version` 修订 |
| POST | `/v1/plans/{plan_id}/tasks/{task_id}/cards` | 对最新版本中已满足条件的 REST 任务生成、校验并保存卡片 |
| GET | `/v1/plans/{plan_id}/cards/{card_id}` | 读取历史卡片及其来源版本 |
| GET | `/v1/plans/{plan_id}/cards/{card_id}/download` | 下载 `.in` 文件 |

### 独立计算直接出卡，多步计算保存流程

`generate_rest_input` 工具使用 `/v1/rest-inputs/prepare`，必填 `system_name`、`position`、`position_unit`、`charge`、`spin`、`xc`、`job_type`、`basis`。坐标单位、电荷、自旋和基组不能省略或为 null；不再从默认值猜这些科学参数。解析器和高级选项仍按当前 REST 能力填写。

独立计算使用此入口；有前置结果或能量组合时先保存 `PlanDraft`，后续用 `patch`。用户要求时也可保存单步计算。

直接出卡、保存卡及卡片摘要返回 `export_relative_path`。路径在 `aifs-inputs/` 下：直接卡按文件名去掉后缀分目录，保存卡按 `plan-{plan_id}/task-{task_id}/` 分目录；文件名保留原样。它是工作区相对路径，后端不写用户工作区，由 DSH 文件工具导出。无需数据库升级；历史卡读取时也会返回路径。

后端生成后立即调用独立 TOML 校验器。校验失败返回 422 `card_validation_failed`，不返回成功卡片。成功返回 `rest_input`、安全的 `.in` 文件名 `filename` 和 `validation`，由 DSH 文件工具导出；不创建数据库记录或下载链接。单独校验工具仍用于用户已有或编辑过的卡片。旧 `/v1/rest-inputs` 只保留渲染 API 的兼容性，桌面模型默认不调用该旧入口。

`source=user` 等来源字段由模型填写，不能独立证明真实确认。输入检查不证明科学方案正确。

计划库由 `AIFS_WORKFLOW_DB` 指定，默认 `data/aifs-workflow.sqlite3`，证据库由 `AIFS_EVIDENCE_DB` 指定。状态由后端计算，不接受草案 `status`。计划可保存未知参数，但缺坐标、单位、电子态、方法或必需优化结构时不出卡。

每次修订保存完整快照，历史卡不改。引用支持本地 `record_id` 或网页 URL／标题；`claim_type` 区分方法使用、对比基准、作者推荐和其他证据。网页引用不自动导入本地库，“论文使用某方法”不证明它更准确。

### 局部修订计划

`PUT /v1/plans/{plan_id}` 可以只提交修改的字段。例如，为已存在的 `sp` 任务换基组：

```json
{
  "expected_version": 1,
  "change_reason": "用户确认新的基组",
  "patch": {"tasks": [{"task_id": "sp", "decision": {"basis": "def2-TZVPP"}}]}
}
```

- `patch.tasks` 按已有任务 ID 更新，不是替换整个任务列表。省略字段保留原值，明确填 `null` 才清空允许为空的字段。
- `inputs`、`decision` 按字段合并；其他列表和字典整项替换，包括 `depends_on`、证据列表和 `rest_options`。新建方法决策需要完整必填字段。
- `patch.add_tasks` 接收完整的新任务；`patch.remove_task_ids` 删除指定任务。重复或不存在的 ID、删除后留下无效依赖均拒绝。
- 原有 `plan` 完整替换方式继续可用。一次请求只能提供 `patch` 或 `plan` 之一，此条件由后端执行。
- 在同一写入事务中核对版本、合并、完整校验和保存。版本冲突返回 409；参数或依赖无效返回 422，原记录不变。历史计划和卡片正文不改。
- 修改上游优化输入或设置后，沿用其旧结果的下游会清空结果坐标和单位并恢复等待。补回或替换一份优化结果时，模型应在同一 patch 中更新使用它的各个任务；未同步更新的消费者不继续沿用旧结构。后端不验证结果记录是否来自真实计算。
- 卡片保留原始 `version`，另用 `is_applicable_to_current_plan` 表示当前适用性。当前任务满足出卡条件，且生成的输入正文与旧卡相同时，可复用旧卡；`is_current_plan_version` 只表示它是否来自最新版本，不能替代适用性判断。

字段见 `workflow_models.py` 的 `PlanPatch`／`PlanRevisionRequest`，合并入口为 `WorkflowStore.revise`。DSH JSON 解析失败时，请求尚未到达后端。

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

依据官方 README 与对应解析代码：

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

- 后端没有统一的能量、ZPE 或波函数结果接口；分析任务保存公式，不自动计算。
- REST 官方 README 未明确 MP2 是否允许经验色散：当前仅对双杂化/RPA 类方法禁止色散，MP2 + 色散被允许（目录与测试中固化此决定）。
- `[geom] unit` 接受 `angstrom|bohr`，省略时提示单位未记录。
- 校验器不检查 `basis_path` 是否真实存在于部署文件系统（输入卡校验与部署环境检查分离）。
- 桌面构建使用 Python 3.11；输入契约检查没有执行 REST，不证明数值精度、梯度完整性或计算收敛。

## 桌面后端

`aifs.desktop_launcher` 先设置绝对数据路径，再绑定 `127.0.0.1:0`，等 Uvicorn 就绪后在 stdout 输出一条 JSON ready 记录（实际 baseUrl、service、version）。日志在数据目录，父进程 stdin 管道 EOF 会请求退出。SQLite 工作流与证据库分别保存，基础包关闭语义模型加载。

`aifs.migrate_desktop` 提供显式 SQLite 迁移：先用 SQLite backup 生成快照再复制，保留源文件并拒绝覆盖。冻结可执行文件同样支持 `migrate --source ... --destination ...`。请先停止使用相关库的 AIFS 服务。

后端完整测试包含 FAISS 持久化测试，安装 `.[dev,retrieval-test]` 后运行。`retrieval-test` 只提供测试所需 FAISS 与 numpy，不要求下载 sentence-transformers 模型；桌面运行包不依赖这组组件。

## 坐标单位与历史兼容

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
