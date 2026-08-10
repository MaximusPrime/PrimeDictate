"""Temporarily mute Windows output sessions while live dictation is active."""

import logging
import os
import threading

logger = logging.getLogger("PrimeDictate.AudioSilencer")


class AudioSessionSilencer:
    """Mute existing output sessions and restore each session's prior state."""

    def __init__(self, session_provider=None):
        self._session_provider = session_provider
        self._lock = threading.RLock()
        self._muted = {}

    def _sessions(self):
        if self._session_provider is not None:
            return self._session_provider()
        from pycaw.pycaw import AudioUtilities
        return AudioUtilities.GetAllSessions()

    def mute(self) -> bool:
        if os.name != "nt" and self._session_provider is None:
            return False
        with self._lock:
            if self._muted:
                return True
            try:
                for session in self._sessions():
                    if getattr(session, "ProcessId", None) == os.getpid():
                        continue
                    try:
                        volume = session.SimpleAudioVolume
                        identifier = getattr(session, "InstanceIdentifier", None) or id(session)
                        was_muted = bool(volume.GetMute())
                        self._muted[identifier] = (volume, was_muted)
                        if not was_muted:
                            volume.SetMute(1, None)
                    except Exception:
                        logger.debug("Could not mute one Windows audio session.", exc_info=True)
                return True
            except Exception:
                logger.warning("Windows audio sessions could not be muted.", exc_info=True)
                self.restore()
                return False

    def restore(self):
        with self._lock:
            saved, self._muted = self._muted, {}
            for volume, was_muted in saved.values():
                try:
                    volume.SetMute(int(was_muted), None)
                except Exception:
                    logger.debug("Could not restore one Windows audio session.", exc_info=True)
