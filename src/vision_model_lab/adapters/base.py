from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class AdapterResult:
    status: str
    path: Path
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "path": str(self.path),
            **self.payload,
        }


class TaskAdapter(Protocol):
    name: str
    task: str
    description: str

    def train(self, config_path: str | Path) -> AdapterResult:
        ...

    def export(self, config_path: str | Path) -> AdapterResult:
        ...

    def evaluate(self, config_path: str | Path, onnx_path: str | Path | None = None) -> AdapterResult:
        ...

