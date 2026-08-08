import os
import logging
import string
import json
import av
import numpy as np
from PySide6.QtCore import QThread, Signal
from src.engine.engine_manager import engine_manager
from src.config import config_manager
from src.i18n import translate
from src.engine.stt_base import TranscriptionCancelled

logger = logging.getLogger("PrimeDictate.FileTranscriber")


def _subtitle_timestamp(seconds: float, separator: str = ",") -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def segments_to_srt(segments) -> str:
    blocks = []
    for index, segment in enumerate(segments, 1):
        blocks.append(
            f"{index}\n{_subtitle_timestamp(segment['start'])} --> "
            f"{_subtitle_timestamp(segment['end'])}\n{segment['text']}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def segments_to_vtt(segments) -> str:
    blocks = ["WEBVTT"]
    for segment in segments:
        blocks.append(
            f"{_subtitle_timestamp(segment['start'], '.')} --> "
            f"{_subtitle_timestamp(segment['end'], '.')}\n{segment['text']}"
        )
    return "\n\n".join(blocks) + "\n"


def segments_to_json(segments) -> str:
    return json.dumps({"segments": segments}, ensure_ascii=False, indent=2) + "\n"

class FileTranscribeWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(str, str)  # (file_path, transcribed_text)
    error = Signal(str)
    cancelled = Signal()

    CHUNK_SECONDS = 30
    OVERLAP_SECONDS = 1
    TARGET_SAMPLE_RATE = 16000
    MIN_LANGUAGE_CONFIDENCE = 0.60

    def __init__(self, file_path: str, parent=None, engine=None):
        super().__init__(parent)
        self.file_path = file_path
        self.engine = engine or engine_manager
        self.segments = []

    def run(self):
        try:
            if not os.path.exists(self.file_path):
                self.error.emit(translate("file.error.not_found", path=self.file_path))
                return

            self.progress.emit(5, translate("file.progress.preparing_media"))
            text_parts = []
            chunk_lengths = []
            configured_language = config_manager.get("language", "tr")
            detected_language = None
            for chunk, percent in self._iter_audio_chunks():
                if self.isInterruptionRequested():
                    self.cancelled.emit()
                    return
                self.progress.emit(percent, translate("file.progress.transcribing_chunk"))
                language_override = detected_language if configured_language == "auto" else None
                text = self.engine.process_audio(
                    chunk,
                    sample_rate=self.TARGET_SAMPLE_RATE,
                    language_override=language_override,
                    cancel_check=self.isInterruptionRequested,
                    apply_text_processing=False,
                )
                if configured_language == "auto" and detected_language is None:
                    info = self.engine.last_transcription_info
                    candidate_language = info.get("detected_language")
                    confidence = info.get("language_probability")
                    if candidate_language and isinstance(confidence, (float, int)) and confidence >= self.MIN_LANGUAGE_CONFIDENCE:
                        detected_language = candidate_language
                        logger.info("File language locked to '%s' after the first chunk.", detected_language)
                if text:
                    text_parts.append(text)
                    chunk_lengths.append(len(chunk))

            if self.isInterruptionRequested():
                self.cancelled.emit()
                return

            text = self._merge_text_parts(text_parts)
            self.segments = self._build_segments(text_parts, chunk_lengths)
            if not text:
                raise RuntimeError(translate("file.error.no_speech"))

            self.progress.emit(95, translate("file.progress.processing_text"))
            text = self.engine.process_text(text, cancel_check=self.isInterruptionRequested)
            if self.isInterruptionRequested():
                self.cancelled.emit()
                return

            self.progress.emit(100, translate("file.progress.complete"))
            self.completed.emit(self.file_path, text)
        except TranscriptionCancelled:
            self.cancelled.emit()
        except Exception as e:
            logger.error(f"Error transcribing file {self.file_path}: {e}")
            self.error.emit(str(e))

    def _iter_audio_chunks(self):
        chunk_size = self.CHUNK_SECONDS * self.TARGET_SAMPLE_RATE
        overlap_size = self.OVERLAP_SECONDS * self.TARGET_SAMPLE_RATE
        step_size = chunk_size - overlap_size
        pending_parts = []
        pending_length = 0
        emitted_chunk = False

        def add_samples(samples):
            nonlocal pending_parts, pending_length
            if len(samples):
                pending_parts.append(samples)
                pending_length += len(samples)

        def take_full_chunks():
            nonlocal pending_parts, pending_length, emitted_chunk
            chunks = []
            if pending_length < chunk_size:
                return chunks
            pending = np.concatenate(pending_parts)
            while len(pending) >= chunk_size:
                chunks.append(pending[:chunk_size])
                pending = pending[step_size:]
                emitted_chunk = True
            pending_parts = [pending] if len(pending) else []
            pending_length = len(pending)
            return chunks

        with av.open(self.file_path) as container:
            stream = next((item for item in container.streams if item.type == "audio"), None)
            if stream is None:
                raise RuntimeError(translate("file.error.no_audio_stream"))

            duration_seconds = None
            if stream.duration is not None and stream.time_base is not None:
                duration_seconds = float(stream.duration * stream.time_base)

            resampler = av.AudioResampler(
                format="fltp",
                layout="mono",
                rate=self.TARGET_SAMPLE_RATE,
            )
            processed_samples = 0

            for frame in container.decode(stream):
                if self.isInterruptionRequested():
                    return
                for resampled in resampler.resample(frame):
                    samples = resampled.to_ndarray().reshape(-1).astype(np.float32, copy=False)
                    add_samples(samples)
                    for chunk in take_full_chunks():
                        processed_samples += chunk_size if processed_samples == 0 else step_size
                        yield chunk, self._calculate_progress(processed_samples, duration_seconds)

            for resampled in resampler.resample(None):
                add_samples(resampled.to_ndarray().reshape(-1).astype(np.float32, copy=False))
                for chunk in take_full_chunks():
                    processed_samples += chunk_size if processed_samples == 0 else step_size
                    yield chunk, self._calculate_progress(processed_samples, duration_seconds)

            pending = np.concatenate(pending_parts) if pending_parts else np.array([], dtype=np.float32)
            has_new_tail = len(pending) > (overlap_size if emitted_chunk else 0)
            if has_new_tail:
                processed_samples += len(pending) - (overlap_size if emitted_chunk else 0)
                yield pending, self._calculate_progress(processed_samples, duration_seconds)

    @staticmethod
    def _merge_text_parts(parts):
        merged_words = []
        punctuation = string.punctuation + "“”‘’…"
        for part in parts:
            words = part.split()
            if not words:
                continue
            max_overlap = min(40, len(merged_words), len(words))
            overlap = 0
            for size in range(max_overlap, 0, -1):
                left = [word.strip(punctuation).casefold() for word in merged_words[-size:]]
                right = [word.strip(punctuation).casefold() for word in words[:size]]
                if left == right:
                    overlap = size
                    break
            merged_words.extend(words[overlap:])
        return " ".join(merged_words).strip()

    def _build_segments(self, parts, chunk_lengths):
        segments = []
        merged_words = []
        step_seconds = self.CHUNK_SECONDS - self.OVERLAP_SECONDS
        punctuation = string.punctuation + "“”‘’…"
        for index, (part, sample_count) in enumerate(zip(parts, chunk_lengths)):
            words = part.split()
            max_overlap = min(40, len(merged_words), len(words))
            overlap = 0
            for size in range(max_overlap, 0, -1):
                left = [word.strip(punctuation).casefold() for word in merged_words[-size:]]
                right = [word.strip(punctuation).casefold() for word in words[:size]]
                if left == right:
                    overlap = size
                    break
            unique_words = words[overlap:]
            merged_words.extend(unique_words)
            if not unique_words:
                continue
            start = index * step_seconds
            end = start + sample_count / self.TARGET_SAMPLE_RATE
            segments.append({
                "start": round(start, 3),
                "end": round(end, 3),
                "text": " ".join(unique_words),
            })
        return segments

    def _calculate_progress(self, processed_samples: int, duration_seconds) -> int:
        if not duration_seconds:
            return 55
        ratio = min(1.0, processed_samples / (duration_seconds * self.TARGET_SAMPLE_RATE))
        return min(92, 10 + int(ratio * 82))
