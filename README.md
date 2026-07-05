# NMS Language Translator

Paste romanized alien text from *No Man's Sky*, detect which language it is
(Gek, Korvax, Vy'keen, Autophage, Atlas), and translate it to English.

The site is a static page: [index.html](index.html) loads
[data/languages.json](data/languages.json) and does all lookup in the browser.
No backend.

## How the data is made

Alien spellings are **procedurally generated at runtime** inside `NMS.exe`, not
stored on disk. The generator was reverse-engineered and is reproduced
byte-exactly by emulating the real code with Unicorn.

Recipe per word: `alien = generator( state = f(wyhash(english, len)),
idx = faction_index, length = english_length +/- 1 )`. Autophage additionally
applies a display cipher (Greek letters + digits).

### Regenerating the dictionary (needs the game executable)

```
pip install unicorn pefile
# point at your own copy of the game binary:
set NMS_EXE=...\No Man's Sky\Binaries\NMS.exe   # (or export on *nix)

python scripts/extract_english.py    # MBIN -> data/words_by_faction.json
python scripts/gen_words.py --verify # gate: reproduce data/rosetta.json exactly
python scripts/gen_words.py --all    # -> data/languages.json  (the shipped dataset)
```

The executable is required only to regenerate the data. End users never need it;
the committed `data/languages.json` is all the site loads.

## Verification

`gen_words.py --verify` reproduces every known (alien, english, faction) pair in
`data/rosetta.json` exactly and deterministically. All five languages are
confirmed against in-game / wiki ground truth.

## Files

- `index.html`, `styles.css`, `app.js` — the static translator.
- `data/languages.json` — `{ faction: { alienWordLower: { en, def } } }`.
- `data/words_by_faction.json` — extracted English words + faction.
- `data/rosetta.json` — verification pairs.
- `scripts/` — extraction + generation pipeline (re-runnable).
