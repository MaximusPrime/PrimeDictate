# PrimeDictate Architecture

This document describes the runtime boundaries, component contracts, data flow, persistence model, and packaging architecture of PrimeDictate `1.0.0`.

## Design Goals

PrimeDictate is built around the following invariants:

1. Speech recognition and transcript processing are independent stages.
2. Local processing must never silently become cloud processing.
3. Cloud fallback requires explicit persisted user consent.
4. API credentials must not be stored in plaintext configuration.
5. Clipboard injection must target the window captured before recording.
6. UI work remains on the Qt thread; recording, inference, downloads, and media decoding do not block it.
7. Installed and portable editions use the same per-user storage contract.

## Runtime Topology

```text
PrimeDictateApp
|-- QApplication
|-- MainWindow
|-- FloatingOverlay
|-- SystemTrayManager
|-- HotkeyListener
|-- AudioRecorder
|-- EngineManager
|   |-- CPUSTTEngine
|   |-- CUDASTTEngine
|   |-- VulkanSTTEngine
|   `-- CloudSTTEngine
|-- AICleanupEngine
`-- PasteInjector
```

`run.py` owns the application state machine and coordinates these long-lived services.

## Application State Machine

The controller uses five states:

```text
IDLE
  -> RECORDING
  -> TRANSCRIBING
  -> SUCCESS
  -> IDLE

Any active stage
  -> ERROR
  -> IDLE
```

The main action button and tray route through the controller toggle operation. The global hotkey uses explicit start and stop callbacks, while the overlay exposes only a stop callback during recording. All paths converge on the same controller state machine, and recording state is synchronized back to the hotkey listener.

## Live Dictation Flow

```text
1. User invokes the global hotkey.
2. PasteInjector captures the current foreground HWND.
3. AudioRecorder opens the selected input device.
4. Live levels are emitted to MainWindow and FloatingOverlay.
5. Recording stops through toggle or key release.
6. Audio is resampled to 16 kHz mono float32.
7. VAD trims silence and rejects non-meaningful recordings.
8. EngineManager dispatches to the selected STT backend.
9. AICleanupEngine optionally processes the raw transcript.
10. The final text returns to the Qt thread through a signal.
11. PasteInjector restores the captured target and sends Ctrl+V only if focus validation succeeds.
12. The transcript may be added to local history.
```

Audio processing runs in a daemon worker thread. Qt widgets are updated only through signals connected to the main thread.

## STT Engine Contract

All STT engines implement `BaseSTTEngine`:

```python
load_model(model_name: str, language: str) -> None
transcribe(audio: np.ndarray, sample_rate: int, language: str) -> str
```

Shared metadata fields:

```text
last_detected_language
last_language_probability
```

The engine may leave these fields unset if the backend does not expose trustworthy metadata.

`BaseSTTEngine.prepare_audio()` converts non-16 kHz arrays before faster-whisper inference. Cloud and Vulkan paths preserve the declared sample rate in their encoded WAV input.

### Language Validation

`EngineManager` accepts `auto` or a code declared in `STT_LANGUAGES`. Invalid persisted values are logged and replaced with `auto` before reaching an engine or provider.

### CPU and CUDA

Both use faster-whisper with multilingual model identifiers. `auto` is translated to `language=None`, allowing faster-whisper to detect the language.

CPU uses `int8`. CUDA attempts `float16` first and falls back to CUDA `int8` model loading. CUDA transcription exceptions are re-raised so `EngineManager` can apply the same user-approved fallback policy as other local engines.

### Vulkan

The Vulkan backend executes a pinned whisper.cpp CLI in a temporary directory. It writes an input WAV, requests text output without timestamps, reads the generated transcript, and deletes temporary files with the directory context.

Before model use, the backend:

1. Locates the bundled or user-selected CLI.
2. Verifies the optional SHA-256 manifest.
3. Inspects CLI help output for whisper.cpp and Vulkan indicators.
4. Identifies the reported Vulkan device.
5. Resolves the corresponding GGML model.

### Cloud STT

`CloudSTTEngine` converts the audio array into an in-memory PCM16 WAV. No temporary audio file is required.

Provider behavior:

| Provider | Transport | Language behavior |
|---|---|---|
| Groq | Multipart HTTP | ISO language code omitted for `auto` |
| OpenAI | Python SDK | Request field depends on recognized model family |
| Gemini | JSON with inline base64 audio | Language is expressed in the transcription instruction |

For known OpenAI model families, PrimeDictate selects the compatible language request shape. Unknown custom model names receive no language hint instead of an assumed incompatible field.

Cloud error logs intentionally omit API keys, raw audio, response bodies, and raw exception messages. Safe diagnostic fields include provider, HTTP status, exception class, and request ID when available.

## Fallback Policy

Fallback is implemented in `EngineManager`, not in individual local engines.

```text
Local engine succeeds -> return local transcript
Local engine fails + fallback disabled -> return failure
Local engine fails + fallback enabled -> call configured cloud STT
Cloud engine selected directly -> no secondary implicit provider
```

An empty local transcript is not automatically treated as an exception requiring upload. This prevents silence or unrecognized speech from silently causing a cloud transfer.

## Text-Processing Stage

`AICleanupEngine.clean_text()` receives only transcript text.

Dispatch options:

```text
rule_based     Local regular expressions and formatting
custom_ollama OpenAI-compatible local endpoint
groq          Groq chat completions
openai        OpenAI chat completions
gemini        Gemini generateContent
grok          xAI OpenAI-compatible endpoint
```

When processing is disabled, the stripped raw transcript is returned. When an LLM provider fails or lacks credentials, the current implementation falls back to local rule-based cleanup rather than discarding the transcript.

