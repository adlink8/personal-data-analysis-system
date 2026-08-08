# Package Qualification Plan

## Wave 1 — Official P0 Baseline

对 `pi-coding-agent`、`pi-ai`、`pi-agent-core`、`pi-storage-sqlite-node` 执行：

1. 将 npm tarball digest、registry integrity、repository/tag/commit、License、Node engine 写入审计记录。
2. 以 `npm pack --dry-run`/tarball inventory 核对发布内容与源码 tag。
3. 检查 lifecycle scripts、native addon、postinstall、动态下载、child process、filesystem、network、credential access。
4. 枚举 exported API、registered tools/events、默认 resource discovery、session paths 和 auth resolution。
5. 使用 `--ignore-scripts` 安装到隔离 Spike 目录；若包必须依赖 install script，单独审查并显式 allowlist。
6. 运行 Runtime Containment 001 的负向权限测试。
7. 生成 package registry checksum；版本、integrity 或源码任一变化都使资格失效。

## Wave 2 — Compatibility

1. 固化 core/coding-agent/ai/storage 的 event、message、Tool result、abort、session replacement contract。
2. 验证 `pi-web-ui` 0.75.3 对 core 0.83.0 的 message/event compatibility；不兼容则暂缓或只移植无状态 renderer。
3. 为每个包记录精确 peer/dependency version，不允许宽松 semver 在生产安装时漂移。
4. 覆盖 Node 24.13 与官方最低 Node 22.19 的 CI/测试矩阵候选。

## Wave 3 — Community Package Review

每次只评估一个包：

1. 源码、维护者、License、release/tag、install script 和 dependency tree 审计。
2. 枚举 Tool/Skill/Command/Event 名称与 person-data registry 冲突。
3. 动态运行时监测文件、进程、网络、secret 和 host config discovery。
4. 将原始权限模型映射到 `domain/purpose/sensitivity/operation`；无法映射则拒绝。
5. 故障注入验证 package failure 不推进 task、水位、promotion 或 active index。
6. 决策只能为 adapted/extracted/rejected；社区包不得在首个 P0 Slice 直接加载。

## Wave 4 — Governance Output

只有通过审查后才生成正式 governance files，并加入：owner、last_reviewed、allowed_scope、registered capabilities、rollback、review expiry 和 requalification trigger。

## Requalification Triggers

- version、commit、integrity 或 dependency lock 变化；
- 新增 Tool/Skill/Command/Event；
- 新增 filesystem/network/process/secret 权限；
- Pi core event/schema 改变；
- License/owner/repository 变化；
- 安全公告或测试出现未声明副作用。

## Exit Gate

Wave 1 未通过则 Kernel Spike 001 失败；Wave 2/3 的 deferred 包不阻塞首个 P0 Slice，但不得被提前安装或列为 accepted。

