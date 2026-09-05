import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from queue import Queue
from typing import List

from builder.audio import process_sfx_files
from builder.images import process_image_files
from builder.iso import build_output
from builder.rsdk import RSDKArchive
from builder.toolfetch import ToolUnavailable, ensure_extract_xiso, ensure_ffmpeg
from builder.utils import _external_base, get_assets_base, get_manifest_path, no_window_kwargs
from builder.video import process_video_files

# Step indices
STEP_VALIDATE = 0
STEP_EXTRACT = 1
STEP_SFX = 2
STEP_VIDEO = 3
STEP_IMAGES = 4
STEP_MODS = 5
STEP_REPACK = 6
STEP_BUILD = 7

STEP_COUNT = 8
STEP_NAMES = [
    "Validate",
    "Extract RSDK",
    "Compress SFX",
    "Re-encode Videos",
    "Resize Images",
    "Apply Mods",
    "Repack RSDK",
    "Build Output",
]

# Approximate weight of each step for overall progress bar
_STEP_WEIGHTS = [0.01, 0.05, 0.25, 0.30, 0.06, 0.02, 0.12, 0.19]


class BuildPipeline:
    def __init__(self, rsdk_path: str, q: Queue, plus_enabled: bool = False) -> None:
        self._rsdk_path = Path(rsdk_path)
        self._q = q
        self._plus_enabled = plus_enabled
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._step_progress = [0.0] * STEP_COUNT

    def start(self) -> None:
        self._thread.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        self._q.put(("log", msg))

    def _overall_progress(self) -> float:
        total = 0.0
        for i in range(STEP_COUNT):
            total += _STEP_WEIGHTS[i] * self._step_progress[i]
        return total

    def _step_progress_cb(self, step: int):
        def cb(pct: float) -> None:
            self._step_progress[step] = pct
            self._q.put(("progress", self._overall_progress()))
        return cb

    def _start_step(self, step: int) -> None:
        self._step_progress[step] = 0.0
        self._q.put(("step_start", step))
        self._q.put(("progress", self._overall_progress()))

    def _finish_step(self, step: int) -> None:
        self._step_progress[step] = 1.0
        self._q.put(("step_done", step))
        self._q.put(("progress", self._overall_progress()))

    def _fail_step(self, step: int, msg: str) -> None:
        self._q.put(("step_error", step, msg))
        self._q.put(("error", msg))

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            self._pipeline()
        except Exception as exc:
            self._q.put(("error", str(exc)))
        finally:
            self._cleanup_work_dir()

    def _cleanup_work_dir(self) -> None:
        work_dir = getattr(self, "_work_dir", None)
        if not work_dir:
            return
        self._work_dir = None
        try:
            shutil.rmtree(work_dir)
        except Exception as exc:
            self._log(f"  Could not remove working directory {work_dir}: {exc}")

    def _pipeline(self) -> None:
        assets_dir = get_assets_base()

        # ── Step 0: Validate ────────────────────────────────────────────
        self._start_step(STEP_VALIDATE)

        if not self._rsdk_path.exists():
            return self._fail_step(STEP_VALIDATE, f"Data.rsdk not found: {self._rsdk_path}")
        with open(self._rsdk_path, "rb") as f:
            magic = f.read(6)
        if magic != b"RSDKv5":
            return self._fail_step(STEP_VALIDATE, "File does not appear to be an RSDKv5 archive")
        self._log(f"Data.rsdk: {self._rsdk_path.stat().st_size // (1024*1024)} MB  ✓")

        # ffmpeg is fetched on first use
        try:
            ffmpeg = ensure_ffmpeg(self._log, self._step_progress_cb(STEP_VALIDATE))
        except ToolUnavailable as exc:
            return self._fail_step(STEP_VALIDATE, str(exc))
        result = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, **no_window_kwargs())
        if result.returncode != 0:
            return self._fail_step(STEP_VALIDATE, f"ffmpeg is present but will not run: {ffmpeg}")
        ver_line = result.stdout.splitlines()[0] if result.stdout else "?"
        self._log(f"ffmpeg: {ver_line}  ✓")


        # extract-xiso is fetched on first use too
        try:
            extract_xiso = ensure_extract_xiso(self._log, self._step_progress_cb(STEP_VALIDATE))
        except ToolUnavailable as exc:
            return self._fail_step(STEP_VALIDATE, str(exc))
        # It exits non-zero with no arguments, so only check that it runs at all.
        subprocess.run([extract_xiso], capture_output=True, text=True, **no_window_kwargs())

        xbe_path = assets_dir / "default.xbe"
        if not xbe_path.exists():
            return self._fail_step(
                STEP_VALIDATE,
                f"default.xbe not found: {xbe_path}\n"
                "Build the XBE from source and place it at assets/default.xbe",
            )
        self._log(f"default.xbe: {xbe_path.stat().st_size // 1024} KB  ✓")

        manifest_path = get_manifest_path()
        if not manifest_path.exists():
            return self._fail_step(STEP_VALIDATE, f"mania_manifest.json not found: {manifest_path}")
        with open(manifest_path) as f:
            manifest = json.load(f)
        self._log(f"Manifest: {sum(len(v) for v in manifest.values())} entries  ✓")

        self._finish_step(STEP_VALIDATE)

        # ── Step 1: Extract RSDK ─────────────────────────────────────────
        self._start_step(STEP_EXTRACT)
        self._log(f"Loading {self._rsdk_path.name}…")

        archive = RSDKArchive.from_file(str(self._rsdk_path))
        self._log(f"  {len(archive)} files in archive")

        work_dir = Path(tempfile.mkdtemp(prefix="mania_build_"))
        self._log(f"  Working directory: {work_dir}")
        self._work_dir = work_dir  # tracked so _run() can always clean it up
        problems: List[str] = []

        all_paths: List[str] = (
            manifest.get("music", [])
            + manifest.get("sfx", [])
            + manifest.get("videos", [])
            + manifest.get("images", [])
        )
        extracted = 0
        skipped = 0
        prog_cb = self._step_progress_cb(STEP_EXTRACT)
        for i, game_path in enumerate(all_paths):
            data = archive.read(game_path)
            if data is None:
                skipped += 1
            else:
                out = work_dir / game_path.replace("\\", "/")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
                extracted += 1
            prog_cb((i + 1) / len(all_paths))

        self._log(f"  Extracted {extracted} files  ({skipped} not in archive — skipped)")

        # Also copy assets/Mods/ into working directory
        mods_src = assets_dir / "Mods"
        if mods_src.exists():
            for mod_file in mods_src.rglob("*"):
                if mod_file.is_file() and not mod_file.name.startswith("."):
                    rel = mod_file.relative_to(mods_src)
                    dst = work_dir / "Data" / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(mod_file, dst)

        self._finish_step(STEP_EXTRACT)

        # ── Step 2: Compress SFX ─────────────────────────────────────────
        self._start_step(STEP_SFX)
        sfx_dir = work_dir / "Data" / "SoundFX"
        if sfx_dir.exists():
            problems += process_sfx_files(sfx_dir, ffmpeg, self._log, self._step_progress_cb(STEP_SFX))
        else:
            self._log("  No SoundFX directory found — skipping")
        self._finish_step(STEP_SFX)

        # ── Step 3: Re-encode Videos ──────────────────────────────────────
        self._start_step(STEP_VIDEO)
        video_dir = work_dir / "Data" / "Video"
        if video_dir.exists():
            problems += process_video_files(video_dir, ffmpeg, self._log, self._step_progress_cb(STEP_VIDEO))
        else:
            self._log("  No Video directory found — skipping")
        self._finish_step(STEP_VIDEO)

        # ── Step 4: Resize Images ─────────────────────────────────────────
        self._start_step(STEP_IMAGES)
        image_dir = work_dir / "Data" / "Images"
        if image_dir.exists():
            problems += process_image_files(image_dir, ffmpeg, self._log, self._step_progress_cb(STEP_IMAGES))
        else:
            self._log("  No Images directory found — skipping")
        self._finish_step(STEP_IMAGES)

        if problems:
            detail = "\n".join(f"  - {p}" for p in problems[:15])
            if len(problems) > 15:
                detail += f"\n  - ... and {len(problems) - 15} more"
            return self._fail_step(
                STEP_IMAGES,
                f"{len(problems)} file(s) were not processed correctly, so the ISO was "
                f"not built:\n{detail}\n\n"
                "Data.rsdk has been left untouched. This usually means ffmpeg could not "
                "read a source file.",
            )

        # ── Step 5: Apply Mods ───────────────────────────────────────────
        self._start_step(STEP_MODS)
        mods_src = assets_dir / "Mods"
        mod_count = 0
        if mods_src.exists():
            for mod_file in mods_src.rglob("*"):
                if mod_file.is_file() and not mod_file.name.startswith("."):
                    rel = mod_file.relative_to(mods_src)
                    dst = work_dir / "Data" / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(mod_file, dst)
                    self._log(f"  Mod: Data/{rel}")
                    mod_count += 1
        self._log(f"  {mod_count} mod file(s) applied")
        self._step_progress[STEP_MODS] = 1.0
        self._finish_step(STEP_MODS)

        # ── Step 6: Repack RSDK ──────────────────────────────────────────
        self._start_step(STEP_REPACK)
        self._log("  Writing modified files back into archive…")

        prog_cb = self._step_progress_cb(STEP_REPACK)
        modified_files = list((work_dir / "Data").rglob("*"))
        modified_files = [f for f in modified_files if f.is_file()]
        for i, file_path in enumerate(modified_files):
            # Derive game path: work_dir/Data/Music/foo.ogg → Data/Music/foo.ogg
            game_path = str(file_path.relative_to(work_dir)).replace("\\", "/")
            archive.write(game_path, file_path.read_bytes())
            prog_cb((i + 1) / len(modified_files))

        repacked_rsdk = work_dir / "Data.rsdk"
        archive.save(str(repacked_rsdk))
        self._log(f"  Repacked: {repacked_rsdk.stat().st_size // (1024*1024)} MB")
        self._finish_step(STEP_REPACK)

        # ── Step 7: Build Output ─────────────────────────────────────────
        self._start_step(STEP_BUILD)
        output_dir = _external_base() / "Output"

        iso_path = build_output(
            rsdk_path=repacked_rsdk,
            assets_dir=assets_dir,
            output_dir=output_dir,
            extract_xiso=extract_xiso,
            log=self._log,
            progress=self._step_progress_cb(STEP_BUILD),
            plus_enabled=self._plus_enabled,
        )
        self._finish_step(STEP_BUILD)

        self._cleanup_work_dir()
        self._q.put(("done", str(output_dir)))
