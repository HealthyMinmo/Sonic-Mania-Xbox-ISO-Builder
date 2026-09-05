import shutil
import subprocess
import tempfile

from builder.utils import no_window_kwargs
from pathlib import Path
from typing import Callable


def _apply_dlc_flag(data: bytes, enabled: bool) -> bytes:
    want = b"y" if enabled else b"n"
    newline = b"\r\n" if b"\r\n" in data else b"\n"

    out, replaced = [], False
    for line in data.split(newline):
        if line.strip().lower().startswith(b"dlcenabled"):
            out.append(b"dlcEnabled=" + want)
            replaced = True
        else:
            out.append(line)

    if not replaced:
        # No key to rewrite -- append one, after [Game] if that section exists.
        idx = next((i for i, l in enumerate(out) if l.strip().lower() == b"[game]"), None)
        if idx is None:
            out.append(b"[Game]")
            idx = len(out) - 1
        out.insert(idx + 1, b"dlcEnabled=" + want)

    return newline.join(out)


def build_output(
    rsdk_path: Path,
    assets_dir: Path,
    output_dir: Path,
    extract_xiso: str,
    log: Callable[[str], None],
    progress: Callable[[float], None],
    plus_enabled: bool = False,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    hdd_dir = output_dir / "Sonic Mania (HDD-Ready)"
    hdd_dir.mkdir(parents=True, exist_ok=True)

    # --- Copy XBE ---
    xbe_src = assets_dir / "default.xbe"
    if not xbe_src.exists():
        raise FileNotFoundError(
            f"default.xbe not found in assets/. "
            f"Build the XBE from source and place it at {xbe_src}"
        )
    shutil.copy2(xbe_src, hdd_dir / "default.xbe")
    log("  Copied default.xbe")
    progress(0.15)

    # --- Copy Data.rsdk ---
    shutil.copy2(rsdk_path, hdd_dir / "Data.rsdk")
    log(f"  Copied Data.rsdk  ({rsdk_path.stat().st_size // (1024*1024)} MB)")
    progress(0.3)

    # --- Copy XBX metadata files ---
    xbx_dir = assets_dir / "xbx"
    for xbx_name in ("TitleMeta.xbx", "TitleImage.xbx", "SaveImage.xbx"):
        src = xbx_dir / xbx_name
        if src.exists():
            shutil.copy2(src, hdd_dir / xbx_name)
            log(f"  Copied {xbx_name}")
        else:
            log(f"  WARNING: {xbx_name} not found in assets/xbx/ — skipping")

    # --- Copy Settings.ini ---
    settings_src = assets_dir / "Settings.ini"
    if settings_src.exists():
        (hdd_dir / "Settings.ini").write_bytes(
            _apply_dlc_flag(settings_src.read_bytes(), plus_enabled)
        )
        log(f"  Copied Settings.ini  (dlcEnabled={'y' if plus_enabled else 'n'})")
    else:
        log("  WARNING: Settings.ini not found in assets/ — output will not include it")
    progress(0.5)

    # --- Build ISO staging directory ---
    with tempfile.TemporaryDirectory(prefix="mania_iso_") as iso_stage:
        stage = Path(iso_stage)

        shutil.copy2(hdd_dir / "default.xbe", stage / "default.xbe")
        shutil.copy2(hdd_dir / "Data.rsdk", stage / "Data.rsdk")

        for name in ("Settings.ini", "TitleMeta.xbx", "TitleImage.xbx", "SaveImage.xbx"):
            src = hdd_dir / name
            if src.exists():
                shutil.copy2(src, stage / name)

        log("  Running extract-xiso to create ISO...")
        progress(0.6)

        iso_path = output_dir / "SonicMania.iso"
        result = subprocess.run(
            [extract_xiso, "-c", str(stage), str(iso_path)],
            capture_output=True,
            text=True,
            **no_window_kwargs(),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"extract-xiso failed (exit {result.returncode}):\n"
                + (result.stderr or result.stdout or "(no output)")
            )

    log(f"  ISO created: {iso_path.stat().st_size // (1024*1024)} MB")
    progress(1.0)
    return iso_path
