"""Adapter protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class TurnContext:
    speaker_id: str
    display_name: str
    prompt: str
    cwd: Path
    room_id: str
    phase: str
    max_floor_chars: int
    ratified_paths: list[str] = field(default_factory=list)
    timeout_sec: int = 900
    work_dir: Path | None = None  # desk/traces dir for side files


@dataclass
class AdapterResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


class Adapter(Protocol):
    name: str

    def run(self, ctx: TurnContext) -> AdapterResult: ...
