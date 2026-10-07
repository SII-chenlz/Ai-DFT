# AIFS 桌面插件安装

插件包含编译后的工具、Skill 和本机后端。提供 macOS arm64 和 Windows x64 调试包；Windows 后端已通过原生运行检查，DSH 客户端安装及真实对话待验收。

## 安装与使用

1. 在 DSH「插件 → 添加插件」填写对应系统 `.tgz` 安装包的绝对路径，安装并启用，无需手工解压。
2. 打开「AIFS 分子计算助手」状态页，确认服务“可用”；启动失败时查看错误、日志并重试。
3. 在 DSH「设置 → 模型」配置官方或支持工具调用的自定义模型。
4. 提出计算需求，确认参数与方法，保存计划并获取逐任务 `.in` 附件。当前不执行 REST 计算。

用户无需安装 Python、Node 或 Conda。更新时卸载旧插件、安装新版，完全退出并重开 DSH。旧聊天的本机下载链接可能失效，要求找回已保存的卡片即可获得当前链接或正文。

## 数据

默认目录为 `$DSH_HOME/aifs/`，未设置 DSH_HOME 时使用用户目录下的 `.dsh/aifs/`。计划和证据数据库、卡片记录及日志独立于安装目录，更新或卸载不会主动删除。日志在 `logs/launcher.log` 和 `logs/backend.log`。

## 结构升级与备份

打开受支持的旧工作流数据库时，后端先用 SQLite backup 保存到数据目录的 `schema-backups/`，再事务升级结构版本；失败会回滚并保留备份。历史计划快照和卡片原文不重写，空基组、缺单位仍表示未知。遇到比程序新的格式会拒绝写入，需使用匹配版本；不自动降级。更新插件不会自动为旧计划补计算任务。

## 迁移已有数据库

`migrate` 是显式搬家，不是结构升级命令。先停用 AIFS，确认目标没有同名数据库。解压对应系统安装包后，运行附带后端的 `migrate` 命令。

macOS：

```sh
"/绝对路径/package/runtimes/darwin-arm64/aifs-backend/aifs-backend" migrate \
  --source "/原数据库目录" --destination "$HOME/.dsh/aifs"
```

Windows PowerShell：

```powershell
& 'C:\解压目录\package\runtimes\win32-x64\aifs-backend\aifs-backend.exe' migrate --source 'C:\原数据库目录' --destination "$env:USERPROFILE\.dsh\aifs"
```

自定义 DSH_HOME 时使用实际目标目录。迁移先备份 SQLite 再复制，保留源文件，拒绝覆盖目标；不合并已使用的数据库。

开发者构建命令见源码仓库的 `scripts/README.md`，真实对话检查见 [验收案例](local-acceptance.md)。
