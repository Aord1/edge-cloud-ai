"""离线缓存 — SQLite 本地队列，断网时暂存、恢复后补传。"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

from ..config import edge_settings

logger = logging.getLogger(__name__)


class OfflineCache:
    """断网容错：失败时缓存到本地 SQLite，恢复后自动补传。"""

    def __init__(self) -> None:
        cache_path = Path(edge_settings.cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        self._db_path = str(cache_path / "offline_uploads.db")
        self._lock = threading.Lock()
        self._upload_func = None

        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS upload_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    image BLOB,
                    created_at REAL NOT NULL,
                    retries INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def set_upload_func(self, fn) -> None:
        """设置补传函数: fn(payload: dict, image: bytes) -> bool"""
        self._upload_func = fn

    def save(self, payload: dict, image: bytes) -> None:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO upload_queue (payload, image, created_at) VALUES (?, ?, ?)",
                    (json.dumps(payload), image, time.time()),
                )
                conn.commit()
        except Exception as e:
            logger.error("OfflineCache save: %s", e)

    def pending_count(self) -> int:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                row = conn.execute("SELECT COUNT(*) FROM upload_queue").fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    def flush(self) -> int:
        """尝试补传所有缓存条目，成功则删除。返回本次成功数。"""
        if not self._upload_func:
            return 0

        succeeded = 0
        max_entries = edge_settings.cache_max_entries

        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT id, payload, image, retries FROM upload_queue ORDER BY id ASC LIMIT ?",
                    (max_entries,),
                ).fetchall()

                for row in rows:
                    row_id, payload_json, image_blob, retries = row

                    current = conn.execute(
                        "SELECT COUNT(*) FROM upload_queue"
                    ).fetchone()
                    if current and current[0] > max_entries * 2:
                        conn.execute(
                            "DELETE FROM upload_queue WHERE id IN "
                            "(SELECT id FROM upload_queue ORDER BY id ASC LIMIT 100)"
                        )
                        continue

                    try:
                        payload = json.loads(payload_json)
                        ok = self._upload_func(payload, image_blob)
                        if ok:
                            conn.execute("DELETE FROM upload_queue WHERE id = ?", (row_id,))
                            succeeded += 1
                        else:
                            conn.execute(
                                "UPDATE upload_queue SET retries = retries + 1 WHERE id = ?",
                                (row_id,),
                            )
                    except Exception as e:
                        logger.warning("OfflineCache retry id=%s: %s", row_id, e)
                        conn.execute(
                            "UPDATE upload_queue SET retries = retries + 1 WHERE id = ?",
                            (row_id,),
                        )

                conn.execute(
                    "DELETE FROM upload_queue WHERE retries > 50"
                )
                conn.commit()
        except Exception as e:
            logger.error("OfflineCache flush: %s", e)

        return succeeded

    def start_retry_loop(self, stop_event: threading.Event) -> None:
        """后台线程：定时补传。"""
        def _loop():
            logger.info("OfflineCache retry loop started (interval=%ds)",
                       edge_settings.cache_retry_interval)
            while not stop_event.is_set():
                stop_event.wait(edge_settings.cache_retry_interval)
                if stop_event.is_set():
                    break
                try:
                    n = self.flush()
                    if n > 0:
                        logger.info("OfflineCache flushed %d entries", n)
                except Exception as e:
                    logger.error("OfflineCache retry error: %s", e)

        t = threading.Thread(target=_loop, daemon=True, name="offline-cache-retry")
        t.start()


_cache: OfflineCache | None = None


def get_cache() -> OfflineCache:
    global _cache
    if _cache is None:
        _cache = OfflineCache()
    return _cache
