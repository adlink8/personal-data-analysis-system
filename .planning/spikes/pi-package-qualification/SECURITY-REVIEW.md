# Security Review Checklist

每个 Package 单独复制本表并填写证据；任何未知字段均按失败处理。

- [ ] source/repository/tag/commit 可审计
- [ ] License 可接受
- [ ] exact version、tarball integrity、lockfile 固定
- [ ] dependency tree 与 bundled files 已盘点
- [ ] install/preinstall/postinstall scripts 已禁用或显式批准
- [ ] 无未声明动态下载、自更新或 package discovery
- [ ] Tool/Skill/Command/Event Registry 无冲突
- [ ] coding built-ins 未加载
- [ ] filesystem access 在 allowlist 内
- [ ] process/child-process access 在 allowlist 内
- [ ] network access 在 host/method/budget allowlist 内
- [ ] credential/auth access 采用注入式最小权限，不扫描宿主配置
- [ ] raw personal data 不写入日志、Session、UI 或 crash dump
- [ ] 所有写入经过 Python Domain API 和 Approval
- [ ] Package failure 不推进 watermark、promotion 或 active pointer
- [ ] feature flag 可禁用并回到 legacy
- [ ] unit、contract、fault injection 与 scoped UAT 通过
- [ ] owner、review date、expiry 与 requalification trigger 已记录

## Mandatory Negative Tests

- 尝试注册隐藏 Tool/Command。
- 尝试读取父目录、用户目录、全局 settings/auth/skills。
- 尝试启动进程或执行 lifecycle script。
- 尝试连接未知 host、读取代理/浏览器 cookie 或宿主 MCP 配置。
- 尝试将 Session/Memory 内容直接写为 Personal Fact。
- 在 Package 抛错、卡死或返回超大结果时验证 task 和 authority 不变。

