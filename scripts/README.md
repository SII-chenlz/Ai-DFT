# AIFS Scripts

本地开发、打包与检查命令。模型接口和密钥在 DSH 设置中配置。

## 本地联调

桌面插件是当前主入口。需要单独调试 API 时，复制 `.env.example` 为 `.env.local`，设置 AIFS 数据与基组池配置，再运行 `./scripts/start-backend.sh`；`./scripts/check-local.sh` 检查后端生成与校验。模型接口及密钥继续在 DSH 设置。

旧 Web 联调脚本不作为本轮维护和桌面验收入口。

## 打包

构建需要 Python 3.11 和 Node 22；平台后端必须在对应系统上生成。使用固定依赖 `packaging/requirements-desktop.lock`。

### macOS arm64

先在 `dsh-plugin-aifs` 运行 `npm ci`，然后从 AIFS 根目录运行：

```bash
AIFS_UPDATE_LOCAL_PACKAGE=0 AIFS_PYTHON=/path/to/python3.11 ./scripts/build-macos-local.sh
```

输出 `dist/aifs-dsh-<版本>-macos-arm64-local.tgz` 及 `.sha256`。只修改 TypeScript 或 Skill、后端版本未变时：

```bash
AIFS_UPDATE_LOCAL_PACKAGE=0 node scripts/build-desktop-plugin.mjs --target darwin-arm64
```

### Windows x64

在 Windows x64 安装 Python 3.11 和 Node 22，确认 `py`、`node`、`npm`、`tar` 可用；将源码放到本机，在 AIFS 根目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows-local.ps1
```

脚本安装固定依赖、构建 `.exe`，检查动态端口、保存／下载、修订、重开持久化和父管道退出，再生成 `dist/aifs-dsh-<版本>-windows-x64-local.tgz` 及 `.sha256`。检查报告位于 `.local/windows-backend-verification.json`。随后在 Windows DSH 安装该包，按 [验收案例](../packaging/local-acceptance.md) 测试真实对话。

### GitHub 构建 Windows 包

工作流文件为 `.github/workflows/windows-plugin.yml`。PR、推送到 `main` 和手动运行先在 Linux 执行后端测试、Ruff、契约同步、插件／打包测试和 TypeScript 检查。`main` 或手动运行的质量检查通过后，使用 Windows x64 runner 原生构建并验证冻结后端。可在 GitHub「Actions → AIFS checks and Windows build → Run workflow」手动启动。

成功后在运行页面的 **Artifacts** 下载 `aifs-windows-x64-<运行序号>` ZIP。解压 ZIP，取出其中的 `.tgz`，在 Windows DSH 添加插件时填写该 `.tgz` 的本机绝对路径。ZIP 内还包含 `.sha256` 和验证报告；Artifact 保存 14 天，需要长期留存时请下载保存。

构建使用仓库的 `main`。后端检查通过后仍需在 Windows DSH 验收安装及真实对话。

两个平台共用插件与 Skill，包中只包含对应平台的后端。成功打包只清理同平台、同渠道的旧压缩包，保留其他平台产物。

### 更新版本与检查

版本来源为 `backend/src/aifs/__init__.py`。修改版本号后运行 `node scripts/release.mjs --sync`，再完整构建后端与插件。


开发检查：

```bash
python -m pip install -c packaging/requirements-desktop.lock -e './backend[dev,retrieval-test]'
python -m aifs.contracts --check
(cd backend && python -m pytest -q)
(cd backend && python -m ruff check src tests)
(cd dsh-plugin-aifs && npm test)
(cd dsh-plugin-aifs && npm run typecheck)
```

`verify-desktop-backend.py` 检查冻结后端；`verify-desktop-host.mjs` 检查 DSH 工具、Skill 和子进程服务。`verify-desktop-import.mjs` 由打包脚本自动执行，检查插件在没有开发依赖的目录中导入。

更新桌面安装副本：完整构建后，在 DSH 卸载旧插件、添加新 `.tgz`，完全退出并重开。`AIFS_UPDATE_LOCAL_PACKAGE=0` 避免覆盖旧的目录链接安装目标；正常 `.tgz` 安装无需使用 `dist/package`，两种方式都不修改数据目录。

## 接口与任务维护

| 改动 | 入口与检查 |
| --- | --- |
| 新任务拆分或物理量流程 | `skills/aifs-molecular-planning/`；保留通用条件，新增计划与回复案例 |
| REST 新字段或组合 | `backend/src/aifs/rest/capabilities.py`、`catalogs.py`、`renderer.py`、`validator.py`；后端支持／拒绝测试及覆盖清单 |
| Python 请求／响应字段 | `models.py`、`workflow_models.py`、`evidence_models.py`；重新生成契约并运行同步检查 |
| 模型说明 | `dsh-plugin-aifs/src/schema-descriptions.ts` 与提示词；说明路径失效会报错 |
| 历史格式变化 | `workflow_schema.py` 注册明确版本适配／升级，新增真实旧库、备份和回滚案例 |
| DSH 工具与进程 | `tools.ts`、`client.ts`、`src/desktop/`；插件测试及真实宿主检查 |

修改 Python 模型后，从仓库根目录运行：

```bash
python -m aifs.contracts --write
python -m aifs.contracts --check
node scripts/check-contracts.mjs
```

第一个命令更新 `contracts/backend-schema.json` 与 `dsh-plugin-aifs/src/generated/backend.ts`；后两个只检查，不修复文件。应一并提交源码及生成文件。生成投影覆盖结构、必填项、枚举和可空字段；数值范围、开放字典内的科学字段和组合约束继续由 Python 检查。插件测试验证随包 Skill 示例，测试／构建拒绝过期契约。

四种版本分别维护：软件版本来自 `__init__.py`；数据库结构用 SQLite `user_version`；计划快照格式用 `plan_versions.schema_version`；用户修订计划产生 `version`。当前首次打开受支持旧工作流库会备份到同目录 `schema-backups/`，事务升级只补版本字段，不重写 JSON 或卡片。空旧基组读成未知；不补确认单位。遇到更高结构／快照格式禁止写入，不尝试自动降级。

`migrate` 命令用于数据库搬家，拒绝覆盖目标；格式升级在服务打开工作流库时执行。数据操作说明见 [安装说明](../packaging/README.md)。

Mac 完整构建先检查冻结后端再组包和清理旧包；检查报告为 `.local/macos-backend-verification.json`。可以另外运行：

```bash
python scripts/verify-desktop-backend.py build/desktop-runtimes/darwin-arm64/aifs-backend/aifs-backend
node scripts/verify-desktop-host.mjs
```

第二条需要可用的 DSH 开发依赖，默认读取邻接 `deepseek-harness`，可用 `DEEPSEEK_HARNESS_DIR` 覆盖。它使用隔离数据目录和实际 DSH 服务，检查十个工具、Skill、生命周期和工作流，不调用模型 API，也不等同于客户端 UI 或科学结果验收。
