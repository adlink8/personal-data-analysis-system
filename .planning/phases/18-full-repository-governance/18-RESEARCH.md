# Phase 18 Research

完整代码库映射位于 `.planning/codebase/`：STACK、INTEGRATIONS、ARCHITECTURE、STRUCTURE、CONVENTIONS、TESTING、CONCERNS。结论是先建立机器可读治理层和零未分类基线，再逐批迁移；禁止一次性大重构。

推荐实现保持轻量：Python scanner + YAML policies + JSON private inventory + Markdown/HTML sanitized summary + pytest/CI gates。无需引入额外 monorepo 平台或资产目录框架。

