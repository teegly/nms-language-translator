"""
extract_english.py  (SPEC T2)

Extract the complete NMS learnable-word list, tagged by faction, from the
game's English localisation MBIN. Output: data/words_by_faction.json.

Data source: NMSARC.MetadataEtc.pak -> language/nms_loc1_english.mbin
The MBIN is a TkLocalisation table. Each entry has:
  - an Id string  (ASCII, e.g. "TRA_FEDERATION")
  - a value pointer at Id_offset + 0x40: int64 relative-offset + int32 length,
    pointing at the localised English string ("federation").

Learnable-word entries have Id = <FACTION_PREFIX>_<WORD>, prefix mapping
(confirmed against the in-game translation-computer template + user-verified
words):
    TRA -> Gek        WAR -> Vy'keen     EXP -> Korvax
    BUI -> Autophage  ATLAS -> Atlas

Word entries are isolated by (a) the faction-prefixed Id and (b) the value
string living inside the alphabetical word-value heap (offset region), which
separates them from UI strings that share the same prefix.

Only the standard library + hgpaktool are used. Re-runnable; writes nothing to
the game install.
"""
import argparse
import json
import re
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

FACTION = {
    "TRA": "Gek",
    "WAR": "Vy'keen",
    "EXP": "Korvax",
    "BUI": "Autophage",
    "ATLAS": "Atlas",
}
VALUE_PTR_OFFSET = 0x40  # bytes from Id start to the value-string pointer field
ID_RE = re.compile(rb"(TRA|WAR|EXP|BUI|ATLAS)_[A-Z0-9]+\x00")

# Point NMS_PAK at your own copy of the game archive. Falls back to a
# repo-relative GAMEDATA/ dir (game files are gitignored, never committed).
DEFAULT_PAK = Path(os.environ.get(
    "NMS_PAK",
    Path(__file__).resolve().parent.parent / "GAMEDATA" / "PCBANKS" / "NMSARC.MetadataEtc.pak",
))
MBIN_MEMBER = "language/nms_loc1_english.mbin"


def extract_mbin(pak: Path, out_dir: Path) -> Path:
    """Unpack just the English loc1 MBIN from the pak via hgpaktool."""
    subprocess.run(
        [sys.executable, "-m", "hgpaktool.cli", "-O", str(out_dir),
         "-f", MBIN_MEMBER, str(pak)],
        check=False, capture_output=True,
    )
    found = list(out_dir.rglob("nms_loc1_english.mbin"))
    if not found:
        sys.exit(f"ERROR: could not extract {MBIN_MEMBER} from {pak}")
    return found[0]


def read_value(data: bytes, id_pos: int):
    """Resolve the English value string for an Id at id_pos."""
    fld = id_pos + VALUE_PTR_OFFSET
    if fld + 12 > len(data):
        return None, None
    rel = struct.unpack_from("<q", data, fld)[0]
    ln = struct.unpack_from("<i", data, fld + 8)[0]
    tgt = fld + rel
    if not (0 < ln < 200 and 0 <= tgt < len(data)):
        return None, None
    return data[tgt:tgt + ln - 1].decode("latin1"), tgt


def parse(mbin: Path) -> dict:
    data = mbin.read_bytes()

    # First pass: resolve every faction-prefixed entry, record value target
    # offsets so we can locate the word-value heap (the dense cluster).
    raw = []
    for m in ID_RE.finditer(data):
        ids = m.group()[:-1].decode()
        val, tgt = read_value(data, m.start())
        if val is not None:
            raw.append((ids, val, tgt))

    # Word-value heap = the 200k-byte bucket holding the vast majority of
    # resolved values (UI strings scatter elsewhere).
    from collections import Counter
    buckets = Counter(tgt // 200_000 for _, _, tgt in raw)
    heap_bucket = buckets.most_common(1)[0][0]
    heap_lo = (heap_bucket - 1) * 200_000  # small margin

    langs = {name: {} for name in FACTION.values()}
    for ids, val, tgt in raw:
        if tgt < heap_lo:
            continue  # UI string, not a learnable word
        prefix = ids.split("_", 1)[0]
        faction = FACTION[prefix]
        # key = lowercased English word; value carries display-case en + def slot
        langs[faction][val.lower()] = {"en": val, "def": None}
    return langs


def main():
    ap = argparse.ArgumentParser(description="Extract NMS words by faction.")
    ap.add_argument("--pak", type=Path, default=DEFAULT_PAK,
                    help="Path to NMSARC.MetadataEtc.pak")
    ap.add_argument("--mbin", type=Path, default=None,
                    help="Path to an already-extracted nms_loc1_english.mbin "
                         "(skips hgpaktool)")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent.parent
                    / "data" / "words_by_faction.json")
    args = ap.parse_args()

    if args.mbin:
        mbin = args.mbin
    else:
        tmp = Path(tempfile.mkdtemp(prefix="nmsx_"))
        mbin = extract_mbin(args.pak, tmp)

    langs = parse(mbin)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(langs, f, ensure_ascii=False, indent=1, sort_keys=True)

    print(f"wrote {args.out}")
    total = 0
    for name, words in langs.items():
        print(f"  {name:10} {len(words):5} words")
        total += len(words)
    print(f"  {'TOTAL':10} {total:5}")


if __name__ == "__main__":
    main()
