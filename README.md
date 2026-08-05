<p align="center">
  <img src="PrimeDictate-Logo.png" alt="PrimeDictate Logo" width="128"/>
</p>

<h1 align="center">PrimeDictate Pro</h1>

<p align="center">
  <b>System-wide Speech-to-Text & AI Voice Assistant Application for Windows</b><br/>
  <i>Hardware-Accelerated for AMD GPUs (DirectML), NVIDIA GPUs (CUDA), Vulkan, and CPU, with Local/Cloud LLM AI Assistant & Rule Engine.</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=flat-square&logo=windows" alt="Windows"/>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/UI-PySide6-41CD52?style=flat-square&logo=qt" alt="PySide6"/>
  <img src="https://img.shields.io/badge/AMD_GPU-DirectML-ED1C24?style=flat-square&logo=amd" alt="AMD GPU"/>
  <img src="https://img.shields.io/badge/NVIDIA_GPU-CUDA-76B900?style=flat-square&logo=nvidia" alt="NVIDIA GPU"/>
  <img src="https://img.shields.io/badge/Ollama-Local_LLM-000000?style=flat-square" alt="Ollama"/>
  <img src="https://img.shields.io/badge/License-GPL--3.0-blue?style=flat-square" alt="License"/>
</p>

---

## 🚀 Key Features

- 🎙️ **System-wide Global Dictation**: Press a custom hotkey (`Ctrl+Alt+D` or `F9`) from any window to record voice and auto-paste clean text instantly.
- 🧠 **AI Assistant & Command Mode**: Switch from standard dictation to **AI Assistant Mode** to issue spoken commands (*"Summarize this text"*, *"Translate to English"*, *"Write a formal email"*). PrimeDictate executes your spoken instruction via AI and pastes the answer into your focused window!
- 📝 **5 Preset Prompt Rule Templates & Custom Rules**:
  - 📝 **Standard Dictation Cleanup**: Strips "eee", "hmmm", "yani", "şey" hesitation sounds, fixes punctuation and capitalization.
  - 💼 **Formal Business Language**: Rewrites spoken voice into polished, professional corporate correspondence.
  - 💻 **Coding & Tech Term Protection**: Preserves technical jargon, library names, and `CamelCase` / `snake_case` code variables.
  - 🌐 **Instant English Translation**: Translates Turkish spoken voice instantly to fluent English text.
  - 📊 **Summarize & Bullet Points**: Summarizes long audio into structured bullet points.
  - ✏️ **Custom User Rules**: Define your own custom AI instructions and rules.
- ⚡ **Multi-Hardware STT Acceleration**:
  - **AMD GPUs**: Native DirectX 12 DirectML hardware acceleration for Radeon RX GPUs & Ryzen APUs.
  - **NVIDIA GPUs**: CUDA & cuDNN (float16 / int8).
  - **Vulkan & CPU**: Cross-platform Vulkan compute shaders and multi-core CPU fallbacks.
  - **Cloud STT**: Sub-0.3s transcription via Groq Whisper API or OpenAI Whisper.
- 🌐 **Local & Custom LLM Support (Ollama / LM Studio / OpenRouter)**:
  - Connect to local AI models running on **Ollama** (`http://localhost:11434/v1`), **LM Studio**, or **OpenRouter** (`llama3.2`, `qwen2.5-coder`, `mistral`).
  - Native support for **Google Gemini 2.5 Flash**, **xAI Grok (Grok-Beta)**, **Groq (Llama 3.3 70B)**, and **OpenAI (GPT-4o Mini)**.
- 📁 **Audio & Video File Transcriber**: Dedicated tab to transcribe `.mp3`, `.wav`, `.mp4`, `.m4a`, `.mkv` media files into formatted text or subtitles.
- 📥 **Async Local Model Downloader**: Progress bar (%0-%100) manager to check and download local HuggingFace Whisper models (`tiny`, `base`, `small`, `medium`, `turbo`) safely.
- 🔒 **Clipboard Auto-Paste & Restoration**: Safely pastes via `Ctrl+V` and automatically restores your previous clipboard content after 0.6s.
- 🛠️ **Dev Mode Live Diagnostic Console**: Live log stream tab for debugging audio devices, sample rates, model downloads, and API responses.
- 🌊 **Floating Audio Wave Visualizer**: Position-remembering, frameless, semi-transparent overlay pill showing live volume waves and state.
- 📌 **System Tray Integration**: Background operation with quick access tray menu.

---

## 🛠️ Installation & Quick Start

### Prerequisites
- Windows 10 / 11 (64-bit)
- Python 3.12+

### Setup & Run Source Code

```bash
# Clone the repository
git clone https://github.com/MaximusPrime/PrimeDictate.git
cd PrimeDictate

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run PrimeDictate
python run.py
```

---

## 📦 Building Executables (Portable & Setup)

PrimeDictate includes an automated build script to generate standalone Windows binaries:

```bash
# Run build script to generate Portable & Setup packages
python build.py
```

### Outputs in `dist/`:
1. **Portable Edition (`dist/PrimeDictate-Portable.exe`)**:
   - Standalone `.exe` file running without installation.
2. **Windows Installer Setup (`dist/PrimeDictate-Setup.exe`)**:
   - Complete setup wizard created via Inno Setup (`ISCC.exe`).

---

## 📐 Architecture Overview

```
PrimeDictate/
├── run.py                          # Main Entry Point & App Controller
├── build.py                        # Automated Executable Builder (Portable & Setup)
├── installer.iss                   # Inno Setup Wizard Script
├── requirements.txt                # Python Dependencies
├── PrimeDictate-Logo.png           # App Branding Logo
└── src/
    ├── config.py                   # App Configuration Manager & Prompt Presets
    ├── audio/
    │   ├── recorder.py             # Low-latency Audio Stream & Resampler (44.1/48kHz -> 16kHz)
    │   └── vad.py                  # Voice Activity Detection & Micro-Recording Filter
    ├── engine/
    │   ├── engine_manager.py       # STT Engine Manager (CUDA/DirectML/Vulkan/Cloud)
    │   ├── model_manager.py        # HuggingFace Model Downloader & Progress Manager
    │   ├── file_transcriber.py     # Audio & Video File Transcription Worker
    │   ├── stt_cuda.py             # NVIDIA GPU CUDA Engine
    │   ├── stt_directml.py         # AMD GPU DirectML Engine
    │   ├── stt_vulkan.py           # Vulkan Engine
    │   ├── stt_cloud.py            # Groq & OpenAI Cloud STT Engine
    │   └── ai_cleanup.py           # Multi-LLM AI Text Cleaner & Ollama Endpoint Client
    ├── hotkey/
    │   └── listener.py             # Win32 Global Hotkey Listener
    ├── injector/
    │   └── paste_injector.py       # Safe Clipboard & Active Window Injector
    └── ui/
        ├── main_window.py          # PySide6 Control Panel, AI Rules & File Transcriber UI
        ├── floating_overlay.py     # Position-Remembering Audio Visualizer Overlay Pill
        ├── styles.py               # Dark Glassmorphism Qt Stylesheet
        └── tray_icon.py            # Windows System Tray Integration
```

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)** - see the [LICENSE](LICENSE) file for details.
