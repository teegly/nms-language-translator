"""Byte-exact reproduction of the NMS alien-word generator by emulating the real
NMS.exe code with Unicorn (read-only static analysis; the executable is never run
as a process, only its instructions are interpreted).

Why emulate instead of porting: the generator is 8 separate ~1MB compiler-emitted
functions plus an intricate driver loop (per-char generator-index rotation, a
per-word context coin-flip, vowel fixups). Emulating the real code is byte-exact
by construction; hand-porting that loop would risk silent divergence.

Pipeline (all reverse-engineered from NMS.exe, see RE_FINDINGS.md):
  seed  = wyhash(english_lowercase, len)          # fn 0x1401c8cc0, wyhash secret consts
  state = ( seed_lo or 1 ,  ror32(seed_lo,16) ^ seed_hi ^ seed_lo )
  alien = driver( state, idx=FACTION_IDX[faction], min=len-1, max=len+1 )  # fn 0x140dcd8e0

Verified against user-confirmed pairs: federation->evykelordur (Gek),
research->agodskovd (Korvax), warrior->doxongh (Vy'keen).
"""
import os
import struct
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UcError, UC_HOOK_CODE
from unicorn.x86_const import (
    UC_X86_REG_RSP, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8,
    UC_X86_REG_R9, UC_X86_REG_RAX, UC_X86_REG_RIP, UC_X86_REG_GS_BASE,
)

# Point NMS_EXE at your own copy of the game executable. Falls back to a
# repo-relative Binaries/ dir (the exe is gitignored, never committed).
DEFAULT_EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Binaries", "NMS.exe")
EXE = os.environ.get("NMS_EXE", DEFAULT_EXE)

DRIVER = 0x140dcd8e0     # general procedural word-generator driver
HASH_FN = 0x1401c8cc0    # wyhash(ptr, len) -> uint64

# faction name -> 8-way generator/start-table index. All VERIFIED against oracle
# pairs. Autophage shares generator idx 0 with Atlas, then applies a display
# substitution cipher (see AUTOPHAGE_CIPHER); confirmed by 107 exact matches
# against wiki english->autophage pairs.
FACTION_IDX = {
    "Gek": 2,
    "Korvax": 3,
    "Vy'keen": 4,
    "Atlas": 0,
    "Autophage": 0,
}
FACTION_VERIFIED = {"Gek", "Korvax", "Vy'keen", "Atlas", "Autophage"}

# Autophage display cipher: the generator emits Latin (idx 0, same as Atlas); the
# game renders it in a smaller glyph set (Greek letters + digits). Many-to-one and
# therefore lossy (n,r,v -> "1"; j,s,y -> "0"), so it is NOT reversible glyph->latin.
AUTOPHAGE_CIPHER = dict(zip(
    "abcdefghijklmnopqrstuvwxyz",
    "aβxδεφγηi0kλμ1oπθ10tu1ωξ0ζ",
))


def autophage_glyphs(latin):
    return "".join(AUTOPHAGE_CIPHER.get(c, c) for c in latin)

RET_SENTINEL = 0x12340000


def _align_up(x, a=0x1000):
    return (x + a - 1) & ~(a - 1)


