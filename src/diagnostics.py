"""Privacy-safe support bundle generation."""

import json
import os
import platform
import sys
import zipfile

from src import __version__
from src.logging_config import SensitiveDataFilter


SAFE_CONFIG_KEYS = (
    "ui_language",
    "stt_backend",
    "model_size",
    "language",
    "cloud_stt_provider",
    "ai_cleanup_enabled",
    "ai_cleanup_provider",
    "allow_cloud_fallback",
    "max_recording_seconds",
)


def create_diagnostics_bundle(destination, config, capabilities=None, log_dir=None):
    report = {
        "application": {"name": "PrimeDictate", "version": __version__},
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "architecture": platform.machine(),
            "frozen": bool(getattr(sys, "frozen", False)),
        },
        "configuration": {key: config.get(key, None) for key in SAFE_CONFIG_KEYS},
        "backends": {},
        "privacy": {
            "contains_api_keys": False,
            "contains_history": False,
            "contains_transcripts": False,
        },
    }
    for backend, capability in (capabilities or {}).items():
        report["backends"][backend] = {
            "available": bool(getattr(capability, "available", False)),
            "device": str(getattr(capability, "device_name", "")),
            "detail": str(getattr(capability, "detail", "")),
        }

    redactor = SensitiveDataFilter()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", json.dumps(report, ensure_ascii=False, indent=2))
        if log_dir and os.path.isdir(log_dir):
            for file_name in sorted(os.listdir(log_dir)):
                if not file_name.startswith("PrimeDictate.log"):
                    continue
                source_path = os.path.join(log_dir, file_name)
                if not os.path.isfile(source_path):
                    continue
                with open(source_path, "r", encoding="utf-8", errors="replace") as log_file:
                    safe_log = "".join(redactor.redact(line) for line in log_file)
                archive.writestr(f"logs/{file_name}", safe_log)
    return destination
