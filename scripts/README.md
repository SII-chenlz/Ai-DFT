# AIFS Scripts

该目录保存本地启动、健康检查、接口生成和验收脚本。脚本必须使用明确路径，不得修改同级 `../deepseek-harness/` 的受跟踪文件或在仓库中写入密钥。

## 本地联调

先复制 `.env.example`：

```bash
cp .env.example .env.local
# 编辑 .env.local，至少填写 DEEPSEEK_API_KEY
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

检查 bundle 是否已安装：

```bash
./scripts/verify-harness-mount.sh
./scripts/verify-harness-mount.sh --require-installed
```

第一个命令只检查 AIFS bundle 源文件；第二个命令还要求 `$DSH_HOME/profiles/web` 已经安装了 AIFS。
