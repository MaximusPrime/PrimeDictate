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
    venv_py = sys.executable

    logo_path = os.path.join(project_root, "PrimeDictate-Logo.png")
    icon_path = os.path.join(project_root, "PrimeDictate-Logo.ico")
    run_py = os.path.join(project_root, "run.py")
    logo_arg = os.path.basename(logo_path)
    icon_arg = os.path.basename(icon_path)
    run_arg = os.path.basename(run_py)
    runtime_arg = "runtime"
    studio_logo_arg = os.path.join("assets", "maximus-prime-software.png")
    app_icon_arg = os.path.join("assets", "PrimeDictate-AppIcon.png")

    version_dir = tempfile.TemporaryDirectory(prefix="primedictate-version-")
    portable_version_file = os.path.join(version_dir.name, "portable-version.txt")
    directory_version_file = os.path.join(version_dir.name, "directory-version.txt")
    write_version_file(portable_version_file, f"{APP_NAME}-Portable.exe")
    write_version_file(directory_version_file, f"{APP_NAME}.exe")

    # 1. Build Portable (.exe)
    print("\n[1/3] Building Portable Edition (PrimeDictate-Portable.exe)...")
    cmd_portable = [
        venv_py, "-m", "PyInstaller",
        "-y",
        "--noconsole",
        "--onefile",
        f"--icon={icon_arg}",
        f"--add-data={logo_arg};.",
        f"--add-data={studio_logo_arg};assets",
        f"--add-data={app_icon_arg};assets",
        f"--add-data={runtime_arg};runtime",
        f"--version-file={portable_version_file}",
        f"--name={APP_NAME}-Portable",
        "--clean",
        run_arg
    ]
    res1 = subprocess.run(cmd_portable, cwd=project_root)
    if res1.returncode == 0:
        print("✓ Portable Edition built successfully in 'dist/PrimeDictate-Portable.exe'")
    else:
        print("x Failed to build Portable Edition.")

    # 2. Build Directory Edition
    print("\n[2/3] Building Directory Edition (dist/PrimeDictate)...")
    cmd_dir = [
        venv_py, "-m", "PyInstaller",
        "-y",
        "--noconsole",
        "--onedir",
        f"--icon={icon_arg}",
        f"--add-data={logo_arg};.",
        f"--add-data={studio_logo_arg};assets",
        f"--add-data={app_icon_arg};assets",
        f"--add-data={runtime_arg};runtime",
        f"--version-file={directory_version_file}",
        f"--name={APP_NAME}",
        run_arg
    ]
    res2 = subprocess.run(cmd_dir, cwd=project_root)
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

    if res1.returncode != 0 or res2.returncode != 0 or (res3 and res3.returncode != 0):
        raise SystemExit(1)

    print("\n==========================================")
    print(" Build process finished! Outputs in /dist ")
    print("==========================================")

if __name__ == "__main__":
    build()