class NmsEmu:
    def __init__(self, exe=EXE):
        pe = pefile.PE(exe, fast_load=True)
        pe.parse_data_directories()
        self.IB = pe.OPTIONAL_HEADER.ImageBase
        data = pe.__data__
        secs = []
        for s in pe.sections:
            va = self.IB + s.VirtualAddress
            secs.append((va, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData))
        img_end = max(va + _align_up(max(vsz, rsz)) for va, vsz, _, rsz in secs)
        img_size = _align_up(img_end - self.IB)

        uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc.mem_map(self.IB, img_size)
        for va, vsz, foff, rsz in secs:
            raw = bytes(data[foff:foff + rsz])
            if raw:
                uc.mem_write(va, raw)

        self.STACK, stack_sz = 0x1000000000, 0x200000
        uc.mem_map(self.STACK, stack_sz)
        self.rsp0 = self.STACK + stack_sz - 0x800

        teb = 0x3000000000
        uc.mem_map(teb, 0x1000)
        uc.mem_write(teb + 0x08, struct.pack("<Q", self.STACK + stack_sz))
        uc.mem_write(teb + 0x10, struct.pack("<Q", self.STACK))
        uc.reg_write(UC_X86_REG_GS_BASE, teb)

        self.SCR = 0x2000000000
        uc.mem_map(self.SCR, 0x10000)
        self.STATE, self.INPUT, self.OUTPUT = self.SCR, self.SCR + 0x40, self.SCR + 0x80

        self.HEAP, self.heap_sz = 0x4000000000, 0x400000
        uc.mem_map(self.HEAP, self.heap_sz)
        self._heap = self.HEAP

        # redirect import thunks to a trampoline region of `ret` stubs we hook
        imp = 0x5000000000
        uc.mem_map(imp, 0x4000)
        slot_names = {}
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            for i in entry.imports:
                if i.address and i.name:
                    slot_names[i.address] = i.name.decode()
        self._imp = {}
        for i, (slot, nm) in enumerate(sorted(slot_names.items())):
            fake = imp + i
            uc.mem_write(fake, b"\xc3")
            uc.mem_write(slot, struct.pack("<Q", fake))
            self._imp[fake] = nm
        uc.hook_add(UC_HOOK_CODE, self._dispatch_import, begin=imp, end=imp + 0x4000)
        self.uc = uc

    def _halloc(self, n):
        p = self._heap
        self._heap = _align_up(p + max(n, 16), 16)
        return p

    def _dispatch_import(self, uc, address, size, ud):
        nm = self._imp.get(address)
        if nm is None:
            return
        rcx = uc.reg_read(UC_X86_REG_RCX)
        rdx = uc.reg_read(UC_X86_REG_RDX)
        r8 = uc.reg_read(UC_X86_REG_R8)
        if nm in ("memcpy", "memmove"):
            if r8:
                uc.mem_write(rcx, bytes(uc.mem_read(rdx, r8)))
            uc.reg_write(UC_X86_REG_RAX, rcx)
        elif nm == "memset":
            if r8:
                uc.mem_write(rcx, bytes([rdx & 0xff]) * r8)
            uc.reg_write(UC_X86_REG_RAX, rcx)
        elif nm == "strncat":
            d = rcx
            while bytes(uc.mem_read(d, 1)) != b"\x00":
                d += 1
            src = bytes(uc.mem_read(rdx, r8)).split(b"\x00")[0]
            uc.mem_write(d, src + b"\x00")
            uc.reg_write(UC_X86_REG_RAX, rcx)
        elif nm in ("malloc", "??2@YAPEAX_K@Z"):
            uc.reg_write(UC_X86_REG_RAX, self._halloc(rcx or 16))
        else:
            uc.reg_write(UC_X86_REG_RAX, 0)
        # the 0xC3 ret at this address then returns to caller

    # ---- primitives ----
    def wyhash(self, b):
        uc = self.uc
        p = self.SCR + 0x4000
        uc.mem_write(p, b + b"\x00" * 8)
        uc.reg_write(UC_X86_REG_RSP, self.rsp0)
        uc.mem_write(self.rsp0, struct.pack("<Q", RET_SENTINEL))
        uc.reg_write(UC_X86_REG_RCX, p)
        uc.reg_write(UC_X86_REG_RDX, len(b))
        uc.emu_start(HASH_FN, RET_SENTINEL, count=1_000_000)
        return uc.reg_read(UC_X86_REG_RAX)

    @staticmethod
    def _ror32(v, r):
        v &= 0xffffffff
        return ((v >> r) | (v << (32 - r))) & 0xffffffff

    def _state(self, seed):
        lo, hi = seed & 0xffffffff, (seed >> 32) & 0xffffffff
        return (lo or 1), (self._ror32(lo, 16) ^ hi ^ lo) & 0xffffffff

    def _driver(self, lo, hi, idx, mn, mx):
        uc = self.uc
        self._heap = self.HEAP
        uc.mem_write(self.STATE, struct.pack("<II", lo & 0xffffffff, hi & 0xffffffff))
        uc.mem_write(self.INPUT, struct.pack("<iii", idx, mn, mx))
        uc.mem_write(self.OUTPUT, b"\x00" * 0x40)
        uc.reg_write(UC_X86_REG_RSP, self.rsp0)
        uc.mem_write(self.rsp0, struct.pack("<Q", RET_SENTINEL))
        uc.reg_write(UC_X86_REG_RCX, self.SCR + 0x2000)
        uc.reg_write(UC_X86_REG_RDX, self.STATE)
        uc.reg_write(UC_X86_REG_R8, self.INPUT)
        uc.reg_write(UC_X86_REG_R9, self.OUTPUT)
        uc.emu_start(DRIVER, RET_SENTINEL, count=5_000_000)
        return bytes(uc.mem_read(self.OUTPUT, 0x40)).split(b"\x00")[0].decode("latin1")

    def generate(self, english, faction):
        """Reproduce the alien spelling for a lowercase english word + faction.
        Autophage output is returned in its rendered glyph form."""
        b = english.encode("utf-8")
        seed = self.wyhash(b)
        lo, hi = self._state(seed)
        idx = FACTION_IDX[faction]
        L = len(b)
        latin = self._driver(lo, hi, idx, max(1, L - 1), L + 1)
        if faction == "Autophage":
            return autophage_glyphs(latin)
        return latin


_singleton = None


def get_emu():
    global _singleton
    if _singleton is None:
        _singleton = NmsEmu()
    return _singleton
