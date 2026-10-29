"""FM26-specific helpers: attach to the game and identify the engine build."""
import struct
from dataclasses import dataclass

from winproc import Process, Module

ENGINE = "game_plugin.dll"


@dataclass
class Build:
    module: Module
    timestamp: int      # PE TimeDateStamp: changes with every game patch
    image_size: int

    @property
    def id(self) -> str:
        return f"{self.timestamp:08X}-{self.image_size:X}"


def engine_build(p: Process) -> Build:
    m = p.module(ENGINE)
    dos = p.read(m.base, 0x40)
    if not dos or dos[:2] != b"MZ":
        raise RuntimeError("engine PE header not readable")
    pe = struct.unpack_from("<I", dos, 0x3C)[0]
    hdr = p.read(m.base + pe, 0x58)
    if hdr[:4] != b"PE\0\0":
        raise RuntimeError("bad PE signature")
    timestamp = struct.unpack_from("<I", hdr, 8)[0]
    image_size = struct.unpack_from("<I", hdr, 24 + 56)[0]  # OptionalHeader.SizeOfImage
    return Build(m, timestamp, image_size)


if __name__ == "__main__":
    import datetime as dt
    with Process.attach() as p:
        b = engine_build(p)
        print(f"pid {p.pid}")
        print(f"{ENGINE} at 0x{b.module.base:X}, {b.module.size / 2**20:.0f} MB in memory")
        print(f"build id {b.id} (linked {dt.datetime.fromtimestamp(b.timestamp, dt.UTC):%Y-%m-%d %H:%M} UTC)")
        priv = [r for r in p.regions(private_only=True)]
        print(f"{len(priv)} readable private regions, {sum(r.size for r in priv) / 2**30:.2f} GB")
