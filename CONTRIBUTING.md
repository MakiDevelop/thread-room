# Contributing

Thanks for interest in Thread Room.

## Dev setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
ruff check src tests        # if ruff installed via [dev]
```

## Guidelines

1. **Protocol vs host** — TRP semantics live in `docs/TRP.md` and message types. Adapter argv matrices and tmux details stay out of the protocol doc.
2. **Fail closed on floor** — never fallback to “last N chars of stdout” as a public conclusion.
3. **Lossy by design** — do not market Room transcripts as compliance / RED audit logs.
4. **Tests** — add unit tests for parsers, ownership, and CLI; mock subprocess for real CLIs.
5. **Secrets** — never commit `desks/*/traces` or real meeting transcripts.

## PR tips

- Keep PRs focused (one feature or fix).
- Update `CHANGELOG.md` under `[Unreleased]` or the next version section.
- Run `pytest -q` before pushing.

## Code of conduct

Be respectful. This is a small open-source tool for multi-agent meetings — assume good intent, prefer concrete repros.
