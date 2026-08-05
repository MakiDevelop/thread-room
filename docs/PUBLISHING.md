# Publishing to PyPI

## Prerequisites

- Account on [pypi.org](https://pypi.org) (and TestPyPI for dry runs)
- API token with upload scope
- Clean git tree on `main`, tests green

## Build

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" build twine
pytest -q
python -m build
# artifacts: dist/thread_room-*.whl  dist/thread_room-*.tar.gz
twine check dist/*
```

## TestPyPI (recommended first)

```bash
twine upload --repository testpypi dist/*
pip install -i https://test.pypi.org/simple/ thread-room
thread-room --version
```

## PyPI

```bash
twine upload dist/*
```

Or use GitHub Actions trusted publishing (OIDC) once configured on the project.

## Version bumps

1. Update `pyproject.toml` `version` and `src/thread_room/__init__.py` `__version__`
2. Update `CHANGELOG.md`
3. Tag: `git tag v0.5.0 && git push origin v0.5.0`

## What we ship

| Include | Exclude |
|---------|---------|
| `src/thread_room/` (incl. `data/*.json`) | `.venv/`, meetings, traces |
| `schemas/`, `docs/`, `examples/` in sdist | secrets, local agent configs |
| CLI entrypoint `thread-room` | live Codex credentials |
