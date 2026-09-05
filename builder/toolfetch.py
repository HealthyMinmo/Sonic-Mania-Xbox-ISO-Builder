import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

FFBINARIES_VERSION = "6.1"
_BASE = (
    "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/"
    f"v{FFBINARIES_VERSION}/ffmpeg-{FFBINARIES_VERSION}-"
)

_RELEASES = {
    "win-64":   (_BASE + "win-64.zip",   "b0fb4bcef9d4b5f7a77d2e4854f80d4ce3e43809bc29fd1f97caa1b467f96993", "ffmpeg.exe"),
    "macos-64": (_BASE + "macos-64.zip", "ffcd56ce5ef50c4d36d675b0ee80674f5a0869f94746460ff5d058a33cbd3128", "ffmpeg"),
    "linux-64": (_BASE + "linux-64.zip", "8bb4a27f5fd02f3dd9a5e75c9eddf6ace1d50a08929ee0d20bbf17eb467fb711", "ffmpeg"),
}


EXTRACT_XISO_BUILD = "build-202505152050"
_XISO_BASE = (
    "https://github.com/XboxDev/extract-xiso/releases/download/"
    f"{EXTRACT_XISO_BUILD}/"
)

_XISO_RELEASES = {
    "win-64":   (_XISO_BASE + "extract-xiso-Win64_Release.zip", "fec88d03c7efd6205ab09be4abba70c0afd0eb27a5709f0a6235b828ba5ac11e", "extract-xiso.exe"),
    "macos-64": (_XISO_BASE + "extract-xiso_macOS.zip",         "371e4a800086e875257ddafc037970789fb942b69dbf8ab0ba8301ff7799fef0", "extract-xiso"),
    "linux-64": (_XISO_BASE + "extract-xiso_Linux.zip",         "982bbfefc9255d51f5348a477d7135d68abf81c0af9600e5728edb1246cfa200", "extract-xiso"),
}


class ToolUnavailable(RuntimeError):
    """Raised when a required tool is absent and cannot be fetched."""


# Kept as an alias: callers still catch this name.
FFmpegUnavailable = ToolUnavailable


def _release_key() -> Optional[str]:
    """Map the running platform onto an ffbinaries build, or None if unsupported."""
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return "win-64" if sys.maxsize > 2**32 else None
    if sys.platform == "darwin":
        # The macos-64 build is x86_64; Apple Silicon runs it under Rosetta 2.
        return "macos-64"
    if sys.platform.startswith("linux"):
        return "linux-64" if machine in ("x86_64", "amd64") else None
    return None


def _cache_root() -> Path:
    """Per-user location for downloaded tools, outside the app bundle."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "SonicManiaXboxBuilder"


def cache_dir() -> Path:
    """Where the ffmpeg binary is cached."""
    return _cache_root() / "ffmpeg" / FFBINARIES_VERSION


def xiso_cache_dir() -> Path:
    """Where the extract-xiso binary is cached."""
    return _cache_root() / "extract-xiso" / EXTRACT_XISO_BUILD


def _cached(directory: Path, member: str) -> Optional[Path]:
    path = directory / member
    if path.is_file() and (sys.platform == "win32" or os.access(path, os.X_OK)):
        return path
    return None


def _fetch(
    name: str,
    releases: dict,
    target_dir: Path,
    log: Callable[[str], None],
    progress: Optional[Callable[[float], None]],
    extra_members: tuple = (),
) -> str:
    key = _release_key()
    if not key or key not in releases:
        raise ToolUnavailable(
            f"No prebuilt {name} is available for this platform "
            f"({sys.platform}/{platform.machine()}).\n"
            f"Build one yourself and place it at:\n  {target_dir}"
        )

    url, expected_sha, member = releases[key]
    cached = _cached(target_dir, member)
    if cached:
        log(f"  {name}: cached ({cached})  ✓")
        return str(cached)

    target_dir.mkdir(parents=True, exist_ok=True)
    log(f"  {name} not found — downloading…")

    fd, tmp_name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    tmp_zip = Path(tmp_name)
    try:
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                digest = hashlib.sha256()
                read = 0
                with open(tmp_zip, "wb") as fh:
                    while True:
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
                        digest.update(chunk)
                        read += len(chunk)
                        if progress and total:
                            progress(min(read / total, 1.0))
        except (urllib.error.URLError, OSError) as exc:
            raise ToolUnavailable(
                f"Could not download {name} from {url}\n{exc}\n\n"
                "An internet connection is needed the first time only; the binary is "
                f"cached afterwards in {target_dir}."
            ) from exc

        actual = digest.hexdigest()
        if actual != expected_sha:
            # Refuse rather than run an executable we cannot vouch for.
            raise ToolUnavailable(
                f"Downloaded {name} failed its integrity check and was discarded.\n"
                f"  expected {expected_sha}\n  got      {actual}"
            )
        log(f"  {name}: sha256 verified  ✓")

        with zipfile.ZipFile(tmp_zip) as zf:
            for want in (member,) + extra_members:
                # Archives may store Windows-style paths ("artifacts\\extract-xiso.exe"),
                # which Path() does not split on POSIX -- normalise before matching.
                hit = next(
                    (n for n in zf.namelist()
                     if PurePosixPath(n.replace("\\", "/")).name == want),
                    None,
                )
                if hit is None:
                    if want == member:
                        raise ToolUnavailable(f"{want} not found inside {url}")
                    continue
                with zf.open(hit) as src, open(target_dir / want, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    finally:
        try:
            tmp_zip.unlink(missing_ok=True)
        except OSError:
            # A stray temp file is not worth failing a build over; the OS reclaims it.
            pass

    out = target_dir / member
    if sys.platform != "win32":
        out.chmod(0o755)
    if sys.platform == "darwin":
        # A downloaded binary is quarantined; Gatekeeper would kill it silently.
        subprocess.run(["xattr", "-d", "com.apple.quarantine", str(out)],
                       capture_output=True)

    log(f"  {name}: downloaded to {out}  ✓")
    return str(out)


def ensure_ffmpeg(
    log: Callable[[str], None],
    progress: Optional[Callable[[float], None]] = None,
) -> str:
    """Return a path to a usable ffmpeg, downloading it once if needed."""
    return _fetch("ffmpeg", _RELEASES, cache_dir(), log, progress)


def ensure_extract_xiso(
    log: Callable[[str], None],
    progress: Optional[Callable[[float], None]] = None,
) -> str:
    """Return a path to a usable extract-xiso, downloading it once if needed."""
    return _fetch("extract-xiso", _XISO_RELEASES, xiso_cache_dir(), log, progress,
                  extra_members=("LICENSE.TXT",))
