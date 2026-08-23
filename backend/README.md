# AIFS Backend

Python FastAPI 领域后端，负责 REST 量子化学软件的输入卡领域核心：

- REST 方法/基组/色散/关键词目录（版本化数据）；
- 结构化请求 → REST TOML 输入卡渲染；
- 与渲染器完全独立的 TOML 输入卡校验器；
- 健康检查与 REST 输入 API。

本目录不包含 Harness 会话循环、Web UI、TypeScript 插件、推荐算法、RAG 或计算执行器。旧原型位于 `../prototype-v0/`，只能作为只读参考。

## 环境与安装

- 推荐 Python >= 3.11（`tomllib` 为标准库）；3.10 通过 `tomli` 兼容包运行（`pyproject.toml` 中按版本条件安装）。
- 安装：`python -m pip install -e './backend[dev]'`（开发依赖包含 pytest、httpx、ruff、mypy）。

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
| GET | `/health` | `{"status": "ok", "service": "aifs-api", "version": "0.1.0"}` |
| POST | `/v1/rest-inputs` | 渲染 REST TOML 输入卡；领域设置不兼容返回 422 与稳定 JSON 错误 |
| POST | `/v1/rest-inputs/validate` | 独立校验完整输入卡；`valid=false` 是 200 领域结果 |

推荐接口 `/v1/recommendations` 由后续任务实现，当前刻意不存在。

## REST 规则来源

方法目录、默认基组、色散取值与输出项均来自 REST 官方 README：

- 来源：https://gitee.com/restgroup/rest/blob/master/README.md
- 读取日期：2026-08-23（见 `src/aifs/rest/catalogs.py` 中的 `SOURCE_URL` / `SOURCE_READ_DATE`）

运行时校验不依赖网络。

## 关键行为

- 自洽场方法（HF、LDA、BLYP、PBE、xPBE、XLYP、SCAN、M06-L、MN15-L、TPSS、B3LYP、X3LYP、PBE0、M05、M05-2X、M06、M06-2X、SCAN0、MN15）默认基组 `def2-TZVPP`；后自洽场方法（MP2、XYG3、XYGJOS、XYG7、xDH-PBE0、sBGE2、ZRPS、scsRPA、R-xDH7、RPA@PBE、RPA@B3LYP）默认基组 `def2-QZVPP`。
- 经验色散仅允许 `d3`、`d3bj`、`d4`，通过独立的 `empirical_dispersion` 键输出；双杂化/RPA 类方法（XYG3、XYG7、XYGJOS、xDH-PBE0、sBGE2、ZRPS、scsRPA、R-xDH7、RPA@PBE、RPA@B3LYP）请求色散时返回结构化领域错误（code `empirical_dispersion_not_needed`），绝不静默删除。
- `spin == 1` 自动推导 `spin_polarization=false`；`spin > 1` 自动推导 `true`；推导结果记录在 `defaults_applied`。
- `num_threads` 缺省为 10；`basis_path` 由部署传入的 `basis_set_pool` 与最终基组拼接，后端不硬编码本机路径。
- `position` 使用 TOML 三双引号多行字符串输出；渲染器不接受任意 TOML 键值片段。
- 校验器独立于渲染器：TOML 语法、`[ctrl]`/`[geom]` 存在性、必需字段、字段位置、伪造关键词（`method`/`coord`/`molecule`）、目录成员、数值范围、有限电荷、自旋一致性、色散兼容与坐标格式；未收录的 section 和 keyword 作为警告返回，不静默忽略；错误按固定顺序返回，TOML 无法解析时只返回语法错误。

## 已知限制

- REST 官方 README 未明确 MP2 是否允许经验色散：当前仅对双杂化/RPA 类方法禁止色散，MP2 + 色散被允许（目录与测试中固化此决定）。
- `[geom]` 中若出现 `unit` 键，校验器不检查其取值（REST README 提及该键，但取值集合未在本任务范围核实）。
- 校验器不检查 `basis_path` 是否真实存在于部署文件系统（输入卡校验与部署环境检查分离）。
- 测试环境为 Python 3.10（AI-DFT conda 环境），通过 `tomli` 兼容包运行；任务目标版本为 3.11+。
