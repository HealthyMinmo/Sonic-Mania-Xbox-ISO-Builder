import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List

from builder.utils import patch_wav_format, wav_sample_rate, no_window_kwargs


def downsample_sfx(
    src: Path,
    dst: Path,
    ffmpeg: str,
    log: Callable[[str], None],
) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Read source and patch format byte if needed
        raw = src.read_bytes()
        patched = patch_wav_format(raw)
        Path(tmp_path).write_bytes(patched)

        result = subprocess.run(
            [
                ffmpeg, "-y",
                "-i", tmp_path,
                "-ar", "22050",
                "-sample_fmt", "s16",
                "-map_metadata", "-1",
                "-fflags", "+bitexact",
                str(dst),
            ],
            capture_output=True,
            **no_window_kwargs(),
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            log(f"  FAILED resampling {src.name}: {stderr}")
            # Fall back to copying original so the RSDK isn't missing the file
            if src.resolve() != dst.resolve():
                import shutil
                shutil.copy2(src, dst)
            return False

        log(f"  {src.name}: OK")
        return True
    except Exception as exc:
        log(f"  ERROR resampling {src.name}: {exc}")
        return False
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


TARGET_SFX_RATE = 22050


def process_sfx_files(
    sfx_dir: Path,
    ffmpeg: str,
    log: Callable[[str], None],
    progress: Callable[[float], None],
) -> List[str]:
    files: List[Path] = sorted(sfx_dir.rglob("*.wav"))
    if not files:
        log("  No SFX files found — skipping")
        return []

    problems: List[str] = []
    for i, src in enumerate(files):
        ok = downsample_sfx(src, src, ffmpeg, log)
        # Judge the file, not the conversion: ffmpeg refuses input that is already at
        # spec, which is exactly what a re-run over a processed archive looks like.
        rate = wav_sample_rate(src)
        if rate != TARGET_SFX_RATE:
            detail = "" if ok else " (conversion failed)"
            problems.append(
                f"{src.name}: {rate or 'unreadable'} Hz{detail}, "
                f"expected {TARGET_SFX_RATE}"
            )
        progress((i + 1) / len(files))

    if problems:
        log(f"  {len(problems)} of {len(files)} SFX did not convert cleanly")
    return problems
