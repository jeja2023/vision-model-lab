from __future__ import annotations

from pathlib import Path


def test_env_files_keep_configuration_body_aligned() -> None:
    root = Path(__file__).resolve().parents[1]
    env_lines = (root / ".env").read_text(encoding="utf-8").splitlines()
    example_lines = (root / ".env.example").read_text(encoding="utf-8").splitlines()

    assert env_lines[2:] == example_lines[2:]
