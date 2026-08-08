import threading


class OperationCoordinator:
    """Serializes operations that share non-thread-safe transcription engines."""

    def __init__(self):
        self._lock = threading.Lock()
        self._owner = None

    @property
    def active_operation(self):
        with self._lock:
            return self._owner

    def try_begin(self, owner: str) -> bool:
        if not owner:
            raise ValueError("Operation owner must be a non-empty string.")
        with self._lock:
            if self._owner is not None:
                return False
            self._owner = owner
            return True

    def finish(self, owner: str) -> bool:
        with self._lock:
            if self._owner != owner:
                return False
            self._owner = None
            return True
