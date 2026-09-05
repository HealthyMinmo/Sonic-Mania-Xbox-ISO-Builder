import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List

from builder.utils import png_dimensions, no_window_kwargs


def resize_image(
    src: Path,
    dst: Path,
    ffmpeg: str,
    log: Callable[[str], None],
) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    orig_size = src.stat().st_size

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                ffmpeg, "-y",
                "-i", str(src),
                "-vf",
                "scale=640:360:force_original_aspect_ratio=decrease,"
                "pad=640:360:-1:-1:black",
                tmp_path,
            ],
            capture_output=True,
            **no_window_kwargs(),
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            log(f"  FAILED: {src.name}: {stderr}")
            return False

        new_size = os.path.getsize(tmp_path)
        os.replace(tmp_path, dst)
        log(f"  {src.name}: {orig_size // 1024} KB → {new_size // 1024} KB")
        return True
    except Exception as exc:
        log(f"  ERROR resizing {src.name}: {exc}")
        return False
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


TARGET_IMAGE_SIZE = (640, 360)


def process_image_files(
    image_dir: Path,
    ffmpeg: str,
    log: Callable[[str], None],
    progress: Callable[[float], None],
) -> List[str]:
    files: List[Path] = sorted(image_dir.glob("*.png"))
    if not files:
        log("  No image files found — skipping")
        return []

    problems: List[str] = []
    for i, src in enumerate(files):
        ok = resize_image(src, src, ffmpeg, log)
        # Judge the file, not the conversion -- an already-correct image is fine.
        size = png_dimensions(src)
        if size != TARGET_IMAGE_SIZE:
            detail = "" if ok else " (resize failed)"
            problems.append(
                f"{src.name}: {size[0]}x{size[1]}{detail}, "
                f"expected {TARGET_IMAGE_SIZE[0]}x{TARGET_IMAGE_SIZE[1]}"
            )
        progress((i + 1) / len(files))

    if problems:
        log(f"  {len(problems)} of {len(files)} images did not resize cleanly")
    return problems
