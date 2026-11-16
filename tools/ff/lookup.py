"""Finds files in a built map the way Warcraft III does, to prove that every file of the map can be read in game.

The game looks a file up through the archive's hash table: it starts at the slot its name hashes to and walks on
until it finds the name or reaches an empty slot. A wrongly emptied slot makes every file behind it unreachable,
without any error before the game needs the file. MPQ format reference: the hash and encryption scheme of StormLib.
"""
from __future__ import annotations

import struct
from pathlib import Path

EMPTY, DELETED = 0xFFFFFFFF, 0xFFFFFFFE


def _crypt_table() -> list[int]:
    table = [0] * 0x500
    seed = 0x00100001
    for i in range(0x100):
        index = i
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            high = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            table[index] = high | (seed & 0xFFFF)
            index += 0x100
    return table


CRYPT = _crypt_table()


def hash_string(text: str, kind: int) -> int:
    """The MPQ hash of a file name (kind 0: table slot, 1 and 2: the two name checks, 3: encryption key)."""
    seed1, seed2 = 0x7FED7FED, 0xEEEEEEEE
    for char in text.upper().encode():
        seed1 = (CRYPT[kind * 0x100 + char] ^ (seed1 + seed2)) & 0xFFFFFFFF
        seed2 = (char + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1


def _decrypt(data: bytes, key: int) -> list[int]:
    words, seed = [], 0xEEEEEEEE
    for (value,) in struct.iter_unpack('<I', data):
        seed = (seed + CRYPT[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        plain = (value ^ (key + seed)) & 0xFFFFFFFF
        key = ((~key << 21) + 0x11111111 | (key >> 11)) & 0xFFFFFFFF
        seed = (plain + seed + (seed << 5) + 3) & 0xFFFFFFFF
        words.append(plain)
    return words


def unreachable(map_file: Path, names: list[str]) -> list[str]:
    """Returns the names the game would not find in the map.

    Args:
        map_file: A built .w3x.
        names: File names inside the map, with / or \\ as separators.
    """
    data = map_file.read_bytes()
    start = data.find(b'MPQ\x1a')
    _, _, _, _, _, table_pos, _, slots, _ = struct.unpack_from('<4sIIHHIIII', data, start)
    words = _decrypt(data[start + table_pos:start + table_pos + slots * 16], hash_string('(hash table)', 3))
    lost = []
    for name in names:
        name = name.replace('/', '\\')
        check_a, check_b = hash_string(name, 1), hash_string(name, 2)
        slot = hash_string(name, 0) & (slots - 1)
        for _ in range(slots):
            a, b, _, block = words[slot * 4:slot * 4 + 4]
            if block == EMPTY:
                lost.append(name)
                break
            if block != DELETED and a == check_a and b == check_b:
                break
            slot = (slot + 1) % slots
        else:
            lost.append(name)
    return lost
