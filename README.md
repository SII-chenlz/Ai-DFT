# AIFS

AIFS 是 [DeepSeek Harness（DSH）](https://github.com/deepseek-ai/deepseek-harness) 的分子计算助手插件。用户通过对话选择泛函与基组、拆分计算任务、保存计划，并获得经过校验的 [REST](https://gitee.com/restgroup/rest) `.in` 输入卡。

仓库包含 TypeScript 插件、规划 Skill 和 Python 后端。支持逐任务设置方法，保留证据、计划版本及卡片记录；当前只准备输入，不运行计算。支持范围见 [REST 能力](packaging/rest-coverage.md)。

DSH 提供界面、模型配置、会话和工具调度；AIFS 提供专业流程及计划／输入卡服务。科学建议与最终回复由所选模型生成，Skill 指导模型，后端检查输入与依赖，不自动证明泛函最优或自由文本公式正确。

## 安装

1. 打开 DSH 桌面版，在「插件 → 添加插件」填写 `.tgz` 安装包的绝对路径，无需解压。
2. 启用 AIFS，打开「AIFS 分子计算助手」状态页，等待显示“可用”。
3. 在 DSH「设置 → 模型」配置接口与 API Key，选择支持工具调用的模型。

当前调试包：`dist/aifs-dsh-0.1.13-macos-arm64-local.tgz`、`dist/aifs-dsh-0.1.13-windows-x64-local.tgz`。Windows 后端已通过原生构建与持久化检查，Windows DSH 安装及真实对话待验收；Intel Mac 暂无安装包。

用户无需安装 Python 或 Node。升级时卸载旧插件、安装新版，完全退出并重开 DSH（Mac 用 `⌘Q`）。

## 使用

例如：

> 我想优化水分子，再计算单点电子能。请推荐适合的方案，让我分别选择优化和单点的泛函、基组，保存计划并准备输入卡。

按提示补充结构、坐标单位、电荷和自旋。当前具备输入条件的任务可生成 `.in`；依赖优化结果的任务等待结果坐标及其单位。输入卡可作为附件交付，或直接查看正文。

对比实验 ADE 时，计划包含阴离子和中性的频率／零点能步骤；电子能差与含零点能的 ADE 分别标明。计算仍由用户运行，结果和单位需补回。

计划、证据与卡片保存在 `$DSH_HOME/aifs/`，默认 `~/.dsh/aifs/`。重开后可要求找回计划；实际运行 REST 时需使用计算环境中的基组路径。

开发与打包见 [脚本文档](scripts/README.md)，数据迁移见 [安装说明](packaging/README.md)。
