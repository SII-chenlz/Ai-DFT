# AIFS Harness Profiles

该目录保存 AIFS 使用的 DeepSeek Harness profile、bundle patch 和本地配置示例。

配置不得包含 API key 或机器特有的绝对密钥路径。运行时的密钥应放在 AIFS 根目录的 `.env.local`，不要写入 profile patch。

`aifs-web/` 是可选的本地 overlay 示例。正常安装 `dsh-plugin-aifs` 后，插件自带的 bundle patch 会自动插入 AIFS 工具；只有需要修改后端地址、超时或响应大小时才使用该 overlay。
