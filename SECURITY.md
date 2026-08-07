# Security Policy

PrimeDictate processes microphone recordings, transcript text, clipboard contents, API credentials, and optional local history. Security reports involving these data paths are treated seriously.

## Supported Version

Security fixes currently target the latest published PrimeDictate release and the default branch.

| Version | Supported |
|---|---|
| `1.0.x` | Yes |
| Older versions | No |

## Reporting a Vulnerability

Do not open a public issue for an unpatched vulnerability.

Send a private report to:

[maximusprimesoftware@gmail.com](mailto:maximusprimesoftware@gmail.com)

Use a subject such as:

```text
[PrimeDictate Security] Short issue summary
```

Include:

- Affected version or commit
- Windows version and architecture
- Required configuration or provider
- Reproduction steps
- Expected and observed behavior
- Security and privacy impact
- Minimal proof of concept when safe
- Suggested mitigation, if known

Do not send real API keys, private recordings, private transcripts, credential database exports, or unrelated personal data. Replace secrets with synthetic test values.

## Response Process

The project will attempt to:

1. Acknowledge a complete report.
2. Reproduce and assess severity.
3. Develop a fix and regression test.
4. Coordinate disclosure when appropriate.
5. Publish remediation information after a fixed release is available.

Response times are best effort and depend on report completeness and maintainer availability.

## Security Boundaries

### Credentials

API credentials are stored through Windows Credential Manager. They must not be serialized to `config.json`, logged, embedded into URLs, included in screenshots, or committed to source control.

### Local and cloud processing

Local CPU, CUDA, and Vulkan STT are intended to keep audio on the device. Audio may leave the device only when cloud STT is selected or the user has explicitly enabled cloud fallback and local processing fails.

Cloud LLM processing receives transcript text, not the original recording.

### Clipboard injection

PrimeDictate captures the intended target window before recording. It avoids sending `Ctrl+V` when it cannot verify restored focus. A report that demonstrates paste injection into an unintended window is security-relevant.

### History

Transcript history is optional and stored in the current user's application-data directory. PrimeDictate does not encrypt `history.json`; users handling sensitive transcripts should disable history or apply appropriate Windows account and disk protections.

### Local LLM endpoints

The user controls the configured Ollama or LM Studio endpoint. PrimeDictate does not establish transport security or authentication for a local endpoint. Exposing such endpoints beyond localhost is the user's responsibility.

### Model and runtime downloads

The bundled Vulkan runtime is checked against a shipped SHA-256 manifest. Downloaded model trust also depends on the configured upstream source and network environment.

## In-Scope Examples

- API credentials written to plaintext configuration or logs
- Cloud upload without the documented selection or fallback consent
- Clipboard paste into an unverified target window
- Path traversal or arbitrary file overwrite during model download or export
- Unsafe command execution through user-controlled model or runtime fields
- Package tampering that bypasses an implemented integrity check
- Exposure of transcript or history data to another Windows user

## Out-of-Scope Examples

- Provider outages, quota exhaustion, or model-quality disagreements
- Hallucination or formatting quality from third-party LLMs without a security impact
- Compromise of a user's cloud-provider account unrelated to PrimeDictate
- Risks that require an already compromised Windows administrator account without crossing an additional boundary
- GPU or driver instability without a security consequence

## Hardening Recommendations

- Prefer local STT and rule-based or local text processing for sensitive material.
- Keep cloud fallback disabled unless it is explicitly required.
- Use provider keys with minimum necessary permissions and quotas.
- Keep Windows, GPU drivers, and PrimeDictate updated.
- Disable transcript history for confidential workflows.
- Do not expose local LLM endpoints to untrusted networks.
- Download releases and runtimes only from trusted project sources.

## Public Issues

After a fix is available, non-sensitive follow-up discussion may move to the public repository:

[github.com/MaximusPrime/PrimeDictate](https://github.com/MaximusPrime/PrimeDictate)
