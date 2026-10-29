"""Read-only access to a running Windows process (no writes, no injection).

Only PROCESS_VM_READ and PROCESS_QUERY_INFORMATION are requested, so the
handle cannot modify the game in any way.
"""
import ctypes
import struct
from ctypes import wintypes as wt
from dataclasses import dataclass

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPPROCESS = 0x02
TH32CS_SNAPMODULE = 0x08
TH32CS_SNAPMODULE32 = 0x10
INVALID_HANDLE_VALUE = wt.HANDLE(-1).value

MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}  # R, RW, WC, XR, XRW, XWC


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", wt.WCHAR * 260)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wt.DWORD),
                ("hModule", wt.HMODULE), ("szModule", wt.WCHAR * 256),
                ("szExePath", wt.WCHAR * 260)]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.OpenProcess.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p,
                               ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t


@dataclass
class Module:
    name: str
    path: str
    base: int
    size: int


@dataclass
class Region:
    base: int
    size: int
    protect: int
    private: bool


def find_pid(exe_name: str) -> int | None:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        e = PROCESSENTRY32W(dwSize=ctypes.sizeof(PROCESSENTRY32W))
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == exe_name.lower():
                return e.th32ProcessID
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return None


class Process:
    def __init__(self, pid: int):
        self.pid = pid
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.h:
            raise ctypes.WinError(ctypes.get_last_error())

    @classmethod
    def attach(cls, exe_name: str = "fm.exe") -> "Process":
        pid = find_pid(exe_name)
        if pid is None:
            raise RuntimeError(f"{exe_name} is not running")
        return cls(pid)

    def close(self):
        if self.h:
            k32.CloseHandle(self.h)
            self.h = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- modules / regions -------------------------------------------------
    def modules(self) -> list[Module]:
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, self.pid)
        if snap == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        out = []
        try:
            e = MODULEENTRY32W(dwSize=ctypes.sizeof(MODULEENTRY32W))
            ok = k32.Module32FirstW(snap, ctypes.byref(e))
            while ok:
                out.append(Module(e.szModule, e.szExePath, e.modBaseAddr or 0, e.modBaseSize))
                ok = k32.Module32NextW(snap, ctypes.byref(e))
        finally:
            k32.CloseHandle(snap)
        return out

    def module(self, name: str) -> Module:
        for m in self.modules():
            if m.name.lower() == name.lower():
                return m
        raise RuntimeError(f"module {name} not loaded")

    def regions(self, private_only: bool = False, lo: int = 0x10000, hi: int = 0x7FFF_FFFF_FFFF):
        """Yield committed, readable regions."""
        mbi = MEMORY_BASIC_INFORMATION()
        addr = lo
        while addr < hi:
            if not k32.VirtualQueryEx(self.h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            base, size = mbi.BaseAddress or 0, mbi.RegionSize
            prot = mbi.Protect & 0xFF
            if (mbi.State == MEM_COMMIT and prot in READABLE and not mbi.Protect & PAGE_GUARD
                    and (not private_only or mbi.Type == MEM_PRIVATE)):
                yield Region(base, size, mbi.Protect, mbi.Type == MEM_PRIVATE)
            addr = base + size

    # --- reads -------------------------------------------------------------
    def read(self, addr: int, n: int) -> bytes | None:
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, addr, buf, n, ctypes.byref(got)) or got.value != n:
            return None
        return buf.raw

    def u8(self, a):  return self._unpack(a, "<B", 1)
    def u16(self, a): return self._unpack(a, "<H", 2)
    def i32(self, a): return self._unpack(a, "<i", 4)
    def u32(self, a): return self._unpack(a, "<I", 4)
    def u64(self, a): return self._unpack(a, "<Q", 8)
    def f32(self, a): return self._unpack(a, "<f", 4)
    ptr = u64

    def _unpack(self, a, fmt, n):
        b = self.read(a, n)
        return None if b is None else struct.unpack(fmt, b)[0]

    def chunks(self, regions, chunk: int = 16 << 20, overlap: int = 256):
        """Yield (address, bytes) over regions in chunks, overlapping so matches across
        chunk edges are not missed."""
        for r in regions:
            off = 0
            while off < r.size:
                n = min(chunk + overlap, r.size - off)
                b = self.read(r.base + off, n)
                if b is not None:
                    yield r.base + off, b
                off += chunk
