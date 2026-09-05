import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ENTRY = ROOT / "builder" / "__main__.py"
NAME = "Sonic Mania Xbox Builder"
SEP = ";" if sys.platform == "win32" else ":"


def main() -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--windowed",
        "--noconfirm",
        f"--name={NAME}",
        f"--add-data=mania_manifest.json{SEP}.",
        "--hidden-import=customtkinter",
        "--collect-all=customtkinter",
        str(ENTRY),
    ]

    print("Running PyInstaller...")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        sys.exit(result.returncode)

    if sys.platform == "darwin":

        external_dir = ROOT / "dist"
        raw_bundle = ROOT / "dist" / NAME
        if raw_bundle.is_dir():
            shutil.rmtree(raw_bundle)
            print(f"Removed redundant onedir bundle: {raw_bundle}")
    else:
        external_dir = ROOT / "dist" / NAME

    for name in ("LICENSE.md",):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, external_dir / name)
            print(f"Copied {name} → {external_dir / name}")

    for folder in ("assets", "licenses"):
        src = ROOT / folder
        dst = external_dir / folder
        if not src.exists():
            print(f"WARNING: {src} not found — skipping")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"Copied {folder}/ → {dst}")

    print(f"\nBuild complete. Distribute the contents of: {ROOT / 'dist'}")

if __name__ == "__main__":
    main()
