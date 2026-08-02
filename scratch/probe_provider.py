"""Diagnose the recall regression: compare raw-score vs hybrid selection in CorrectionProvider."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = Path(__file__).with_suffix(".txt")
_fh = open(OUT, "w", encoding="utf-8")


def log(*args: object) -> None:
    print(*args, file=_fh, flush=True)


from teea.engine import TEEAEngine  # noqa: E402
from teea.nlp.edit_distance import tibetan_damerau  # noqa: E402

print("Initialising engine...", flush=True)
engine = TEEAEngine()
provider = engine._correction_provider
log("engine ready.")

# Membership checks
for w in ["བོདསྐད", "བོད", "སྐད", "དི", "དེ", "བདི", "བདེ", "སེས", "ཤེས"]:
    log(f"  in dict: {w} = {w in engine.dictionary}")
    log(f"  in provider._vocabulary: {w} = {w in provider._vocabulary}")


def analyze(word: str, sentence: str) -> None:
    word_norm = __import__("unicodedata").normalize("NFC", word)
    ws = sentence.find(word)
    we = ws + len(word)
    log(f"\n=== correct_with_score({word!r}) in {sentence!r}")
    cands = provider._find_candidates(word)
    log(f"  _find_candidates -> {cands!r}")
    valid = provider._validate_candidates(word, sentence, we, cands)
    log(f"  validated -> {valid!r}")
    if not valid:
        return
    try:
        raw = provider._score(sentence, ws, we, valid)
    except Exception as exc:  # noqa: BLE001
        log(f"  SCORING FAILED: {type(exc).__name__}: {exc}")
        return
    hybrid = {}
    canon = __import__("teea.plugins.builtin.correction", fromlist=["_canonical_tibetan_syllable"])._canonical_tibetan_syllable(word_norm)
    for c in valid:
        c_norm = __import__("unicodedata").normalize("NFC", c)
        dist = 0.5 if c_norm == canon else tibetan_damerau(word_norm, c_norm)
        ctx = 0.0
        if provider._corpus_repository is not None:
            try:
                ctx = provider._corpus_repository.get_context_score(sentence, ws, we, c)
            except Exception:  # noqa: BLE001
                ctx = 0.0
        hybrid[c] = (0.5 * raw.get(c, 0.0)) + (0.3 * ctx) - (dist * 0.15)
    for c in valid:
        log(f"    cand={c!r} raw={raw.get(c):.3f} hybrid={hybrid[c]:.3f} "
            f"in_vocab={c in provider._vocabulary}")
    raw_winner = max(valid, key=lambda c: (raw.get(c, 0.0), hybrid[c]))
    hybrid_winner = max(valid, key=lambda c: hybrid[c])
    log(f"  RAW-argmax winner   = {raw_winner!r} (raw {raw.get(raw_winner):.3f})")
    log(f"  HYBRID-argmax winner= {hybrid_winner!r} (raw {raw.get(hybrid_winner):.3f})")
    best, score = provider.correct_with_score(word, sentence, ws, we)
    log(f"  correct_with_score -> ({best!r}, {score:.3f})")


analyze("བོདསྐད", "ང་བོདསྐད་སྦྱོང་བྱེད་ཀྱི་ཡོད།")
analyze("དི", "དི་རིང་ང་བོད་སྐད་སློབ་སྦྱོང་བྱེད་ཀྱི་ཡོད།")
analyze("བདི", "བཀྲ་ཤིས་བདི་ལེགས།")
analyze("སེས", "སེས་ཡོན་མེད་ན་མུན་ནག་ནང་དུ་འགྲོ་བ་དང་འདྲ།")

# Sample synthetic errors of the types that regressed
syn_path = ROOT / "Data/SyntheticErrors/synthetic_errors.json"
with open(syn_path, encoding="utf-8") as f:
    syn = json.load(f)
records = syn.get("records", [])
target_types = {"VOWEL_MUTATION", "CHARACTER_CONFUSION", "PARTICLE_OMISSION", "SYLLABLE_SWAP", "TSHEG_DROP"}
picked = 0
for r in records:
    if not isinstance(r, dict):
        continue
    if r.get("error_type") not in target_types:
        continue
    if r.get("corrupted_text") == r.get("original_text"):
        continue
    corr, orig = r["corrupted_text"], r["original_text"]
    # find a differing token
    import re
    ct = [t for t in re.split(r"[་\s།]+", corr) if t]
    ot = [t for t in re.split(r"[་\s།]+", orig) if t]
    diff = [t for t in ct if t not in set(ot)]
    if not diff:
        continue
    analyze(diff[0], corr)
    picked += 1
    if picked >= 12:
        break
log(f"\n(picked {picked} synthetic records)")
_fh.close()
print(f"probe written to {OUT}", flush=True)
