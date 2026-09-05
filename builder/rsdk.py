"""
Archive format ported from the RSDKv5 decompilation's Reader.cpp. See LICENSE.md.
RSDK: Evening Star. Decompilation: Rubberduckycooly and chuliRMG.
"""

import hashlib
import struct
from typing import Dict, List, Optional, Tuple

MAGIC = b"RSDKv5"
HEADER_SIZE = 8
ENTRY_SIZE = 24  # 16 hash + 4 offset + 4 size


def _md5(game_path: str) -> bytes:
    raw = hashlib.md5(game_path.lower().encode()).digest()
    return bytes(b for i in range(4) for b in reversed(raw[i * 4 : i * 4 + 4]))


def _make_key(s: str) -> bytes:
    raw = hashlib.md5(s.encode()).digest()
    return bytes(b for i in range(4) for b in reversed(raw[i * 4 : i * 4 + 4]))


def _decrypt_bytes(data: bytes, game_path: str, file_size: int) -> bytes:
    key_a = _make_key(game_path.upper())
    key_b = _make_key(str(file_size))

    e_key_no      = (file_size // 4) & 0x7F
    e_key_pos_a   = 0
    e_key_pos_b   = 8
    e_nybble_swap = False

    out = bytearray(data)
    for i in range(len(out)):
        b = out[i] ^ e_key_no ^ key_b[e_key_pos_b]
        if e_nybble_swap:
            b = ((b << 4) | (b >> 4)) & 0xFF
        b ^= key_a[e_key_pos_a]
        out[i] = b

        e_key_pos_a += 1
        e_key_pos_b += 1

        if e_key_pos_a <= 15:
            if e_key_pos_b > 12:
                e_key_pos_b    = 0
                e_nybble_swap  = not e_nybble_swap
        elif e_key_pos_b <= 8:
            e_key_pos_a   = 0
            e_nybble_swap = not e_nybble_swap
        else:
            e_key_no = (e_key_no + 2) & 0x7F
            if e_nybble_swap:
                e_nybble_swap = False
                e_key_pos_a   = e_key_no % 7
                e_key_pos_b   = (e_key_no % 12) + 2
            else:
                e_nybble_swap = True
                e_key_pos_a   = (e_key_no % 12) + 3
                e_key_pos_b   = e_key_no % 7

    return bytes(out)


class RSDKArchive:
    def __init__(self) -> None:
        self._order: List[bytes] = []
        self._data: Dict[bytes, bytes] = {}
        self._encrypted: Dict[bytes, bool] = {}

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str) -> "RSDKArchive":
        arc = cls()
        with open(path, "rb") as f:
            header = f.read(HEADER_SIZE)
            if len(header) < HEADER_SIZE or header[:6] != MAGIC:
                raise ValueError(f"Not an RSDKv5 file: {path!r}")
            file_count = struct.unpack_from("<H", header, 6)[0]

            # Read all directory entries first
            entries: List[Tuple[bytes, int, int, bool]] = []
            for _ in range(file_count):
                raw = f.read(ENTRY_SIZE)
                if len(raw) < ENTRY_SIZE:
                    raise ValueError("Truncated RSDK directory")
                h = raw[:16]
                offset = struct.unpack_from("<i", raw, 16)[0]
                size_field = struct.unpack_from("<i", raw, 20)[0]
                encrypted = bool(size_field & 0x80000000)
                size = size_field & 0x7FFFFFFF
                entries.append((h, offset, size, encrypted))

            # Read file data
            for h, offset, size, encrypted in entries:
                f.seek(offset)
                data = f.read(size)
                arc._order.append(h)
                arc._data[h] = data
                arc._encrypted[h] = encrypted

        return arc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self, game_path: str) -> Optional[bytes]:
        """Return decrypted bytes for game_path, or None if not present."""
        h = _md5(game_path)
        data = self._data.get(h)
        if data is None:
            return None
        if self._encrypted.get(h, False):
            data = _decrypt_bytes(data, game_path, len(data))
        return data

    def write(self, game_path: str, data: bytes) -> None:
        """Add or replace an entry. Written data is always stored unencrypted."""
        h = _md5(game_path)
        if h not in self._data:
            self._order.append(h)
        self._encrypted[h] = False
        self._data[h] = data

    def save(self, path: str) -> None:
        """Write the archive to disk, recalculating all offsets."""
        file_count = len(self._order)
        dir_end = HEADER_SIZE + ENTRY_SIZE * file_count

        # Calculate absolute offsets
        offsets: Dict[bytes, int] = {}
        cursor = dir_end
        for h in self._order:
            offsets[h] = cursor
            cursor += len(self._data[h])

        with open(path, "wb") as f:
            # Header
            f.write(MAGIC)
            f.write(struct.pack("<H", file_count))

            # Directory entries
            for h in self._order:
                data = self._data[h]
                size = len(data)
                encrypted = self._encrypted.get(h, False)
                size_field = size | (0x80000000 if encrypted else 0)
                f.write(h)
                f.write(struct.pack("<I", offsets[h]))
                f.write(struct.pack("<I", size_field))

            # File data
            for h in self._order:
                f.write(self._data[h])

    def __len__(self) -> int:
        return len(self._order)
