<p align="center">
  <img src="PrimeDictate-Logo.png" alt="PrimeDictate Logo" width="128"/>
</p>

<h1 align="center">PrimeDictate</h1>

<p align="center">
  <b>System-wide Speech-to-Text & AI Voice Typing Application for Windows</b><br/>
  <i>Hardware-Accelerated for AMD GPUs (DirectML), NVIDIA GPUs (CUDA), Vulkan, and CPU, with Multi-LLM AI Text Cleanup.</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=flat-square&logo=windows" alt="Windows"/>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/UI-PySide6-41CD52?style=flat-square&logo=qt" alt="PySide6"/>
  <img src="https://img.shields.io/badge/AMD_GPU-DirectML-ED1C24?style=flat-square&logo=amd" alt="AMD GPU"/>
  <img src="https://img.shields.io/badge/NVIDIA_GPU-CUDA-76B900?style=flat-square&logo=nvidia" alt="NVIDIA GPU"/>
  <img src="https://img.shields.io/badge/Vulkan-Cross--GPU-E23126?style=flat-square&logo=vulkan" alt="Vulkan"/>
  <img src="https://img.shields.io/badge/License-GPL--3.0-blue?style=flat-square" alt="License"/>
</p>

---

## 🚀 Key Features

- 🎙️ **System-wide Global Dictation**: Press a custom hotkey (`Ctrl+Alt+D` or `F9`) from any application to record voice and auto-paste clean text instantly.
- ⚡ **Multi-Hardware STT Acceleration**:
  - **AMD GPUs**: Accelerated via Microsoft DirectML (DirectX 12) for all Radeon RX & Ryzen APUs.
  - **NVIDIA GPUs**: Accelerated via CUDA & cuDNN (float16 / int8).
  - **Vulkan & CPU**: Cross-platform Vulkan compute shaders and multi-core CPU fallbacks.
  - **Cloud STT**: Sub-0.3s transcription using Groq Whisper API or OpenAI Whisper.
- 🤖 **Multi-LLM AI Text Cleanup**:
  - Automatically strips hesitation sounds ("eee", "hmmm", "yani", "şey") and fixes grammar & punctuation.
  - Supports **Google Gemini 2.5 Flash**, **xAI Grok (Grok-Beta)**, **Groq (Llama 3.3 70B)**, **OpenAI (GPT-4o Mini)**, or local rule-based engine.
- 💬 **Clipboard Auto-Paste**: Safely copies text to clipboard and triggers synthetic `Ctrl+V` to inject into active windows (Notepad, Word, VS Code, Browser, WhatsApp, etc.).
- 🌊 **Floating Audio Wave Visualizer**: Draggable, frameless, semi-transparent overlay pill showing live microphone volume waves and transcription state.
- 📌 **System Tray Integration**: Quiet background operation with quick access context menu.

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
   - Single standalone `.exe` file.
   - Runs instantly without installation. Ideal for USB drives or quick deployment.
2. **Setup / Installer Package (`dist/PrimeDictate-Setup-v1.0.zip`)**:
   - Complete application directory containing `PrimeDictate.exe` and dynamic libraries.
   - Can be distributed as a zip or packaged with installer creators like Inno Setup or NSIS.

---

## ⚙️ Configuration & Usage

1. Launch PrimeDictate (`python run.py` or double-click `PrimeDictate-Portable.exe`).
2. The control panel window will open and the system tray icon will appear.
3. Focus any text input window (Notepad, VS Code, Word, Chrome).
4. Press **`Ctrl+Alt+D`** (or your configured shortcut) to start recording.
5. Speak into your microphone and press the shortcut again (or release the key).
6. PrimeDictate will transcribe, clean, and auto-paste the text into your active window.

---

## 📐 Architecture Overview

```
PrimeDictate/
├── run.py                          # Main Entry Point & App Controller
├── build.py                        # Automated Executable Builder (Portable & Setup)
├── requirements.txt                # Python Dependencies
├── PrimeDictate-Logo.png           # App Branding Logo
└── src/
    ├── config.py                   # App Configuration Manager
    ├── audio/
    │   ├── recorder.py             # Low-latency Audio Stream & RMS Meter
    │   └── vad.py                  # Voice Activity Detection & Silence Trimming
    ├── engine/
    │   ├── engine_manager.py       # STT Engine Manager (CUDA/DirectML/Vulkan/Cloud)
    │   ├── stt_cuda.py             # NVIDIA GPU CUDA Engine
    │   ├── stt_directml.py         # AMD GPU DirectML Engine
    │   ├── stt_vulkan.py           # Vulkan Engine
    │   ├── stt_cloud.py            # Groq & OpenAI Cloud STT Engine
    │   └── ai_cleanup.py           # AI Text Cleaner (Gemini/Grok/Groq/OpenAI)
    ├── hotkey/
    │   └── listener.py             # Win32 Global Hotkey Listener
    ├── injector/
    │   └── paste_injector.py       # Safe Clipboard & Ctrl+V Injector
    └── ui/
        ├── main_window.py          # PySide6 Control Panel & Settings UI
        ├── floating_overlay.py     # Floating Audio Visualizer Overlay Pill
        ├── styles.py               # Dark Glassmorphism Qt Stylesheet
        └── tray_icon.py            # Windows System Tray Integration
```

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)** - see the [LICENSE](LICENSE) file for details.
