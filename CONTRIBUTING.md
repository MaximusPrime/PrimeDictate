# Contributing to PrimeDictate

Thank you for considering a contribution to PrimeDictate.

PrimeDictate handles microphone input, clipboard injection, local model execution, and optional cloud transfers. Changes in these areas require explicit attention to privacy, failure behavior, and Windows-specific integration.

## Before You Start

- Search existing issues before opening a duplicate.
- Use a focused branch for one logical change.
- Do not include API keys, credentials, private transcripts, model files, build outputs, or user configuration.
- For security vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Development Environment

Required:

- Windows 10 or Windows 11, 64-bit
- Python 3.12
- Git

Setup:

```powershell
git clone https://github.com/MaximusPrime/PrimeDictate.git
Set-Location PrimeDictate

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run:

```powershell
python run.py
```

## Engineering Principles

### Preserve explicit cloud consent

Local processing must not upload audio after failure unless `allow_cloud_fallback` is explicitly enabled by the user. New fallback behavior must include tests for both consent states.

### Keep STT and text processing independent

An STT provider converts audio to text. A text-processing provider receives transcript text. UI labels, configuration keys, and runtime code must not collapse these stages into one ambiguous “AI model” setting.

### Protect credentials and diagnostics

New secrets must be added to `SECRET_KEYS` and stored through `ConfigManager`. Logs and exceptions must not contain API keys, authorization headers, raw audio, complete response bodies, or private transcript content.

### Fail safely during paste

Do not send paste keystrokes unless the originally captured target window is valid and focus restoration has been verified.

### Preserve localization

User-visible text must support Turkish and English. Add new catalog entries to `src/i18n.py` and test dynamic messages where applicable.

### Keep package resources explicit

Runtime assets required by source execution must also be declared in `build.py`, `PrimeDictate.spec`, and `PrimeDictate-Portable.spec` where applicable.

## Code Style

- Follow the established Python style and module boundaries.
- Prefer small, direct changes over speculative abstractions.
- Use `logging` instead of `print` in application code.
- Keep Qt widget mutation on the main thread.
- Keep network and inference work off the UI thread.
- Use UTF-8 for source and documentation.
- Add comments only where the intent is not evident from the code.

## Tests

Run the complete suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run compilation checks:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src run.py build.py
```

Changes should include regression coverage when they affect:

- STT dispatch or model selection
- Language handling
- Cloud request payloads
- Cloud fallback
- Credential persistence
- Clipboard focus behavior
- File chunking
- UI visibility rules
- Localization
- Overlay geometry
- Packaging resources

Tests must not call paid cloud APIs. Mock provider clients and assert the generated request contract.

## Documentation

Update documentation when behavior, settings, privacy boundaries, supported providers, build steps, or file locations change.

Canonical locations:

- Product overview and setup: `README.md`
- End-user workflow: `docs/USER_GUIDE_TR.md`
- Component contracts: `docs/ARCHITECTURE.md`
- Security reporting: `SECURITY.md`
- Product metadata: `src/metadata.py`
- Vulkan binary provenance: `runtime/whisper-vulkan/PROVENANCE.md`

Do not duplicate a version or publisher value when it can be sourced from `src/metadata.py`. `installer.iss` is a static exception and must be kept synchronized.

## Packaging Checks

Build the portable target:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean PrimeDictate-Portable.spec
```

For a complete release build:

```powershell
.\.venv\Scripts\python.exe build.py
```

Inno Setup 6 is optional for development but required to produce `PrimeDictate-Setup.exe`.

Before publishing a package, verify:

- The executable starts on a clean Windows user profile.
- Application and studio logos are present.
- Version resources match `src/metadata.py`.
- Local CPU inference can load a model.
- Selected GPU backends report accurate availability.
- Credentials are absent from `config.json` and package contents.
- Portable execution still writes user data only under `%APPDATA%\PrimeDictate`.

## Pull Requests

A pull request should contain:

- A concise problem statement
- The implemented behavior
- Privacy or compatibility impact
- Tests added or updated
- Manual verification performed
- Screenshots for visible UI changes

Avoid combining unrelated refactors, formatting changes, and feature work in the same pull request.

## License

By contributing, you agree that your contribution is licensed under the project's [GNU General Public License v3.0](LICENSE).
