"""Central logging configuration with bounded files and secret redaction."""

import logging
from logging.handlers import RotatingFileHandler
import os
import re


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FILE_NAME = "PrimeDictate.log"


class SensitiveDataFilter(logging.Filter):
    _patterns = (
        (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
        (re.compile(r"(?i)((?:api[_ -]?key|token|secret)\s*[:=]\s*)[^\s,;]+"), r"\1[REDACTED]"),
        (re.compile(r"\b(?:sk|xai)-[A-Za-z0-9_-]{12,}\b"), "[REDACTED]"),
        (re.compile(r"\bgsk_[A-Za-z0-9_-]{12,}\b"), "[REDACTED]"),
        (re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"), "[REDACTED]"),
    )

    def __init__(self):
        super().__init__()
        user_profile = os.path.expanduser("~")
        self._profile_pattern = (
            re.compile(re.escape(user_profile), re.IGNORECASE)
            if user_profile and user_profile not in {"~", os.path.sep}
            else None
        )

    def redact(self, value) -> str:
        text = str(value)
        for pattern, replacement in self._patterns:
            text = pattern.sub(replacement, text)
        if self._profile_pattern:
            text = self._profile_pattern.sub("%USERPROFILE%", text)
        return text

    def filter(self, record):
        record.msg = self.redact(record.getMessage())
        record.args = ()
        return True


def configure_logging(app_dir: str, level=logging.INFO) -> str:
    log_dir = os.path.join(app_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, LOG_FILE_NAME)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT)
    redaction_filter = SensitiveDataFilter()

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction_filter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(SensitiveDataFilter())
    root.addHandler(stream_handler)
    return log_path
