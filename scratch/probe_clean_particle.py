"""Diagnose particle-omission rule clean-text FPs.

Runs the TEEA engine over the same 150 clean BoCorpus sentences used by
eval_unforeseen.py (seed 42, same length filters) and dumps, for every
TIB-PART-OMIT-001 firing: the a/b pair, the inserted particle, the raw corpus
bigram counts ((a,p), (p,b), bare (a,b)), whether the dependency tree was
empty (POS None), the POS categories of a and b, and whether the joined
compound ``a+tsheg+b`` is attested in the dictionary / corpus vocabulary.
"""
from __future__ import annotations

import re
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from teea.engine import TEEAEngine  # noqa: E402

SEED = 42
MAX_CLEAN_SENTENCES = 150
_TSHEG = "\u0f0b"
_STRIP_CHARS = "་ །ཿ\u0f0b\u0f0d "

out_lines: list[str] = []


def log(msg: str) -> None:
    out_lines.append(msg)


def main() -> None:
    import pandas as pd  # noqa: PLC0415

    parquet_path = ROOT / "Data/Corpus/BoCorpus/bo_corpus.parquet"
    df = pd.read_parquet(parquet_path, columns=["text"])
    texts = df["text"].dropna().tolist()
    rng = random.Random(SEED)
    sents: list[str] = []
    for t in texts:
        for s in re.split(r"[།]+", str(t)):
            s = s.strip()
            if 8 <= len(s) <= 120 and "་" in s and re.search(r"[\u0f40-\u0fbc]", s):
                sents.append(s + "།")
    rng.shuffle(sents)
    clean = sents[:MAX_CLEAN_SENTENCES]

    log(f"clean sentences: {len(clean)}")
    engine = TEEAEngine()
    log("engine ready")

    # Corpus / dictionary for the compound-attestation probe
    repo = None
    dictionary = None
    try:
        from teea.corpus.repository import BoCorpusRepository
        repo = BoCorpusRepository()
        log(f"corpus bigrams: {len(repo.bigrams)}, vocab: {len(repo.vocabulary)}")
    except Exception as exc:  # noqa: BLE001
        log(f"corpus repo unavailable: {exc}")

    def compound_attested(a: str, b: str) -> bool:
        """Is the joined form a+tsheg+b (and bare variants) attested anywhere?"""
        joined = a + _TSHEG + b
        # dictionary membership
        if dictionary is not None:
            try:
                if joined in dictionary or a + _TSHEG in dictionary or joined.strip(_STRIP_CHARS) in dictionary:
                    return True
            except Exception:  # noqa: BLE001
                pass
        # corpus vocabulary (tsheg-masked variants)
        if repo is not None:
            for cand in (joined, joined.rstrip(_TSHEG), a + b):
                try:
                    if repo.vocabulary.get(cand) or repo.get_syllable_frequency(cand):
                        return True
                except Exception:  # noqa: BLE001
                    pass
        return False

    def ngram_count(table: dict, *parts: str) -> int:
        if not table:
            return 0
        cleaned = [p.rstrip("་ །\u0f0b\u0f0d ") for p in parts]
        for mask in range(1 << len(parts)):
            tokens = [cleaned[j] + _TSHEG if (mask >> j) & 1 else cleaned[j] for j in range(len(parts))]
            count = table.get(" ".join(tokens))
            if count:
                return int(count)
        return 0

    from teea.nlp.postagging import PosCategory  # noqa: PLC0415

    total_fire = 0
    emitted_clean = 0
    empty_tree = 0
    for idx, s in enumerate(clean):
        unified = engine.analyze(s)
        part_fires = [
            sg for sg in unified.suggestions
            if sg.source == "teea.grammar" and "TIB-PART-OMIT" in (sg.message or "")
        ]
        edits = [sg for sg in unified.suggestions if sg.is_edit and sg.replacement]
        if edits:
            emitted_clean += 1
        # Recover tree emptiness + POS from the snapshot if reachable
        tree_empty = "?"
        try:
            snap = getattr(unified, "_snapshot", None)
            if snap is None:
                snap = getattr(unified, "snapshot", None)
            if snap is not None and snap.analyses:
                tree_empty = str(snap.analyses[0].tree.is_empty if snap.analyses[0].tree else "?")
                if snap.analyses[0].tree is not None and not snap.analyses[0].tree.is_empty:
                    empty_tree += 0
                elif snap.analyses[0].tree is not None:
                    empty_tree += 1
        except Exception as exc:  # noqa: BLE001
            tree_empty = f"err:{exc}"
        if not part_fires:
            continue
        total_fire += 1
        log(f"\n--- clean[{idx}] tree_empty={tree_empty} emitted_edit={bool(edits)} ---")
        log(f"text: {s[:80]}")
        for sg in part_fires:
            # Parse the message for a and b
            msg = sg.message or ""
            m = re.search(r'between "([^"]+)" and "([^"]+)"', msg)
            if not m:
                log(f"  {msg}")
                continue
            a, b = m.group(1), m.group(2)
            a_last = a.split(_TSHEG)[-1] if _TSHEG in a else a
            from teea.plugins.builtin.grammar import _get_tibetan_final_consonant, GENITIVE_PARTICLES  # noqa: PLC0415
            final_c = _get_tibetan_final_consonant(a_last)
            particle = GENITIVE_PARTICLES.get(final_c)
            counts = {
                "a_p": ngram_count(repo.bigrams, a_last, particle) if repo else -1,
                "p_b": ngram_count(repo.bigrams, particle, b) if repo else -1,
                "bare": ngram_count(repo.bigrams, a_last, b) if repo else -1,
            }
            log(
                f"  FIRE a={a!r} b={b!r} particle={particle!r} counts={counts} "
                f"compound_attested={compound_attested(a, b)} "
                f"score={sg.score} repl={sg.replacement!r} span={sg.span.char_start}-{sg.span.char_end}"
            )

    log(f"\n=== SUMMARY ===")
    log(f"clean with any edit: {emitted_clean}/{len(clean)}")
    log(f"sentences with >=1 particle fire: {total_fire}")
    log(f"empty-tree first-analyses: {empty_tree}")

    out = ROOT / "scratch/probe_clean_particle.txt"
    out.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"wrote {out} ({len(out_lines)} lines)")


if __name__ == "__main__":
    main()
