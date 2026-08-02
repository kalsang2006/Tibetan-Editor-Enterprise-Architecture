"""Comprehensive unit tests for extended Tibetan grammar, particle agreement,
repeated words, and typography checking.
"""


from teea.core.types import TextSpan, utf8_byte_offsets
from teea.engine import TEEAEngine
from teea.nlp.dependency import DependencyTree
from teea.nlp.ner import EntityAnnotation
from teea.nlp.segmentation import Sentence
from teea.nlp.semantics import SemanticGraph, SentenceIntent
from teea.nlp.snapshot import DocumentSnapshot, SentenceAnalysis
from teea.nlp.snapshot.hashing import sentence_hash
from teea.nlp.terminology import TerminologyAnnotation
from teea.plugins.builtin.grammar import GrammarCheckerPlugin


def _make_empty_tree_snapshot(text: str) -> DocumentSnapshot:
    """Build a snapshot whose dependency tree has no nodes (no parse)."""
    byte_offsets = utf8_byte_offsets(text)
    sent_span = TextSpan(
        char_start=0,
        char_end=len(text),
        byte_start=byte_offsets[0],
        byte_end=byte_offsets[len(text)],
    )
    sent = Sentence(text=text, index=0, span=sent_span, terminator="")
    tree = DependencyTree(source=text, nodes=())
    entities = EntityAnnotation(source=text, entities=())
    terms = TerminologyAnnotation(source=text, terms=())
    graph = SemanticGraph(
        source=text,
        intent=SentenceIntent(mood="declarative", polarity="affirmative"),
        nodes=(),
        edges=(),
    )
    analysis = SentenceAnalysis(
        sentence=sent,
        tree=tree,
        entities=entities,
        terms=terms,
        graph=graph,
        content_hash=sentence_hash(text),
    )
    return DocumentSnapshot(source=text, analyses=(analysis,))


def test_genitive_particle_agreement():
    engine = TEEAEngine()

    # 'ང་ ཀྱི' is invalid after open vowel 'ང་' -> should be 'ང་ གི' or 'ང་ ཡི'
    unified = engine.analyze("ང་ ཀྱི དཔེ་ཆ།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Genitive particle agreement error" in s.message for s in suggestions)


def test_ergative_particle_agreement():
    engine = TEEAEngine()

    # 'དགེ་རྒན་ གིས' is invalid after final 'ན' -> should be 'དགེ་རྒན་ གྱིས'
    unified = engine.analyze("དགེ་རྒན་ གིས བཤད་པ།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Ergative particle agreement error" in s.message for s in suggestions)


def test_interrogative_particle_agreement():
    engine = TEEAEngine()

    # 'ཡོད་ གམ' is invalid after final 'ད' -> should be 'ཡོད་ དམ'
    unified = engine.analyze("ཁྱོད་ ཡོད་ གམ།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Interrogative particle agreement error" in s.message for s in suggestions)


def test_sentence_final_particle_agreement():
    engine = TEEAEngine()

    # 'ཡོད་ གོ' is invalid after final 'ད' -> should be 'ཡོད་ དོ'
    unified = engine.analyze("ང་ ཡོད་ གོ")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Sentence-final particle agreement error" in s.message for s in suggestions)


def test_duplicate_repeated_words():
    engine = TEEAEngine()

    # 'ང་ ང་' is duplicate repeated word
    unified = engine.analyze("ང་ ང་ བོད་སྐད་ སྦྱོང་གི་ཡོད།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Duplicate repeated word detected" in s.message for s in suggestions)


def test_duplicate_tsheg_spacing():
    engine = TEEAEngine()

    # 'བཀྲ་shis' with duplicate tshegs 'བཀྲ་་ཤིས'
    unified = engine.analyze("བཀྲ་་ཤིས།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.typography"]
    assert len(suggestions) >= 1
    assert any("Duplicate tsheg" in s.message for s in suggestions)


def test_particle_checks_run_when_tree_is_empty():
    """Basic particle agreement checks still run for empty-tree sentences.

    Regression: with no fallback, an empty dependency tree used to skip the
    whole sentence, so particle errors were never reported.
    """
    plugin = GrammarCheckerPlugin()

    # 'ང་ ཀྱི' triggers the genitive agreement rule. The existing
    # _get_tibetan_final_consonant helper treats single-consonant words like
    # 'ང' as "open", so the rule proposes 'ཡི' (pre-existing behaviour).
    text = "ང་ཀྱི་དཔེ་ཆ།"
    snapshot = _make_empty_tree_snapshot(text)
    suggestions = list(plugin.examine(snapshot))

    assert any("Genitive particle agreement error" in s.message for s in suggestions)
    genitive = [s for s in suggestions if "Genitive particle agreement error" in s.message]
    assert genitive[0].replacement == "ཡི"
    assert text[genitive[0].span.char_start : genitive[0].span.char_end] == "ཀྱི"
