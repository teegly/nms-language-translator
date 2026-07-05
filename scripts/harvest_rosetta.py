"""
harvest_rosetta.py  (SPEC T3)

Build the ground-truth verification oracle for the alien-word generator.

Two sources, merged + deduped into data/rosetta.json:
  1. USER-CONFIRMED pairs (hand-verified in-game) - the trusted seed (SPEC V18).
  2. RAM harvest - the running NMS.exe caches rendered "word pages" for words
     the save has learned / recently viewed. Each cached page matches the
     template:
       The <TRANS_XXX>Faction<> word <STELLAR>"<alien>"<>, which is rendered
       by the Exosuit's translation computer as <STELLAR>"<english>"<>.
     TRANS prefix -> faction (TRA Gek, WAR Vy'keen, EXP Korvax, BUI Autophage,
     ATLAS Atlas).

Read-only: uses ReadProcessMemory via pymem. Never writes the process or saves.
Re-runnable: merges new finds into the existing rosetta.json each pass. Drive
the in-game catalogue (Words Collected, each faction) between passes to grow
coverage.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import re
from pathlib import Path

TRANS = {"TRA": "Gek", "WAR": "Vy'keen", "EXP": "Korvax",
         "BUI": "Autophage", "ATLAS": "Atlas"}

# User-confirmed ground truth (SPEC V18). alien -> (english, faction)
USER_PAIRS = [
    ("evykelordur", "federation", "Gek"),
    ("agodskovd", "research", "Korvax"),
    ("doxongh", "warrior", "Vy'keen"),
]

TEMPLATE = re.compile(
    rb'The <TRANS_(TRA|WAR|EXP|BUI|ATLAS)>[\w\'\- ]+<> word'
    rb' <STELLAR>"([^"]{1,60})"<>, which is rendered by the\s+'
    rb'Exosuit\'s translation computer as <STELLAR>"([^"]{1,60})"<>',
    re.S,
)

OUT = Path(__file__).resolve().parent.parent / "data" / "rosetta.json"


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


def harvest_ram():
    import pymem
    pm = pymem.Pymem("NMS.exe")
    k = ctypes.windll.kernel32
    addr, mbi, out = 0, MBI(), []
    while addr < 0x7FFFFFFFFFFF:
        if not k.VirtualQueryEx(pm.process_handle, ctypes.c_void_p(addr),
                                ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        size = mbi.RegionSize
        if (mbi.State == 0x1000 and mbi.Protect != 0x01
                and not (mbi.Protect & 0x100) and size < 2_000_000_000):
            try:
                data = pm.read_bytes(addr, size)
                for m in TEMPLATE.finditer(data):
                    pfx, alien, eng = (x.decode("latin1") for x in m.groups())
                    if "%" in alien or "%" in eng:  # skip blank template
                        continue
                    out.append((alien, eng, TRANS[pfx]))
            except Exception:
                pass
        addr += size
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ram", action="store_true",
                    help="skip RAM harvest (seed with user pairs only)")
    args = ap.parse_args()

    pairs = {}  # (alien, faction) -> english
    for alien, eng, fac in USER_PAIRS:
        pairs[(alien, fac)] = eng

    if OUT.exists():  # merge prior harvests
        for r in json.loads(OUT.read_text(encoding="utf-8")):
            pairs[(r["alien"], r["faction"])] = r["english"]

    if not args.no_ram:
        try:
            for alien, eng, fac in harvest_ram():
                pairs[(alien, fac)] = eng
        except Exception as e:
            print(f"RAM harvest skipped ({e}); is NMS running?")

    rows = [{"alien": a, "english": e, "faction": f}
            for (a, f), e in sorted(pairs.items())]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter
    per = Counter(r["faction"] for r in rows)
    print(f"wrote {OUT}  ({len(rows)} pairs)")
    for fac in TRANS.values():
        n = per.get(fac, 0)
        flag = "OK" if n >= 5 else "NEED >=5 (V15)"
        print(f"  {fac:10} {n:4}  {flag}")


if __name__ == "__main__":
    main()
