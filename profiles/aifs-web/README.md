# AIFS Web profile overlay

这是可选的本地 profile 说明，不是官方 `deepseek-harness/` 的文件。正常情况下，安装 `dsh-plugin-aifs` bundle 就会自动插入 AIFS 工具；只有需要覆盖后端地址或超时设置时，才把下面的 patch 内容合并到 `$DSH_HOME/profiles/web/cordis.patch.yml`。

安装本地 bundle：

```bash
cd /path/to/harness/deepseek-harness
export DSH_HOME=/path/to/harness/AIFS/.dsh-home
pnpm dsh plugin --profile web add /path/to/harness/AIFS/dsh-plugin-aifs
```

模型密钥由 Harness 读取，不要写进 patch：

```bash
export DEEPSEEK_API_KEY='在这里填入你的密钥'
export AIFS_BASIS_SET_POOL='/absolute/path/to/rest/basis_set_pool'
```

可选覆盖 patch：

```yaml
- id: aifs
  config:
    baseUrl: !!js process.env.AIFS_BACKEND_URL ?? 'http://127.0.0.1:8000'
    requestTimeoutMs: 30000
    maxResponseBytes: 1048576
```

