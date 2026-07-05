"""Generate NMS alien spellings by reproducing the in-game generator.

Usage:
  python gen_words.py --verify        # T6 GATE: reproduce rosetta.json pairs exactly + determinism
  python gen_words.py --all           # T7: generate data/languages.json for all words

Needs NMS.exe (see nms_emu.EXE / set NMS_EXE). The generated languages.json is
static; the web app reads it and never touches the executable.
"""
import sys
import os
import json
import argparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nms_emu

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def verify():
    emu = nms_emu.get_emu()
    pairs = load("rosetta.json")
    ok = True
    print(f"Verifying {len(pairs)} rosetta pairs (V12) + determinism (V13)\n")
    for p in pairs:
        eng, faction, expect = p["english"], p["faction"], p["alien"]
        got1 = emu.generate(eng, faction)
        got2 = emu.generate(eng, faction)
        determ = got1 == got2
        match = got1 == expect
        ok = ok and match and determ
        flag = "OK " if match else "FAIL"
        d = "" if determ else "  <NON-DETERMINISTIC>"
        print(f"  [{flag}] {faction:8} {eng:12} -> {got1!r}  expected {expect!r}{d}")
    print()
    if ok:
        print("V12/V13 GATE: PASS (100% of oracle reproduced, deterministic)")
        return 0
    print("V12/V13 GATE: FAIL")
    return 1


# Confirmed meta-words not present in the MBIN word list: each faction's own
# name for its language (user-confirmed in-game). Injected so the translator
# recognises them. def = short gloss.
LANGUAGE_NAME_WORDS = {
    "Gek": [("gek", "the Gek language")],
    "Korvax": [("korvax", "the Korvax language")],
    "Vy'keen": [("vy'keen", "the Vy'keen language")],
    "Atlas": [("atlas", "the Atlas language")],
}


def generate_all():
    emu = nms_emu.get_emu()
    words = load("words_by_faction.json")
    out = {}
    counts = {}
    for faction, entries in words.items():
        verified = faction in nms_emu.FACTION_VERIFIED
        lang = {}
        for key, rec in entries.items():
            eng = rec["en"]
            alien = emu.generate(eng, faction)
            if not alien:
                continue
            lang[alien.lower()] = {"en": eng, "def": rec.get("def")}
        for eng, gloss in LANGUAGE_NAME_WORDS.get(faction, []):
            alien = emu.generate(eng, faction)
            if alien:
                lang.setdefault(alien.lower(), {"en": eng, "def": gloss})
        out[faction] = lang
        counts[faction] = (len(lang), verified)
    outpath = os.path.join(DATA, "languages.json")
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print("wrote", os.path.normpath(outpath))
    for faction, (n, ver) in counts.items():
        tag = "verified" if ver else "UNVERIFIED (no oracle pair; idx is best-guess)"
        print(f"  {faction:10} {n:5} words  [{tag}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="T6 gate: reproduce rosetta pairs")
    ap.add_argument("--all", action="store_true", help="T7: generate languages.json")
    args = ap.parse_args()
    if args.verify:
        sys.exit(verify())
    elif args.all:
        generate_all()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
