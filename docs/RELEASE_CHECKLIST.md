# Windows Release Checklist

PrimeDictate ships two Windows artifacts from the same source and configuration contract:

- `PrimeDictate-Portable.exe`: single-file, no installer, standard-user process by default.
- `PrimeDictate-Setup.exe`: 64-bit per-machine installer; setup elevation is used only to write under Program Files. The installed app remains a standard-user process by default.

Both editions store settings, history, credentials and downloaded models per Windows user. “Portable” means no installation is required; it does not place private data beside the executable.

## Automated gate

1. Create a clean Python 3.12 virtual environment.
2. Install `requirements-lock.txt` directly.
3. Run `python -m pip check`.
4. Run `python -m unittest discover -s tests -v`.
5. Run `python build.py --check`, then `python build.py`.
6. Preserve `dist/SHA256SUMS.txt` with the release artifacts.

## Signing gate

Before public distribution, sign all three executables with the publisher's trusted Windows code-signing certificate and a trusted timestamp server:

- `dist/PrimeDictate-Portable.exe`
- `dist/PrimeDictate/PrimeDictate.exe`
- `dist/PrimeDictate-Setup.exe`

Verify each signature with `Get-AuthenticodeSignature`. An unsigned build is suitable for internal testing only and is not a production release candidate.

## Physical acceptance gate

Complete every applicable row in `WINDOWS_COMPATIBILITY_MATRIX.md` on Windows 10 and Windows 11 for installed and portable editions. At minimum, verify standard and elevated Notepad targets, Office, Chromium, Firefox, rich clipboard restoration, UAC rejection, startup behavior, CPU, CUDA and Vulkan where hardware is available.
