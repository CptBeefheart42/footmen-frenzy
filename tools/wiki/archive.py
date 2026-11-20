"""Read named entries from a Warcraft map using the system StormLib library."""
import ctypes as c
from ctypes.util import find_library
import os
from pathlib import Path


class Archive:
    """A read-only MPQ archive, including maps with no listfile."""

    def __init__(self, path):
        windows = os.name == "nt"
        library = os.environ.get("STORMLIB_DLL") or find_library("storm") or ("StormLib.dll" if windows else None)
        if not library:
            raise ValueError("Install StormLib or set STORMLIB_DLL to its library path.")
        self.lib = (c.WinDLL if windows else c.CDLL)(library)
        path_type = c.c_wchar_p if windows else c.c_char_p
        signatures = {
            'SFileOpenArchive': [path_type, c.c_uint, c.c_uint, c.POINTER(c.c_void_p)],
            'SFileOpenFileEx': [c.c_void_p, c.c_char_p, c.c_uint, c.POINTER(c.c_void_p)],
            'SFileGetFileSize': [c.c_void_p, c.c_void_p],
            'SFileReadFile': [c.c_void_p, c.c_void_p, c.c_uint, c.POINTER(c.c_uint), c.c_void_p],
            'SFileCloseFile': [c.c_void_p], 'SFileCloseArchive': [c.c_void_p],
        }
        for name, args in signatures.items():
            getattr(self.lib, name).argtypes = args
            getattr(self.lib, name).restype = c.c_bool
        self.lib.SFileGetFileSize.restype = c.c_uint
        self.handle = c.c_void_p()
        archive_path = str(Path(path).resolve())
        if not self.lib.SFileOpenArchive(archive_path if windows else os.fsencode(archive_path), 0, 256, c.byref(self.handle)):
            raise RuntimeError(f'Cannot open map archive: {path}')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if not self.lib.SFileCloseArchive(self.handle):
            raise RuntimeError('Cannot close map archive')

    def read(self, name):
        handle = c.c_void_p()
        if not self.lib.SFileOpenFileEx(self.handle, name.encode('utf-8'), 0, c.byref(handle)):
            raise KeyError(name)
        try:
            size = self.lib.SFileGetFileSize(handle, None)
            if size == 0xFFFFFFFF:
                raise RuntimeError(f'Invalid entry size: {name}')
            data = c.create_string_buffer(size)
            count = c.c_uint()
            if size and (not self.lib.SFileReadFile(handle, data, size, c.byref(count), None) or count.value != size):
                raise RuntimeError(f'Incomplete read: {name}')
            return data.raw
        finally:
            self.lib.SFileCloseFile(handle)
