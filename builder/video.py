import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List

from builder.utils import no_window_kwargs

THEORA_QUALITY = "8"
KEYFRAME_INTERVAL = "256"

def _run_ffmpeg(
    ffmpeg: str,
    args: List[str],
    src: Path,
    dst: Path,
    log: Callable[[str], None],
) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    orig_size = src.stat().st_size

    with tempfile.NamedTemporaryFile(suffix=".ogv", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [ffmpeg, "-y"] + args + [tmp_path],
            capture_output=True,
            **no_window_kwargs(),
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            log(f"  FAILED {src.name}: {stderr}")
            return False

        new_size = os.path.getsize(tmp_path)
        os.replace(tmp_path, dst)
        log(
            f"  {src.name}: {orig_size / 1_000_000:.1f} MB"
            f" → {new_size / 1_000_000:.1f} MB"
        )
        return True
    except Exception as exc:
        log(f"  ERROR encoding {src.name}: {exc}")
        return False
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def reencode_intro(
    src: Path,
    dst: Path,
    ffmpeg: str,
    log: Callable[[str], None],
) -> bool:
    """Re-encode Mania.ogv (intro) with letterbox bars."""
    return _run_ffmpeg(
        ffmpeg,
        [
            "-ss", "7",
            "-i", str(src),
            "-vf", "scale=640:320,pad=640:360:0:20",
            "-r", "24",
            "-c:v", "libtheora", "-q:v", THEORA_QUALITY, "-g", KEYFRAME_INTERVAL,
            "-c:a", "libvorbis", "-b:a", "70k",
        ],
        src, dst, log,
    )


def reencode_ending(
    src: Path,
    dst: Path,
    ffmpeg: str,
    log: Callable[[str], None],
) -> bool:
    """Re-encode an ending/cutscene OGV (crop source bars, add new bars)."""
    return _run_ffmpeg(
        ffmpeg,
        [
            "-i", str(src),
            "-vf", "crop=1024:396:0:58,scale=640:248,pad=640:360:0:56",
            "-r", "24",
            "-c:v", "libtheora", "-q:v", THEORA_QUALITY, "-g", KEYFRAME_INTERVAL,
            "-c:a", "libvorbis", "-b:a", "70k",
        ],
        src, dst, log,
    )

TARGET_VIDEO_SIZE = (640, 360)

def probe_video_size(path: Path, ffmpeg: str) -> tuple:

    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            capture_output=True,
            **no_window_kwargs(),
        )
    except Exception:
        return (0, 0)
    text = result.stderr.decode(errors="replace")
    match = re.search(r"Video:.*?[ ,](\d{2,5})x(\d{2,5})[ ,]", text)
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2)))


def process_video_files(
    video_dir: Path,
    ffmpeg: str,
    log: Callable[[str], None],
    progress: Callable[[float], None],
) -> List[str]:
    files: List[Path] = sorted(video_dir.glob("*.ogv"))
    if not files:
        log("  No video files found — skipping")
        return []

    problems: List[str] = []
    for i, src in enumerate(files):
        if src.name == "Mania.ogv":
            ok = reencode_intro(src, src, ffmpeg, log)
        else:
            ok = reencode_ending(src, src, ffmpeg, log)

        size = probe_video_size(src, ffmpeg)
        if size != TARGET_VIDEO_SIZE:
            detail = "" if ok else " (re-encode failed)"
            problems.append(
                f"{src.name}: {size[0]}x{size[1]}{detail}, "
                f"expected {TARGET_VIDEO_SIZE[0]}x{TARGET_VIDEO_SIZE[1]}"
            )
        progress((i + 1) / len(files))

    if problems:
        log(f"  {len(problems)} of {len(files)} videos did not re-encode cleanly")
    return problems
