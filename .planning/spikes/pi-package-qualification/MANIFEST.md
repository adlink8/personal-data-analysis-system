# Package Qualification Manifest

## Objective

证明进入 Pi Kernel 的每一个包都具有可审计来源、精确版本/integrity、可接受 License、明确系统能力和可回退路径；任何未知项均 fail-closed。

## Required Outputs

执行完成后才生成正式候选文件：

```text
agent-runtime/package.json
agent-runtime/package-lock.json
governance/pi-packages.lock.json
governance/pi-tool-registry.json
governance/pi-network-allowlist.json
docs/architecture/pi-package-boundaries.md
PI_COMPATIBILITY_MATRIX.md
```

当前规划阶段不创建这些生产文件。

## Status Vocabulary

- `candidate`：仅登记，未审计。
- `accepted_for_spike`：可在隔离 Spike 中精确锁版使用。
- `conditional`：仅允许指定组件/适配器/提取机制。
- `rejected`：不得安装或加载。
- `deferred`：当前阶段不评估或不启用。

