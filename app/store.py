"""Generation persistence: MongoDB preferred, JSON file fallback.

Assignment allows MongoDB Atlas or a well-justified JSON store.
Atlas SSL/IP allowlist failures are common on first setup; we fall back
to data/generations.json so the rest of the pipeline remains demoable.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.config import get_settings

_lock = threading.Lock()
_JSON_PATH = Path(__file__).resolve().parents[1] / "data" / "generations.json"


class GenerationStore:
    def __init__(self) -> None:
        self.backend = "json"
        self._coll = None
        try:
            from pymongo import MongoClient

            settings = get_settings()
            client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            self._coll = client[settings.mongodb_db]["generations"]
            self.backend = "mongodb"
        except Exception:
            self.backend = "json"
            _JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not _JSON_PATH.exists():
                _JSON_PATH.write_text("[]", encoding="utf-8")

    def _read_json(self) -> list[dict[str, Any]]:
        with _lock:
            return json.loads(_JSON_PATH.read_text(encoding="utf-8") or "[]")

    def _write_json(self, rows: list[dict[str, Any]]) -> None:
        with _lock:
            _JSON_PATH.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        if self.backend == "mongodb" and self._coll is not None:
            return self._coll.find_one(query)

        rows = self._read_json()
        for row in rows:
            if self._matches(row, query):
                return row
        return None

    def find(self, query: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        if self.backend == "mongodb" and self._coll is not None:
            return list(self._coll.find(query).sort("created_at", -1).limit(limit))

        rows = [r for r in self._read_json() if self._matches(r, query)]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    def insert_one(self, doc: dict[str, Any]) -> None:
        if self.backend == "mongodb" and self._coll is not None:
            self._coll.insert_one(doc)
            return
        rows = self._read_json()
        rows.append(doc)
        self._write_json(rows)

    @staticmethod
    def _matches(row: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, expected in query.items():
            if key == "llm_status" and isinstance(expected, dict) and "$in" in expected:
                if row.get("llm_status") not in expected["$in"]:
                    return False
                continue
            if key == "source_nodes.node_id":
                nodes = row.get("source_nodes") or []
                if not any(n.get("node_id") == expected for n in nodes):
                    return False
                continue
            if "." in key:
                # simple dotted path
                cur: Any = row
                for part in key.split("."):
                    if not isinstance(cur, dict) or part not in cur:
                        return False
                    cur = cur[part]
                if cur != expected:
                    return False
                continue
            if row.get(key) != expected:
                return False
        return True


_store: GenerationStore | None = None


def get_generation_store() -> GenerationStore:
    global _store
    if _store is None:
        _store = GenerationStore()
    return _store
