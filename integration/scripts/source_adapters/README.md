# Source Adapter Contract

Phase 05 只建立最小 adapter 契约，不替换现有 `run_pipeline.py`。

## Canonical record

每个 adapter 必须产出这些字段：

- `source_type`
- `source_id`
- `title`
- `content`
- `created_at`
- `updated_at`
- `metadata`
- `source_path`
- `source_hash`

## 设计约束

- adapter 只负责把单一来源映射成 canonical record，不负责写入统合库。
- 允许先接结构稳定、读取简单的来源做样例。
- metadata 保留来源特有字段，但不能替代 canonical 字段。
- `source_hash` 必须是确定性的，适合后续批次导入去重。

## 当前样例

- `google_activities.py`
  读取 `Google/structured/db/google_data.sqlite` 的 `activities` 表，
  输出 canonical record 样例，不改变现有 pipeline。

## 冒烟验证

```powershell
python integration\scripts\source_adapters\google_activities.py --limit 2
python integration\scripts\run_pipeline.py --dry-run
```
