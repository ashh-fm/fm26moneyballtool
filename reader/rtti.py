"""MSVC x64 RTTI helpers: class name of a vtable, and vtable of a class name.

vtable[-1] -> RTTICompleteObjectLocator {sig=1, offset, cdOffset, pTypeDescriptor (RVA), ...}
TypeDescriptor {pVFTable, spare, name[] = ".?AVNAME@@"}
"""
import struct
import sys

from game import engine_build
from winproc import Process


def class_name(p: Process, base: int, vt: int) -> str | None:
    col = p.u64(vt - 8)
    if not col:
        return None
    hdr = p.read(col, 0x18)
    if not hdr:
        return None
    sig, _off, _cd, td_rva = struct.unpack_from("<IIII", hdr)
    if sig != 1:
        return None
    name = p.read(base + td_rva + 0x10, 128)
    if not name:
        return None
    return name.split(b"\0", 1)[0].decode("latin-1")


def vtables_for(p: Process, module, mangled: str) -> dict[int, int]:
    """Find every vtable in the module whose RTTI name equals `mangled`.
    Returns {vtable address: COL offset of that sub-object}."""
    base, size = module.base, module.size
    image = b"".join(p.read(base + o, min(16 << 20, size - o)) or b"\0" * min(16 << 20, size - o)
                     for o in range(0, size, 16 << 20))
    i = image.find(mangled.encode() + b"\0")
    if i < 0:
        return {}
    td_rva = i - 0x10
    out = {}
    # object locators: {sig=1, offset, cdOffset, TypeDescriptor RVA, ...}
    pat = struct.pack("<I", td_rva)
    j = image.find(pat)
    while j != -1:
        c = j - 0xC
        if c >= 0 and c % 4 == 0 and struct.unpack_from("<I", image, c)[0] == 1:
            col, offset = base + c, struct.unpack_from("<I", image, c + 4)[0]
            # vtable[-1] == col
            k = image.find(struct.pack("<Q", col))
            while k != -1:
                if k % 8 == 0:
                    out[base + k + 8] = offset
                k = image.find(struct.pack("<Q", col), k + 1)
        j = image.find(pat, j + 1)
    return out


if __name__ == "__main__":
    with Process.attach() as p:
        m = engine_build(p).module
        for a in sys.argv[1:]:
            vt = int(a, 16)
            print(f"0x{vt:X} (+0x{vt - m.base:X}): {class_name(p, m.base, vt)}")
