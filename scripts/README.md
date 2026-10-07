# AIFS Scripts

本地开发、打包与检查命令。模型接口和密钥在 DSH 设置中配置。

## 本地联调

先复制 `.env.example`：

```bash
cp .env.example .env.local
# 按需编辑 AIFS 配置；模型、接口和密钥统一在 DSH 设置中配置
```

只启动后端：

```bash
./scripts/start-backend.sh
```

检查后端生成并独立校验输入卡：

```bash
./scripts/check-local.sh
```

启动完整 Harness Web + AIFS：

```bash
# 首次使用先在 ../deepseek-harness 完成：pnpm install && pnpm run build
./scripts/start-local.sh
```

首次启动会把本地 `dsh-plugin-aifs` 安装到隔离的 `$DSH_HOME` Web profile。脚本不会修改官方仓库中受跟踪的源码；Harness 需要先在其仓库内完成 `pnpm install` 和 `pnpm run build`。

`.env.local` 只保存 AIFS 开发配置。模型、接口和 API Key 在 DSH「设置 → 模型」配置；自定义模型选择「添加模型提供商」。默认隔离目录与桌面客户端的配置分开；当前脚本只安装 Web profile。详情见 [仓库安装说明](../README.md#安装)。

检查 bundle 是否已安装：

```bash
./scripts/verify-harness-mount.sh
./scripts/verify-harness-mount.sh --require-installed
```

第一个命令在 profile 尚未创建时只检查 AIFS bundle 源文件；若已创建，也检查插件和 Skill 链接。第二个命令要求 `$DSH_HOME/profiles/web` 已安装 AIFS，并核对 `package.json` 中的 bundle、插件链接及 Skill 链接。

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

工作流文件为 `.github/workflows/windows-plugin.yml`，使用 Windows x64 runner，自动构建、验证后端、运行插件测试及类型检查。推送到 `main` 会触发构建，也可在 GitHub「Actions → Build Windows plugin → Run workflow」手动启动。

成功后在运行页面的 **Artifacts** 下载 `aifs-windows-x64-<运行序号>` ZIP。解压 ZIP，取出其中的 `.tgz`，在 Windows DSH 添加插件时填写该 `.tgz` 的本机绝对路径。ZIP 内还包含 `.sha256` 和验证报告；Artifact 保存 14 天，需要长期留存时请下载保存。

构建使用私有仓库的 `main`。后端检查通过后仍需在 Windows DSH 验收安装及真实对话。

两个平台共用插件与 Skill，包中只包含对应平台的后端。成功打包只清理同平台、同渠道的旧压缩包，保留其他平台产物。

### 更新版本与检查

版本来源为 `backend/src/aifs/__init__.py`。修改版本号后运行 `node scripts/release.mjs --sync`，再完整构建后端与插件。


开发检查：

```bash
python -m pip install -e './backend[dev,retrieval-test]'
(cd backend && python -m pytest -q)
(cd backend && python -m ruff check src tests)
(cd dsh-plugin-aifs && npm test)
(cd dsh-plugin-aifs && npm run typecheck)
```

`verify-desktop-backend.py` 检查冻结后端；`verify-desktop-host.mjs` 检查 DSH 工具、Skill 和子进程服务。`verify-desktop-import.mjs` 由打包脚本自动执行，检查插件在没有开发依赖的目录中导入。

运行中的桌面插件更新：先用 `AIFS_UPDATE_LOCAL_PACKAGE=0 ./scripts/build-macos-local.sh` 构建新测试包而保留 `dist/package`；确认旧插件已停用后，运行 `node scripts/build-desktop-plugin.mjs` 更新链接目标，再重新启用。此选项不会改变数据目录。
