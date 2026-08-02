"""Debug probe: inspect engine suggestions on the key handcrafted/foreseen cases."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = Path(__file__).with_suffix(".txt")
_fh = open(OUT, "w", encoding="utf-8")


def log(*args: object) -> None:
    print(*args, file=_fh, flush=True)


from teea.engine import TEEAEngine  # noqa: E402

CASES = [
    ("VOWEL_MUTATION", "བཀྲ་ཤིས་བདི་ལེགས།"),
    ("VOWEL_MUTATION2", "དི་རིང་ང་བོད་སྐད་སློབ་སྦྱོང་བྱེད་ཀྱི་ཡོད།"),
    ("CHAR_CONF_1", "སློབ་སྦྱོབ་ནི་གལ་ཆེ་བ་ཞིག་ཡིན།"),
    ("CHAR_CONF_2", "སེས་ཡོན་མེད་ན་མུན་ནག་ནང་དུ་འགྲོ་བ་དང་འདྲ།"),
    ("PARTICLE_OMISSION", "སློབ་སྦྱོང་གལ་གནད་སྐོར་བཤད་པ།"),
    ("SYLLABLE_SWAP", "ང་སྐད་བོད་སྦྱོང་བྱེད་ཀྱི་ཡོད།"),
    ("TSHEG_DROP", "ང་བོདསྐད་སྦྱོང་བྱེད་ཀྱི་ཡོད།"),
    ("CLEAN1", "གནད་དོན་འདི་བཤད་པར་བྱའོ། འཇིག་རྟེན་གསོན་པོའི་དཔེ་དེབ་ཤེས་རིག་བཟང་པོ་འདི་ཡིས་ནུས་པ་གཏན་ཏན་ཐོན་ནོ།"),
]

print("Initialising engine...", flush=True)
engine = TEEAEngine()
log("ready.")

# Dictionary membership probes
dict_repo = engine.dictionary
for w in ["བདེ", "བདི", "གལ", "ཤེས", "སེས", "སྦྱོང", "སྦྱོབ", "དེ", "དི", "རིང"]:
    log(f"  dict contains {w}: {w in dict_repo}")

# Corpus bigram key-format verification for TIB-PART-OMIT-001:
# rule builds keys via _ngram_count (tsheg-mask variants of 'a p' / 'p b').
# Confirm the repository actually stores such keys and that a real attested
# pair like (སྦྱོང, གི) or (གི, གལ) is present under some variant.
log("\n=== corpus bigram key format ===")
repo = getattr(engine, "_corpus_repository", None)
if repo is None:
    log("  engine._corpus_repository is None (grammar rules inert!)")
else:
    bg = repo.bigrams
    log(f"  bigrams total keys: {len(bg)}")
    # Grammar rule calls _ngram_count(bigrams, a_last, particle) etc.
    from teea.plugins.builtin.grammar import GENITIVE_PARTICLES, _get_tibetan_final_consonant
    pairs = [("སྦྱོང", "གི"), ("གི", "གལ"), ("སྦྱོང", "གལ"), ("གནད", "སྐོར"), ("སྐོར", "བཤད")]
    for a, b in pairs:
        hits = [k for k in bg if k.startswith(a.rstrip("་") + " ") and k.split(" ")[0].rstrip("་") == a.rstrip("་") and k.split(" ")[-1].rstrip("་") == b.rstrip("་")]
        log(f"  key variant hit for ('{a}','{b}'): {hits[:4]}")
    # simulate the rule's decision on the PARTICLE_OMISSION case
    a_last = "སྦྱོང"
    b = "གལ"
    final_c = _get_tibetan_final_consonant(a_last)
    p = GENITIVE_PARTICLES.get(final_c)
    log(f"  final_c={final_c!r} particle={p!r} for a_last={a_last}")
    def ngram(table, *parts):
        _T = "\u0f0b"
        cleaned = [pp.rstrip("་ །\u0f0b\u0f0d ") for pp in parts]
        for mask in range(1 << len(parts)):
            tokens = [cleaned[j] + _T if (mask >> j) & 1 else cleaned[j] for j in range(len(parts))]
            c = table.get(" ".join(tokens))
            if c:
                return int(c)
        return 0
    log(f"  ngram(a_last,b)={ngram(bg, a_last, b)}  ngram(a_last,p)={ngram(bg, a_last, p)}  ngram(p,b)={ngram(bg, p, b)}")

for label, text in CASES:
    log(f"\n=== {label}: {text}")
    unified = engine.analyze(text)
    for s in unified.suggestions:
        repl = s.replacement if s.replacement is not None else "<advisory>"
        log(f"  [{s.source}] {s.error_type} {s.priority.value:6s} score={s.score:.2f} "
            f"span=({s.span.char_start},{s.span.char_end}) -> {repl}")
        log(f"      msg: {s.message[:110]}")
    for r in unified.rejected:
        log(f"  REJECTED({r.reason.value}): {r.suggestion.source} "
            f"span=({r.suggestion.span.char_start},{r.suggestion.span.char_end}) "
            f"-> {r.suggestion.replacement}")
    corrected = unified.patch.apply() if unified.patch else text
    log(f"  corrected: {corrected}")

_fh.close()
print(f"probe written to {OUT}", flush=True)