Preset prompts preserve the transcript language unless the selected profile explicitly requests translation.

## File Transcription

`FileTranscribeWorker` is a cooperatively cancellable `QThread`. Cancellation is propagated through `EngineManager` without triggering cloud fallback. CPU/CUDA check between decoded segments, Vulkan terminates its active subprocess, and cloud requests check cancellation before dispatch and after the blocking provider call returns.

PyAV decodes the selected media stream and resamples it to mono 16 kHz. Pending samples are emitted in bounded 30-second chunks. Progress is calculated from stream duration when available.

If language is `auto`, the first detected language with probability at or above `0.60` is passed as an override for later chunks. Lower-confidence results and engines without probability metadata continue using automatic behavior.

Each chunk currently passes through the same optional text-processing stage as live dictation. This is relevant for transformative profiles such as summarization.

## Clipboard Safety

`PasteInjector` captures a target HWND before microphone capture begins.

The insertion sequence is:

1. Store the existing clipboard value when restoration is enabled.
2. Copy the final transcript.
3. Validate that the target HWND still exists.
4. Request foreground focus for the target.
5. Verify that the foreground window matches the target.
6. Send `Ctrl+V` only after successful verification.
7. Restore the previous plain-text clipboard value after the configured delay.

If focus verification fails, the transcript remains on the clipboard and no keystroke is sent.

Clipboard backup uses `pyperclip` and therefore preserves only plain text. Images, file lists, HTML, rich text, and other Windows clipboard formats are outside this restoration contract.

## Configuration and Secrets

`ConfigManager` merges persisted values with `DEFAULT_CONFIG` and performs small migrations for obsolete settings.

Files:

```text
%APPDATA%\PrimeDictate\config.json
%APPDATA%\PrimeDictate\history.json
%APPDATA%\PrimeDictate\models\faster-whisper\
%APPDATA%\PrimeDictate\models\whisper.cpp\
```

Writes to JSON files use a temporary file, flush, `fsync`, and `os.replace` to reduce partial-write risk.

Secret keys are intercepted by `ConfigManager.get()`, `set()`, and `update()` and stored as generic Windows credentials under the `PrimeDictate/` target prefix. Secret keys are filtered from serialized configuration.

## Localization

`src/i18n.py` contains the Turkish-English runtime catalog. The UI language is independent from the spoken-language setting.

Main window widgets are translated after construction and can be retranslated after settings are saved. Dynamic controller, overlay, tray, model-download, file-worker, and selected engine messages use the same translation function.

The language catalog supports reverse lookup so an existing English widget tree can be switched back to Turkish without recreating the application.

## UI Information Architecture

`MainWindow.PAGE_DEFINITIONS` is the canonical page registry. Navigation buttons, stacked pages, headers, and footer visibility are derived from this single ordered source.

Current pages:

```text
Home
Speech to Text
Text Processing & API
File Transcription
Audio & Shortcuts
History
Diagnostics
About
```

Conditional controls are tied to active capability:

- Local model controls are hidden for cloud STT.
- Cloud STT controls appear for direct cloud use or local fallback.
- LLM profile fields are hidden for rule-based processing.
- Only credentials required by active providers are shown.

## Overlay Geometry

`FloatingOverlay` is a fixed-size, non-focus-accepting tool window.

At first use it selects the screen under the cursor and positions itself above the bottom-center of the available geometry. Stored coordinates are clamped to a valid connected display on load, show, drag, and release. A successful drag persists the final position.

The overlay stylesheet is scoped by object name to prevent child-style leakage.

## Persistence and Privacy Boundaries

| Data | Storage or destination |
|---|---|
| General settings | Per-user JSON |
| API credentials | Windows Credential Manager |
| Optional history | Per-user JSON |
| Local models | Per-user models directory |
| Local STT audio | Process memory and temporary runtime input where required |
| Cloud STT audio | Selected provider |
| Cloud LLM input | Transcript text only |

Portable packaging changes executable delivery, not this storage contract.

## Build Architecture

`src/metadata.py` is the canonical Python metadata source for application name, version, publisher, website, email, and repository.

`build.py` creates Windows version resources and invokes PyInstaller for one-file and onedir targets. If Inno Setup is installed, it then compiles `installer.iss` against the onedir output.

Both PyInstaller specs include:

```text
PrimeDictate-Logo.png
assets/maximus-prime-software.png
runtime/
```

The pinned Vulkan runtime includes its own upstream license, provenance record, and checksum manifest.

## Test Strategy

Core tests cover:

- Rule-based cleanup
- Independent text-processing models
- Cloud provider request contracts
- Safe provider error logging
- Language validation
- Approved and denied cloud fallback
- Detected-language metadata
- Bounded media decoding
- Automatic file-language locking
- Credential serialization safety
- Clipboard focus safety
- Vulkan command construction

UI tests cover:

- Single-source page registry consistency
- Local/cloud control visibility
- Turkish-English catalog round trips
- Full Whisper language list exposure
- Overlay geometry clamping
- Studio asset declarations in build paths

## Extension Guidelines

When adding an STT provider:

1. Implement the `BaseSTTEngine` contract or extend cloud dispatch deliberately.
2. Define whether audio leaves the device.
3. Define exact language-field behavior.
4. Sanitize provider errors.
5. Add UI capability text and credential visibility rules.
6. Add request-contract and privacy tests.

When adding a UI page:

1. Add one entry to `PAGE_DEFINITIONS`.
2. Add the page factory method.
3. Add Turkish-English catalog entries.
4. Add a page-registry regression test if behavior changes.

When adding persisted secrets, include the key in `SECRET_KEYS`; otherwise it can be serialized as plaintext.
