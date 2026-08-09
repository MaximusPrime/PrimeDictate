"""Own the lifecycle of background file-transcription workers."""

from PySide6.QtCore import QObject, Signal

from src.engine.file_transcriber import FileTranscribeWorker


class FileTranscriptionController(QObject):
    progress = Signal(int, str)
    completed = Signal(str, str)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.worker = None
        self.segments = []

    def start(self, file_path: str):
        if self.worker is not None and self.worker.isRunning():
            raise RuntimeError("A file transcription is already running.")
        worker = FileTranscribeWorker(file_path, engine=self.engine)
        self.worker = worker
        self.segments = []
        worker.progress.connect(self.progress)
        worker.completed.connect(self._on_completed)
        worker.error.connect(self.error)
        worker.cancelled.connect(self.cancelled)
        worker.finished.connect(lambda worker=worker: self._release(worker))
        worker.start()

    def cancel(self) -> bool:
        worker = self.worker
        if worker is None or not worker.isRunning():
            return False
        worker.requestInterruption()
        return True

    def shutdown(self, timeout_ms: int = 10000) -> bool:
        worker = self.worker
        if worker is None or not worker.isRunning():
            return True
        worker.requestInterruption()
        if not worker.wait(timeout_ms):
            return False
        if self.worker is worker:
            self.worker = None
        worker.deleteLater()
        return True

    def _on_completed(self, file_path: str, text: str):
        self.segments = list(getattr(self.worker, "segments", []))
        self.completed.emit(file_path, text)

    def _release(self, worker):
        if self.worker is not worker:
            return
        self.worker = None
        worker.deleteLater()
