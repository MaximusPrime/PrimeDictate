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
    print("\n[1/2] Building Portable Edition (PrimeDictate-Portable.exe)...")
    cmd_portable = [
        venv_py, "-m", "PyInstaller",
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

    # 2. Build Folder / Setup Package
    print("\n[2/2] Building Directory Edition for Installer (dist/PrimeDictate)...")
    cmd_dir = [
        venv_py, "-m", "PyInstaller",
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
        # Create Zip archive for setup/distribution
        dist_dir = os.path.join(project_root, "dist")
        target_dir = os.path.join(dist_dir, "PrimeDictate")
        zip_path = os.path.join(dist_dir, "PrimeDictate-Setup-v1.0")
        shutil.make_archive(zip_path, 'zip', target_dir)
        print(f"✓ Setup Zip Archive created at '{zip_path}.zip'")
    else:
        print("x Failed to build Directory Edition.")

    print("\n==========================================")
    print(" Build process finished! Outputs in /dist ")
    print("==========================================")

if __name__ == "__main__":
    build()
