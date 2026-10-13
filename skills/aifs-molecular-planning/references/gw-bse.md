# REST 的 GW/BSE 输入

本说明对应 AIFS 已核对的输入子集。先查 `get_rest_capabilities`；需要字段类型、单位与范围时查 `section="quasiparticle_methods"`。参数通过 AIFS 校验不表示 REST 已运行，也不保证收敛或精度。

## 选择出卡入口

GW/BSE 使用 `job_type="energy"`，额外设置放在 `rest_options.quasiparticle_methods`。`xc` 和 `basis` 指 SCF 起点的方法与轨道基组；不要把 GW 或 BSE 填成泛函名。这里的 `energy` 是 REST 作业入口，不表示 GW 准粒子能量就是体系总能。

一张 REST 卡内部可以完成 SCF → GW → BSE。用户要求在给定结构上计算时，直接用该结构出卡；用户要求先优化时，才建立优化 → GW/BSE 的依赖。后者等真实优化坐标及其单位，再用 patch 补回。不要把 REST 内部的 SCF/GW/BSE 顺序强行拆成三个 AIFS 任务。

## 最小设置示例

以下只展示 `rest_options`。假设用户已选定：限制性闭壳层参考、G₀W₀ 外推、三重态 BSE-TDA、Davidson 求五个激发根，并提供 SCF/GW 辅助基组目录。结构、单位、电荷、基态多重度、SCF 泛函与轨道基组仍通过主字段提交。

```json
{
  "ctrl": {
    "eri_type": "ri_v",
    "use_ri_symm": true,
    "auxbas_path": "./basis/JKFIT"
  },
  "quasiparticle_methods": {
    "gw_or_bse": "bse",
    "gw_scheme": "extrapolated",
    "scgw": "g0w0",
    "bse_spin": "triplet",
    "bse_tda": true,
    "bse_davidson_solver": true,
    "davidson_target_excitations": 5
  }
}
```

这是用户已确认设置的输入形状示例，不是通用推荐。未提供辅助基组时按目标运行环境确认，不能假称示例路径存在。直接出卡和保存任务都使用同样的 `rest_options`；保存任务时该字段在任务顶层。

## 基态与激发通道

主字段 `spin` 是 SCF 参考态的多重度；`bse_spin` 是 BSE 通道。闭壳层分子算三重激发时，基态 `spin` 仍为 1，设置 `bse_spin="triplet"`。

- 限制性参考：`bse_spin` 可选 `singlet`、`triplet`、`both`。
- 非限制性参考：目前只接入 G₀W₀、`gw_scheme="extrapolated"`；UBSE 用 `bse_spin="unrestricted"` 开启单个耦合通道。上游也接受旧写法 `singlet`，但它不表示纯单重态。不能选 `triplet` 或 `both`。
- ROHF、非限制性 evGW 和 rsGW 不在当前接入范围。
- `bse_tda=true` 为 TDA，`false` 为 full BSE；须明确选择。

## GW 方法与加速

| 需求 | REST 设置与注意事项 |
| --- | --- |
| G₀W₀ | `scgw="g0w0"`；`gw_or_bse="gw"` 只做 GW，`"bse"` 后接 BSE |
| 全轨道准粒子方程 | `gw_scheme="qp equation"`；不是 `"full"`，也与 full BSE 的 `bse_tda=false` 不同 |
| 线性化准粒子方程 | `gw_scheme="linearize"` |
| 部分轨道计算后外推 | `gw_scheme="extrapolated"`；窗口参数见下文 |
| evGW | 限制性参考，`scgw="evgw"` 与明确的正整数 `evgw_rounds`；轮数不证明收敛 |
| rsGW | 限制性参考，`renormalized_singles=true`；`w_rs=true` 让屏蔽也采用 RS。两个开关不代替 `scgw` |
| 仅 HOMO/LUMO | 当前接入限制性 GW-only G₀W₀ 的 `homo_lumo_gw_qp=true`；不能把不完整轨道谱用于 BSE |
| 低秩围道加速 | `use_low_rank_contour=true`，按需设置 `nomega_chi_real`、`low_rank_tolerance`、`omega_chi_max`、网格与插值；`omega_chi_max=0` 自动选范围，非零值单位 Hartree |

教程中的单个 `threshold` **没有被所核对源码解析**。外推窗口实际是 `gw_extrapolate_occ_threshold` 和 `gw_extrapolate_vir_threshold`，单位 Hartree，分别控制占据与虚轨道的显式计算范围。不要把它们当成求解器收敛误差。

Davidson 根数使用 `davidson_target_excitations`，需 `bse_davidson_solver=true`。子空间、重启、迭代上限和收敛阈值是求解器设置。`bse_cutoff_energy` 则是**虚轨道绝对能量上限，单位 Hartree**，不是激发能区间或根数。根数和截断是否适合实际轨道空间仍需运行检查。

## 辅助基组、LAMB 与外部文件

- `ctrl.auxbas_path`：SCF/GW 的 RI 辅助基组目录。
- `quasiparticle_methods.bse_auxbas_path`：可选的 BSE 专用辅助基组目录；REST 在 GW 后重建 BSE 所用 RI，不替换前面的 GW 辅助基组。
- LAMB 用较低角动量的辅助基组加速 BSE。本轮接入的是**用户准备好的截断辅助基组目录**，通过 `bse_auxbas_path` 使用。AIFS 不自动生成或截断基组；尚未核实的角动量截断开关不出卡。
- `bse_matvec_style="ao"` 请求 AO 路径；非限制性参考、关闭 `use_ri_symm` 或缺少 BSE 专用辅助基组时可能退回 MO。不要据此承诺使用了 AO 加速。
- `save_qp=true` 可配 `save_qp_path` 输出准粒子文件。另一次 BSE 读取已有文件需 `gw_scheme="parse from file"` 和明确的 `parse_qp_path`；此时跳过 GW，不再附加 evGW/rsGW 设置。用户须确认文件对应的参考态、轨道顺序与能量单位。

这些路径是 REST 运行环境中的路径，原样写入，不拼接 AIFS 的轨道基组池。AIFS 不检查目标机器上的目录、文件或续算数据是否匹配。GW/BSE 使用 RI-V；`eri_type="ri_v"` 与 `"ri-v"` 均接受，不能使用 AO pair pruning。

## 范围和依据

本轮未接入 GW/BSE 频域响应、SOC、QSGW、动态核、FEAST 和激发态导数。TDDFT 已接入的同名能力不能直接套用到 BSE。

用户提供的指南中，六个分子的十二张闭壳层 BSE-TDA 示例用于输入回归检查；没有提供可独立复核的 REST 输出，因此不据此声称数值验证通过或对所有分子准确。

规则核对 [REST 固定源码](https://gitee.com/restgroup/rest/tree/6fa7f3b0b6476fa533dfc38af8b8505730713ac6)：`src/ctrl_io/quasiparticle_methods.rs`、`src/ri_gw/`、`src/ri_bse/`。方法与加速背景见 [Gao、Zhang、Xu，JCP 164, 214116 (2026)](https://doi.org/10.1063/5.0331920)。数值精度和加速比取决于体系及参数，运行后再比较。
