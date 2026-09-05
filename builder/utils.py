import subprocess
import sys
import struct
from pathlib import Path


def _external_base() -> Path:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        if sys.platform == "darwin":
            return exe.parent.parent.parent.parent
        return exe.parent
    return Path(__file__).parent.parent


def get_assets_base() -> Path:
    """Return the assets/ directory."""
    return _external_base() / "assets"


def get_manifest_path() -> Path:
    """Return path to mania_manifest.json."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "mania_manifest.json"
    return Path(__file__).parent.parent / "mania_manifest.json"


def patch_wav_format(data: bytes) -> bytes:
    """
    Patch IEEE float WAV format code (0x0003) to PCM (0x0001).

    Some Sonic Mania SFX files claim IEEE float format but contain 16-bit PCM
    data, which confuses ffmpeg. Patching the fmt chunk fixes this.
    Returns the (possibly modified) bytes.
    """
    if len(data) < 44:
        return data
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data

    # Walk chunks to find fmt
    i = 12
    while i + 8 <= len(data):
        chunk_id = data[i : i + 4]
        chunk_size = struct.unpack_from("<I", data, i + 4)[0]
        if chunk_id == b"fmt ":
            if i + 10 <= len(data):
                audio_format = struct.unpack_from("<H", data, i + 8)[0]
                if audio_format == 0x0003:  # IEEE float → patch to PCM
                    data = bytearray(data)
                    struct.pack_into("<H", data, i + 8, 0x0001)
                    data = bytes(data)
            break
        # Chunks are padded to even size
        i += 8 + chunk_size + (chunk_size & 1)

    return data

def wav_sample_rate(path: Path) -> int:
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return 0

    i = 12
    while i + 8 <= len(data):
        chunk_id = data[i : i + 4]
        chunk_size = struct.unpack_from("<I", data, i + 4)[0]
        if chunk_id == b"fmt " and i + 16 <= len(data):
            return struct.unpack_from("<I", data, i + 12)[0]
        i += 8 + chunk_size + (chunk_size & 1)
    return 0


def png_dimensions(path: Path) -> tuple:
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError:
        return (0, 0)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return (0, 0)
    return struct.unpack(">II", head[16:24])


def no_window_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

