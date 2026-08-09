"""Background orchestration for provider credential/model discovery tests."""

import threading

from PySide6.QtCore import QObject, Signal


class ProviderTestController(QObject):
    completed = Signal(object, object)

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self._catalog = catalog

    def start(self, provider: str, key: str, context=None):
        def worker():
            result = self._catalog.discover(provider, key)
            self.completed.emit(result, context)

        threading.Thread(
            target=worker,
            daemon=True,
            name=f"ProviderTest-{provider}",
        ).start()
