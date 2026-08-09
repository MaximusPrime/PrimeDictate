"""Persistence boundary for the local transcription history."""

import threading

from src.config import config_manager


class HistoryStore:
    """Cache bounded history entries and centralize disk mutations."""

    def __init__(self, persistence=None, limit: int = 100):
        self._persistence = persistence or config_manager
        self._limit = max(1, int(limit))
        self._entries = None
        self._lock = threading.RLock()

    def invalidate(self):
        with self._lock:
            self._entries = None

    def entries(self) -> list:
        with self._lock:
            if self._entries is None:
                loaded = self._persistence.load_history()
                self._entries = list(loaded) if isinstance(loaded, list) else []
            return [dict(item) for item in self._entries if isinstance(item, dict)]

    def add(self, entry: dict):
        with self._lock:
            entries = self.entries()
            entries.insert(0, dict(entry))
            self._replace(entries)

    def delete(self, text: str, timestamp: str) -> bool:
        with self._lock:
            entries = self.entries()
            for index, item in enumerate(entries):
                if item.get("text", "") == text and item.get("time", "") == timestamp:
                    del entries[index]
                    self._replace(entries)
                    return True
            return False

    def clear(self):
        with self._lock:
            self._replace([])

    def _replace(self, entries: list):
        replacement = [dict(item) for item in entries[:self._limit] if isinstance(item, dict)]
        result = self._persistence.save_history(replacement)
        if result is False:
            raise OSError("Could not persist transcription history.")
        self._entries = replacement
