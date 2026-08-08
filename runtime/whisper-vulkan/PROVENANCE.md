# PrimeDictate whisper.cpp Vulkan Runtime Provenance

This directory contains the pinned whisper.cpp runtime distributed with PrimeDictate for local Vulkan speech-to-text inference on Windows.

## Upstream Source

| Field | Value |
|---|---|
| Project | [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) |
| Release | `v1.9.2` |
| Commit | `306c88f4d1286aec1bf96e544632897886af5501` |
| Upstream license | [LICENSE.whisper.cpp.txt](LICENSE.whisper.cpp.txt) |

## Build Environment

| Field | Value |
|---|---|
| Target | Windows x64 |
| Compiler | Microsoft Visual C++ 19.51 |
| Vulkan SDK | `1.4.350` |
| Required build option | `GGML_VULKAN=ON` |

The CLI and shared libraries were built locally from the pinned upstream source. `whisper-server.exe` was reproduced from the same pinned commit with CMake, MSVC x64, `GGML_VULKAN=ON`, and the server example target enabled. PrimeDictate inspects the CLI runtime for Vulkan backend indicators before reporting it as available.

## Integrity Verification

Runtime files are listed in `SHA256SUMS`. Before use, PrimeDictate calculates each listed file's SHA-256 digest and compares it with the shipped manifest.

Verification protects against accidental corruption and unexpected file replacement relative to the manifest included in the same application package. It is not a substitute for authenticating the application package itself.

## Runtime Files

The directory includes the whisper.cpp CLI, the loopback-only persistent server, and their required GGML/Vulkan dynamic libraries. Model weights are not bundled here; compatible GGML models are managed separately in the current user's PrimeDictate model directory.
