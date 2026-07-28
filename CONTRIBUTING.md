# Contributing to TEEA

Thank you for your interest in the Tibetan Editor Enterprise Architecture.

## Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/)
Code of Conduct. By participating, you agree to uphold this code.

## Architecture Is Frozen

TEEA's architecture is governed by ADR-001 through ADR-020 (see
`docs/ARCHITECTURE_DECISIONS.md`). These decisions are considered final
for the 1.x release cycle.

Before proposing an architectural change:
1. Read the existing ADRs to understand why a decision was made.
2. Open a discussion to present your rationale.
3. Propose a new ADR that supersedes the relevant one(s).

All ADRs are enforced mechanically by `tests/test_architecture.py`.

## Getting Started

### Prerequisites

- **Python 3.12+**
- **Git**
- **Node.js 18+** (for the Office.js add-in)
- **No GPU required** — the TiBERT tokenizer does not need `torch`

### Setup

```powershell
# Clone the repository
git clone <repo-url>
cd teea

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install pinned dependencies (reproducible build)
pip install -r requirements.lock

# Install the package in editable mode
pip install -e "." --no-deps

# Set UTF-8 encoding for Tibetan text output (Windows)
$env:PYTHONIOENCODING = "utf-8"

# Set up the Office.js add-in (optional, for add-in development)
cd addin
npm ci
```

### Regenerating Lock Files

```powershell
# Python
pip install pip-tools
pip-compile --extra=dev --output-file=requirements.lock --strip-extras --no-annotate pyproject.toml

# TypeScript
cd addin
npm install --package-lock-only
```

## Development Workflow

### Branching

- `main` — stable, release-ready
- `develop` — integration branch for feature work
- Feature branches: `feat/<description>`
- Bug fixes: `fix/<description>`

### Running Checks

Always run these before committing:

```powershell
# Python
python -m pytest -q --tb=short       # 2,131+ tests
python -m mypy src                     # strict type checking
python -m ruff check src tests         # linting

# TypeScript (add-in)
cd addin
npm run typecheck                      # tsc --noEmit
npm run lint                           # eslint
npm test                               # jest (263+ tests)
npm run build                          # webpack production build
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add SQLite-backed fingerprint repository
fix: correct off-by-one in span translation
docs: update HANDOVER.md with release status
refactor: extract common tokenizer logic
test: add regression test for IPC cancel race
ci: cache pip dependencies using requirements.lock
```

## Project Structure

```
teea/
├── src/teea/           # Python package (the daemon)
├── addin/              # TypeScript Office.js add-in
├── tests/              # Python test suite
├── docs/               # Architecture documentation
└── .github/workflows/  # CI/CD configuration
```

## Testing Guidelines

1. **All tests must be hermetic** — no network access, no external services.
2. **No timing-dependent assertions** — use structural equality checks.
3. **Use fixtures** — reuse existing `conftest.py` fixtures where possible.
4. **Test with Tibetan text** — use corpus-derived fixtures from `tests/data/`.
5. **Run the full suite** — your change must not break existing tests.

## Code Style

- **Python**: Follow `ruff` and `mypy --strict`. The project uses Google-style
  docstrings and `from __future__ import annotations`.
- **TypeScript**: Follow `eslint` and `tsc --strict`. Use React functional
  components with hooks.
- **No TODO/FIXME/HACK** — tracked defects are strict `xfail` tests.

## License

Proprietary. See the license file for details.
