# Windows Paste Compatibility Matrix

PrimeDictate captures one foreground top-level window, its process ID, and the focused child control when recording starts. It restores that verified target after transcription. If verification fails, text remains on the clipboard.

## Required release checks

Run each row for both installed and portable builds on Windows 10 and Windows 11. Test standard mode first; use administrator mode only for an elevated target.

| Target | Standard target | Elevated target | Rich clipboard restored | Multiline/Unicode | Result |
|---|---:|---:|---:|---:|---|
| Windows Notepad | Required | Required | Required | Required | Pending physical release check |
| Microsoft Word | Required | Required | Required | Required | Pending physical release check |
| Microsoft Outlook compose | Required | Optional | Required | Required | Pending physical release check |
| Chrome / Edge text field | Required | Optional | Required | Required | Pending physical release check |
| Firefox text field | Required | Optional | Required | Required | Pending physical release check |
| Visual Studio Code | Required | Required | Required | Required | Pending physical release check |
| Windows Terminal / PowerShell | Required | Required | Required | Required | Pending physical release check |
| Remote Desktop client | Required | Optional | Required | Required | Pending physical release check |
| Password / secure field | Must fail safely | Must fail safely | Required | N/A | Pending physical release check |
| Full-screen game | Must not steal focus | N/A | Required | N/A | Pending physical release check |

## Acceptance criteria

1. The captured top-level HWND must still belong to the captured PID.
2. A standard PrimeDictate process must refuse an elevated target and leave text on the clipboard.
3. Administrator mode must be opt-in and must show a Windows UAC prompt on launch.
4. A user clipboard change after injection must never be overwritten.
5. HTML, image, file-list and plain-text MIME formats must survive restoration.
6. Closing or replacing the target during transcription must never redirect the paste to another application.
7. The UI must report that a paste command was sent, not claim that the target accepted it.

Windows exposes only one foreground window; PrimeDictate intentionally does not broadcast dictated text to multiple windows because that would make target and privacy guarantees impossible.
