import os
import shutil
import subprocess
import sys
import tempfile

from src.metadata import (
    APP_NAME,
    EMAIL,
    PUBLISHER,
    REPOSITORY,
    STUDIO,
    VERSION,
    WEBSITE,
)


REQUIRED_BUILD_PATHS = (
    "run.py",
    "PrimeDictate-Logo.ico",
    "PrimeDictate-Logo.png",
    "PrimeDictate.spec",
    "PrimeDictate-Portable.spec",
    "installer.iss",
    os.path.join("assets", "PrimeDictate-AppIcon.png"),
    os.path.join("assets", "maximus-prime-software.png"),
    os.path.join("src", "locales", "tr.json"),
    os.path.join("src", "locales", "en.json"),
    os.path.join("runtime", "whisper-vulkan", "SHA256SUMS"),
)


def validate_build_inputs(project_root=None):
    project_root = project_root or os.path.dirname(os.path.abspath(__file__))
    missing = [path for path in REQUIRED_BUILD_PATHS if not os.path.isfile(os.path.join(project_root, path))]
    if missing:
        raise RuntimeError(f"Missing required build inputs: {', '.join(missing)}")
    for spec_name in ("PrimeDictate.spec", "PrimeDictate-Portable.spec"):
        spec_text = open(os.path.join(project_root, spec_name), encoding="utf-8").read()
        if "primedictate-version-" in spec_text or "C:\\Users\\" in spec_text:
            raise RuntimeError(f"{spec_name} contains a machine-specific path")
        if "PRIMEDICTATE_VERSION_FILE" not in spec_text:
            raise RuntimeError(f"{spec_name} does not use the generated version file")
    return True


def write_version_file(path, executable_name):
    version_parts = [int(part) for part in VERSION.split(".")]
    if len(version_parts) > 4:
        raise ValueError(f"VERSION must contain at most four numeric parts: {VERSION}")
    version_tuple = tuple(version_parts + [0] * (4 - len(version_parts)))
    version_text = ", ".join(str(part) for part in version_tuple)
    comments = f"Studio: {STUDIO}; Website: {WEBSITE}; Email: {EMAIL}; Repository: {REPOSITORY}"
    contents = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({version_text}),
    prodvers=({version_text}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', {PUBLISHER!r}),
         StringStruct('FileDescription', {APP_NAME!r}),
         StringStruct('FileVersion', {VERSION!r}),
         StringStruct('InternalName', {APP_NAME!r}),
         StringStruct('OriginalFilename', {executable_name!r}),
         StringStruct('ProductName', {APP_NAME!r}),
         StringStruct('ProductVersion', {VERSION!r}),
         StringStruct('Comments', {comments!r})]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open(path, "w", encoding="utf-8") as version_file:
        version_file.write(contents)


def build():
    print("==========================================")
    print(f" Building {APP_NAME} {VERSION} Executables ")
    print("==========================================")

    project_root = os.path.dirname(os.path.abspath(__file__))
    validate_build_inputs(project_root)
    venv_py = sys.executable

    version_dir = tempfile.TemporaryDirectory(prefix="primedictate-version-")
    portable_version_file = os.path.join(version_dir.name, "portable-version.txt")
    directory_version_file = os.path.join(version_dir.name, "directory-version.txt")
    write_version_file(portable_version_file, f"{APP_NAME}-Portable.exe")
    write_version_file(directory_version_file, f"{APP_NAME}.exe")

    # 1. Build Portable (.exe)
    print("\n[1/3] Building Portable Edition (PrimeDictate-Portable.exe)...")
    portable_env = os.environ.copy()
    portable_env["PRIMEDICTATE_VERSION_FILE"] = portable_version_file
    cmd_portable = [venv_py, "-m", "PyInstaller", "--noconfirm", "--clean", "PrimeDictate-Portable.spec"]
    res1 = subprocess.run(cmd_portable, cwd=project_root, env=portable_env)
    if res1.returncode == 0:
        print("✓ Portable Edition built successfully in 'dist/PrimeDictate-Portable.exe'")
    else:
        print("x Failed to build Portable Edition.")

    # 2. Build Directory Edition
    print("\n[2/3] Building Directory Edition (dist/PrimeDictate)...")
    directory_env = os.environ.copy()
    directory_env["PRIMEDICTATE_VERSION_FILE"] = directory_version_file
    cmd_dir = [venv_py, "-m", "PyInstaller", "--noconfirm", "--clean", "PrimeDictate.spec"]
    res2 = subprocess.run(cmd_dir, cwd=project_root, env=directory_env)
    if res2.returncode == 0:
        print("✓ Directory Edition built successfully in 'dist/PrimeDictate'")

    # 3. Build Windows Installer (.exe) with Inno Setup
    print("\n[3/3] Building Windows Installer Wizard (PrimeDictate-Setup.exe)...")
    iscc_candidates = [
        shutil.which("ISCC.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
    ]
    iscc_path = next((path for path in iscc_candidates if path and os.path.exists(path)), None)
    iss_file = os.path.join(project_root, "installer.iss")
    if iscc_path and os.path.exists(iss_file):
        res3 = subprocess.run([iscc_path, f"/O{os.path.join(project_root, 'dist')}", iss_file], cwd=project_root)
        if res3.returncode == 0:
            print("✓ Windows Installer wizard created successfully in 'dist/PrimeDictate-Setup.exe'")
        else:
            print("x Inno Setup compilation failed.")
    else:
        res3 = None
        print("Inno Setup ISCC compiler not found, skipping setup.exe creation.")

    if res1.returncode != 0 or res2.returncode != 0:
        raise SystemExit(1)

    print("\n==========================================")
    print(" Build process finished! Outputs in /dist ")
    print("==========================================")

if __name__ == "__main__":
    if "--check" in sys.argv:
        validate_build_inputs()
        print("Build inputs are valid.")
    else:
        build()
