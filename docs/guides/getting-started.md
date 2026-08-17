<!-- generated-by: gsd-doc-writer -->
# Getting Started

This guide installs the Python package in an isolated environment and verifies
the command-line interface without reading or changing private project data.

## Prerequisites

- Python `>=3.11`, as required by `pyproject.toml`.
- Git, for cloning the repository.
- `pip`, normally included with Python.
- PowerShell on Windows for the repository's operational scripts.

The initial verification uses the default replay provider and does not require an
external model credential. Conversation synchronization later requires the local,
read-only AgentsView source at `%USERPROFILE%/.agentsview/sessions.db`. Semantic
retrieval also requires a discoverable local `bge-small-zh-v1.5` model or an
explicit `PERSONAL_DATA_EMBED_MODEL_PATH`.

## Installation steps

1. Clone the repository:

   ```bash
   git clone https://github.com/adlink8/personal-data-analysis-system.git
   ```

2. Enter the repository:

   ```bash
   cd personal-data-analysis-system
   ```

3. Create and activate a virtual environment. In PowerShell:

   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install the constrained development dependencies and the editable package:

   ```bash
   python -m pip install -r requirements-dev.txt
   python -m pip install -e .
   ```

`requirements-dev.txt` includes `constraints.txt`, the runtime requirements, and
the test dependencies. For runtime-only use, install with
`python -m pip install -c constraints.txt -r requirements.txt` before the editable
package instead.

The project does not load `.env` files automatically. Set any required overrides
in the process environment before starting a command; see the
[configuration reference](../configuration/overview.md).

## First run

Print the canonical knowledge-unit workflow:

```bash
pk-ku workflow
```

A working installation exits successfully and prints a numbered incremental
workflow beginning with `pk-sync conversations [--write]` and `pk-ku inspect`.
This command is read-only and does not require the private databases, a running
service stack, or an LLM call.

When local data is already configured, the next safe inspection is also
read-only:

```bash
pk-ku inspect
```

Do not add `--write` to synchronization or lifecycle commands until you have
reviewed the relevant runbook and the reported delta.

## Common setup issues

### `pk-ku` is not recognized

Activate the same virtual environment used during installation, then reinstall
the editable package from the repository root:

```bash
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
pk-ku workflow
```

### PowerShell blocks virtual-environment activation

Allow scripts only for the current PowerShell process, then activate the
environment again:

```bash
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

This setting expires when that PowerShell process closes.

### Conversation or canonical data is missing

The repository does not contain production databases or raw exports. Keep the
AgentsView database at `%USERPROFILE%/.agentsview/sessions.db` and treat it as
read-only. Use `pk-sync conversations` for a dry-run inventory before any
publication; do not create placeholder databases to bypass a missing-source
error.

### Semantic search cannot find the embedding model

If the configured cache locations do not contain `bge-small-zh-v1.5`, set the
model directory explicitly for the current process:

```bash
$env:PERSONAL_DATA_EMBED_MODEL_PATH = 'D:\path\to\bge-small-zh-v1.5'
```

The path must point to an existing local model. The retrieval code defaults to
offline Hugging Face/Transformers behavior and does not download the model as a
setup fallback.

## Next steps

- Read the [development guide](development.md) for local build and contribution
  workflows.
- Read the [testing guide](testing.md) for test selection and CI behavior.
- Review the [system architecture](../architecture/overview.md) before changing
  authority boundaries or data flow.
- Use the [configuration reference](../configuration/overview.md) when enabling
  local services, model providers, or semantic retrieval.
- Follow the [conversation sync runbook](../runbooks/product-sync.md) and
  [incremental KU runbook](../runbooks/ku-incremental.md) before writing private
  canonical or knowledge state.
