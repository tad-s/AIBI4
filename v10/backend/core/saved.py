"""保存済み分析（ダッシュボード）の永続化。

QuerySpec は JSON なので、名前を付けてファイルに保存し、後から呼び出して
現在のセッションで再実行できる。セッションはインメモリで揮発するが、
保存済み分析はサーバ再起動をまたいで残る。

保存先: v10/backend/data/saved_views.json（単一ファイル・簡易ロック）。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_PATH = os.path.join(_DIR, "saved_views.json")
_LOCK = threading.Lock()


def _read() -> list[dict]:
    if not os.path.exists(_PATH):
        return []
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(items: list[dict]) -> None:
    os.makedirs(_DIR, exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _PATH)


def list_saved(dataset: str | None = None) -> list[dict]:
    items = _read()
    if dataset:
        items = [x for x in items if x.get("dataset") == dataset]
    return sorted(items, key=lambda x: x.get("created_at", 0), reverse=True)


def add_saved(name: str, spec: dict, dataset: str) -> dict:
    item = {
        "id": str(uuid.uuid4()),
        "name": name.strip() or "無題の分析",
        "dataset": dataset,
        "spec": spec,
        "created_at": time.time(),
    }
    with _LOCK:
        items = _read()
        items.append(item)
        _write(items)
    return item


def delete_saved(view_id: str) -> bool:
    with _LOCK:
        items = _read()
        new = [x for x in items if x.get("id") != view_id]
        if len(new) == len(items):
            return False
        _write(new)
    return True
