# Prototype Boundary

本目录预留给 001–005 的实验代码。

- 只允许 synthetic fixture 和 Spike 专用数据库。
- 依赖必须精确锁定；禁止 `latest`、动态安装和社区 Package。
- 不读取全局 Pi/Codex/Claude settings、credentials、skills 或 extensions。
- 不连接正式 SQLite/Chroma authority，不调用 promote/watermark advance。
- 任何真实 cohort 运行前必须单独获得只读授权。
- Prototype 不进入生产 import path，不由现有服务自动启动。

