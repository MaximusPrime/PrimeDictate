import os
import sys
import shutil
import subprocess

def build():
    print("==========================================")
    print(" Building PrimeDictate Executables ")
    print("==========================================")

    project_root = os.path.dirname(os.path.abspath(__file__))
    venv_py = sys.executable

    logo_path = os.path.join(project_root, "PrimeDictate-Logo.png")
    run_py = os.path.join(project_root, "run.py")

    # 1. Build Portable (.exe)
    print("\n[1/3] Building Portable Edition (PrimeDictate-Portable.exe)...")
    cmd_portable = [
        venv_py, "-m", "PyInstaller",
        "-y",
        "--noconsole",
        "--onefile",
        f"--icon={logo_path}",
        f"--add-data={logo_path};.",
        "--name=PrimeDictate-Portable",
        "--clean",
        run_py
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
        f"--icon={logo_path}",
        f"--add-data={logo_path};.",
        "--name=PrimeDictate",
        run_py
    ]
    res2 = subprocess.run(cmd_dir, cwd=project_root)
    if res2.returncode == 0:
        print("✓ Directory Edition built successfully in 'dist/PrimeDictate'")

    # 3. Build Windows Installer (.exe) with Inno Setup
    print("\n[3/3] Building Windows Installer Wizard (PrimeDictate-Setup.exe)...")
    iscc_path = r"C:\Users\MAXIMUS\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
    iss_file = os.path.join(project_root, "installer.iss")
    if os.path.exists(iscc_path) and os.path.exists(iss_file):
        res3 = subprocess.run([iscc_path, f"/O{os.path.join(project_root, 'dist')}", iss_file], cwd=project_root)
        if res3.returncode == 0:
            print("✓ Windows Installer wizard created successfully in 'dist/PrimeDictate-Setup.exe'")
        else:
            print("x Inno Setup compilation failed.")
    else:
        print("Inno Setup ISCC compiler not found, skipping setup.exe creation.")

    print("\n==========================================")
    print(" Build process finished! Outputs in /dist ")
    print("==========================================")

if __name__ == "__main__":
    build()
