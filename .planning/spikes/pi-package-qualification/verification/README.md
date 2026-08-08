# Package Qualification Evidence

执行时保存：

```text
npm-metadata.json
tarball-inventory.json
integrity-report.json
license-report.json
dependency-tree.json
install-script-audit.json
capability-trace.jsonl
negative-test-report.json
compatibility-report.json
```

证据必须可由 package/version/integrity/commit 定位，且不得包含 registry token、npm auth、环境凭据、用户目录内容或个人数据正文。

本轮已保存 `package-integrity-report.json`。npm audit 在 npmmirror endpoint 不可用时切换到 npmjs.org；结果为 2 high、1 moderate，故只给 `CONDITIONAL`。
