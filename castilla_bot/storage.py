"""Persistência local dos dados recebidos pelo chatbot."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Protocol


class RecordStorage(Protocol):
    def save(self, collection: str, record: dict[str, Any]) -> str | None: ...


class JsonlStorage:
    """Grava um objeto JSON por linha, com segurança entre threads."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self._lock = Lock()

    def save(self, collection: str, record: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        destination = self.data_dir / f"{collection}.jsonl"
        with self._lock, destination.open("a", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False)
            file.write("\n")
