---
spike: 003
name: skill-selection-and-artifact-isolation
type: standard
validates: "Given a deterministic Delta manifest, when the Personal Skill runs, then routing and tool permissions are deterministic and Session/Candidate storage remain separate."
verdict: VALIDATED
related: [001, 002, 004]
tags: [skills, artifacts, privacy, isolation]
---

# Spike 003: Skill Selection and Artifact Isolation

## How to Run

```powershell
cd <repo-root>\.planning\spikes\pi-embedded-personal-kernel\prototype\python-domain
python skill_isolation.py
```

## Investigation Trail

- 显式绑定 `maintain-conversation-delta`，不把模型自动选择当作权限边界。
- `bash`、未注册 Skill、缺少 `task_id/source_cutoff/evidence_refs` 和 synthetic secret 均被拒绝。
- Session 与 Candidate 写入两个独立 SQLite；删除 Session 库后 Candidate 仍可读。

## Results

通过。确定性绑定、双重工具门、证据字段门、secret 阻断和存储隔离均通过；2 个 Candidate 无重复。
