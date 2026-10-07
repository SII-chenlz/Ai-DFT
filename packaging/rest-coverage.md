# REST 能力范围

AIFS 的目标是覆盖官方 REST 的计算规划与输入文件，不执行计算。当前输入契约核对至 [REST 源码 `6fa7f3b`](https://gitee.com/restgroup/rest/tree/6fa7f3b0b6476fa533dfc38af8b8505730713ac6)（2026-10-02 提交）。下列“已接入”指可保存参数、生成并由 AIFS 独立检查输入；尚未用 REST 执行这些新任务。

## 已接入

| 能力 | 输入表示 | 当前条件 |
| --- | --- | --- |
| 单点能、优化、力、数值偶极 | `job_type` | 坐标、单位、电荷、自旋与方法已确认 |
| 新增范围分离方法 | legacy：wB97X、CAM-B3LYP、LC-BLYP、LC-wPBE、HSE03/06 | 对目标性质评估依据，不固定推荐某个方法 |
| 新增 parse_xc 变体 | wB97X-V、wB97M-V、wB97X-D3、wB97X-D3BJ、wB97M-D3BJ | 变体原样保存；含 VV10 优化/力须显式数值力，不支持未经核对的解析 Hessian/响应组合 |
| 原生 Hessian、谐振频率 | `energy` + `[hessian]` 或 `[ctrl.hessian]` | 限已声明的闭壳层 HF/LDA/GGA/常规杂化；mGGA、RSH 与后 SCF 方法阻塞 |
| analdrv Hessian、谐振频率 | `energy` + `ctrl.analdrv_tasks=["hessian"]`、可选 `[analdrv]` | 支持已接入 SCF 方法的限制性／非限制性参考，包括 RSH、mGGA；不支持 ROHF、后 SCF 或未经核对的 VV10 导数 |
| 电多极矩 | `ctrl.analdrv_tasks=["multipole"]`、`[analdrv]` | 1–4 阶、参考原点 Bohr；SCF 支持开放壳层，指定 PT2 家族后 SCF 仅限制性、无冻结芯；密度导出尚未接入 |
| RRHO / quasi-RRHO 热化学 | Hessian + `[thermo]` / `[ctrl.thermo]` | 温度 K、压力 atm；温压扫描、低频处理、标度、浓度校正 |
| TDDFT / TDA / 波函数稳定性 | `energy` + `[tddft]` | 限制性 triplet/both 需 AO；非限制性参考不能显式设置 tddft_spin；稳定性与激发任务分开 |
| 频域 TDDFT 响应 | `tddft.response_tddft=true` | 限制性参考；外场频率与展宽 Hartree、空间网格 Bohr；不与 FEAST、激发态梯度或 PySOC 混用 |
| FEAST、PySOC 导出、激发态力 | `[tddft]` 中相应开关 | FEAST 限制性 MO；PySOC 限制性 both/AO；梯度限已声明 HF/LDA/GGA/普通杂化、已计算根内的限制性单通道 `force`，不支持 RSH/mGGA、FEAST 梯度与激发态优化 |
| 一维／二维 RRS-PBC | `geom.rrs_pbc=true` 及晶胞、向量、平移、k 点字段 | 闭壳层单点后的有限团簇重构，不是周期 SCF；索引从 0 开始，晶格向量沿用坐标单位；三维采样分支未验收 |
| 过渡态与 IRC 输入 | `opt` + `[geometric_pyo3]` | 初始几何、方法与 Hessian 路径适用；得到真正过渡态仍需结果验证 |
| 固定原子、优化控制 | 五列坐标 + geometric 设置 | fix=0 固定、1 可动；geometric-pyo3 与 tric/dlc/hdlc |
| SCF、格点、RI-PT2、溶剂、相对论等额外设置 | `rest_options` 的已声明字段 | 类型、枚举、范围、组合检查；未知字段不算校验通过 |
| Ghost、点电荷、外电场 | `[geom]` 扩展 | 外电场三分量 a.u.；ghost 坐标/电荷要求显式小数，防止上游忽略不匹配行；不检查外部文件是否存在 |

## 尚未完整接入

| 官方 REST 能力 | AIFS 还需完成 |
| --- | --- |
| MD / AIMD / QM-MM / pure-MM 与伞形采样 | QM/MM 输入模式、外部文件与原子映射、积分与采样参数、纯 MM 例外必需项 |
| GW / BSE / UGW / UBSE | 准粒子参数、参考态与通道、续算文件、求解器组合 |
| analdrv 密度导出 | 计划中的显式 fchk 输出、后 SCF 密度附加文件与目标文件存在性 |
| TDDFT 激发态优化及复杂梯度组合 | RSH／mGGA／FEAST／双通道梯度、优化能量与激发态跟踪；其中当前上游梯度代码明确拒绝 RSH 和 mGGA |
| 三维 RRS-PBC | 核对上游三维采样索引；实际有限团簇和晶胞匹配、轨道数及数值结果验证 |
| 任意 LibXC 与自定义 parse_xc 表达式 | 组件、系数、参数与多步泛函解析；目前仅接入明确列出的名字 |
| 基组、ECP、自定义运行文件 | 实际目标环境的路径与文件准备；当前 basis 参数仍是配置池中的名字 |

这些步骤可先以待接入任务保存，不能用其他卡冒充已支持。清单作为后续接入顺序与验收范围，每项完成后更新状态。

## 契约与查询

`GET /v1/rest-capabilities` 返回方法、区块、来源提交、检查范围与剩余项；`?section=thermo` 等返回该区块的字段类型、范围、枚举与单位。DSH 对应工具为 `get_rest_capabilities`。

计划中的 `rest_options` 使用区块名作为键：

```json
{"hessian":{"frequencies":true},"thermo":{"temperature":298.15,"pressure":1.0}}
```

该任务 `job_type` 仍为 `energy`。决策中的 `xc_parser` 默认为 `legacy`，选择扩展变体时显式设为 `parse_xc`。区块可以为空但其存在可能触发计算，不应自动添加。`[analdrv]` 是设置区块，必须另外设置 `ctrl.analdrv_tasks` 来选择性质；几何优化的解析 Hessian 设置也可使用该区块。

额外参数不能覆盖已确认的 xc、basis、charge、spin、position 或 unit。修订保留旧参数与旧卡；读取历史卡保持正文原样。旧库不需要重写，新增字段有兼容默认值。

## 版本注意事项

- REST 当前源码已接入 VV10 能量；旧 parse_xc 文档仍写未实现。优先核对具体源码提交，不从旧说明推断所有版本。
- wB97X-D 在该源码的解析器中明确拒绝；它与 wB97X-D3 不相同。
- LDA 是方法类别，当前 legacy 解析器不接受裸 `LDA`；可选明确的 SVWN、SVWN-RPA、PZ-LDA、PW-LDA 或 LDA_X_SLATER。不能把泛称自动改成其中一种。
- geomeTRIC 收敛字段实际是 `convergence_*`；README 部分写成 `converge_*`，AIFS 按解析代码校验。
- 原生 `[thermo]` 压力为 atm；geometric 的 `thermo=[T,P]` 压力为 bar。
- README、当前 master 与用户安装的 REST 发布版本可能不同。正式运行前应确认目标版本支持输入中的特性。AIFS 当前无 REST 执行环境探测或数值结果验证。

契约位于 `backend/src/aifs/rest/capabilities.py` 与 `catalogs.py`；生成与独立检查分别位于 `renderer.py`、`validator.py`。下一项接入需要同时更新契约、条件检查、工作流、DSH 参数与相应案例。
