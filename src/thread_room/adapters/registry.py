"""Adapter registry — name → instance."""

from __future__ import annotations

from thread_room.adapters.base import Adapter
from thread_room.adapters.codex import CodexAdapter
from thread_room.adapters.mock import MockAdapter, MockFailAdapter


def get_adapter(name: str | None) -> Adapter:
    key = (name or "mock").strip().lower().replace("-", "_")
    if key in ("mock",):
        return MockAdapter()
    if key in ("mock_fail", "fail"):
        return MockFailAdapter()
    if key in ("codex", "codex_cli"):
        return CodexAdapter()
    # Desk-first speakers: interactive CLI exists; floor pump falls back to mock
    # until a real headless adapter is wired.
    if key in (
        "claude",
        "claude_code",
        "gemini",
        "gemini_cli",
        "grok",
        "grok_build",
    ):
        return MockAdapter()
    raise KeyError(
        f"unknown adapter: {name!r} "
        "(known: mock, codex_cli, claude_code, gemini_cli, grok)"
    )
