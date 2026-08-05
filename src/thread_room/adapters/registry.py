"""Adapter registry — name → instance."""

from __future__ import annotations

from thread_room.adapters.base import Adapter
from thread_room.adapters.codex import CodexAdapter
from thread_room.adapters.mock import MockAdapter, MockFailAdapter


def get_adapter(name: str | None) -> Adapter:
    key = (name or "mock").strip().lower()
    if key in ("mock",):
        return MockAdapter()
    if key in ("mock_fail", "fail"):
        return MockFailAdapter()
    if key in ("codex", "codex_cli", "codex-cli"):
        return CodexAdapter()
    raise KeyError(
        f"unknown adapter: {name!r} (known: mock, mock_fail, codex / codex_cli)"
    )
