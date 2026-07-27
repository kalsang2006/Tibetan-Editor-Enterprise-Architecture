"""Shared pytest fixtures for the tokenization test suite.

Fixtures load the **real** classical-Tibetan corpus and lexicon samples that
were extracted from the authoritative project repository, so unit tests run
against authentic Tibetan rather than invented strings. Model-dependent tests
use a fake backend (see :mod:`tests.fakes`) injected into the real
:class:`~teea.nlp.tokenization.TiBERTTokenizer`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from teea.core.config import TokenizationSettings
from teea.nlp.dependency import TibetanDependencyParser
from teea.nlp.morphology import TibetanMorphologicalAnalyzer
from teea.nlp.ner import TibetanEntityRecognizer
from teea.nlp.postagging import HmmPosTagger
from teea.nlp.segmentation import TibetanSentenceSegmenter
from teea.nlp.semantics import TibetanSemanticAnalyzer
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.nlp.terminology import GlossaryTerminologyRecognizer
from teea.nlp.tokenization import (
    SyllableSegmenter,
    TextNormalizer,
    TiBERTTokenizer,
)
from teea.nlp.tokenization.tibert import BackendTokenizer
from teea.persistence import (
    InMemoryDictionaryRepository,
    InMemoryGazetteer,
    InMemoryTerminology,
    InMemoryVerbLexicon,
    default_dictionary,
    default_gazetteer,
    default_terminology,
    default_verb_lexicon,
)
from tests.fakes import FakeBackendTokenizer

_DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Directory containing real corpus/lexicon fixtures."""
    return _DATA_DIR


@pytest.fixture(scope="session")
def corpus_sentences() -> list[str]:
    """Real classical-Tibetan sentences (Milarepa corpus), one per line."""
    text = (_DATA_DIR / "mila_sentences.txt").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


@pytest.fixture(scope="session")
def lexicon_sample() -> list[str]:
    """Real classical-lexicon entries (edge-shaped: bare syllables, particles)."""
    raw = (_DATA_DIR / "lexicon_sample.json").read_text(encoding="utf-8")
    return list(json.loads(raw))


def _read_tagged(path: Path) -> list[list[tuple[str, str]]]:
    """Parse a ``surface|tag`` annotated corpus file into per-line pairs."""
    lines: list[list[tuple[str, str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        pairs = [
            (token.split("|", 1)[0], token.split("|", 1)[1])
            for token in line.split()
            if "|" in token
        ]
        if pairs:
            lines.append(pairs)
    return lines


@pytest.fixture(scope="session")
def heldout_corpus() -> list[list[tuple[str, str]]]:
    """Gold annotations from a text the POS model was **not** built from.

    The Dictionary Repository is derived from the Milarepa text; this excerpt
    comes from the Marpa text, a different work by a different author. Measuring
    against it reports generalisation rather than recall of training data.
    """
    return _read_tagged(_DATA_DIR / "marpa_tagged_sample.txt")


@pytest.fixture(scope="session")
def tagged_corpus() -> list[list[tuple[str, str]]]:
    """Gold-standard morpheme annotations from the reference corpus.

    Each entry is one line of the corpus as ``(surface, tag)`` pairs, taken
    verbatim from ``Data/Texts/mila-horizontal.txt``. Because the annotation
    separates grammatical morphemes into their own tokens, it doubles as
    ground truth for morpheme boundaries: concatenating the surfaces gives
    running Tibetan, and the token boundaries are the correct segmentation.
    """
    return _read_tagged(_DATA_DIR / "mila_tagged_sample.txt")


@pytest.fixture(scope="session")
def corpus_document(corpus_sentences: list[str]) -> str:
    """The corpus as one multi-paragraph document.

    Sentence segmentation (Stage 4) is a document-level concern, so it needs an
    input with both shad-terminated sentences and paragraph structure. Joining
    the real corpus in groups of four produces exactly that, without inventing
    any Tibetan.
    """
    paragraphs = [
        "".join(corpus_sentences[index : index + 4])
        for index in range(0, len(corpus_sentences), 4)
    ]
    return "\n\n".join(paragraphs)


@pytest.fixture
def settings() -> TokenizationSettings:
    """Default tokenization settings."""
    return TokenizationSettings()


@pytest.fixture
def normalizer() -> TextNormalizer:
    """A default NFC normalizer."""
    return TextNormalizer(form="NFC")


@pytest.fixture
def segmenter() -> SyllableSegmenter:
    """A syllable segmenter."""
    return SyllableSegmenter()


@pytest.fixture
def sentence_segmenter() -> TibetanSentenceSegmenter:
    """A sentence segmenter with default (prose) boundary rules."""
    return TibetanSentenceSegmenter()


@pytest.fixture
def morphological_analyzer() -> TibetanMorphologicalAnalyzer:
    """A morphological analyzer with default settings."""
    return TibetanMorphologicalAnalyzer()


@pytest.fixture(scope="session")
def dictionary() -> InMemoryDictionaryRepository:
    """The shipped, corpus-derived Dictionary Repository."""
    return default_dictionary()


@pytest.fixture
def pos_tagger() -> HmmPosTagger:
    """A part-of-speech tagger backed by the shipped repository."""
    return HmmPosTagger()


@pytest.fixture
def dependency_parser() -> TibetanDependencyParser:
    """A dependency parser with default attachment rules."""
    return TibetanDependencyParser()


@pytest.fixture(scope="session")
def gazetteer() -> InMemoryGazetteer:
    """The shipped, corpus-derived proper-noun gazetteer."""
    return default_gazetteer()


@pytest.fixture
def entity_recognizer() -> TibetanEntityRecognizer:
    """An entity recogniser backed by the shipped gazetteer."""
    return TibetanEntityRecognizer()


@pytest.fixture(scope="session")
def terminology() -> InMemoryTerminology:
    """The shipped, corpus-derived terminology glossary."""
    return default_terminology()


@pytest.fixture
def terminology_recognizer() -> GlossaryTerminologyRecognizer:
    """A terminology recogniser backed by the shipped glossary."""
    return GlossaryTerminologyRecognizer()


@pytest.fixture(scope="session")
def verb_lexicon() -> InMemoryVerbLexicon:
    """The shipped verb lexicon: lemmas and attested argument frames."""
    return default_verb_lexicon()


@pytest.fixture
def semantic_analyzer() -> TibetanSemanticAnalyzer:
    """A semantic analyser backed by the shipped verb lexicon."""
    return TibetanSemanticAnalyzer()


@pytest.fixture
def snapshot_builder() -> LanguageServerSnapshotBuilder:
    """The whole Language Server: Stages 04 -> 11 wired into Stage 12."""
    return LanguageServerSnapshotBuilder()


@pytest.fixture
def make_tokenizer() -> Callable[..., TiBERTTokenizer]:
    """Factory building a TiBERTTokenizer backed by a configurable fake.

    Returns a callable accepting optional ``settings``, ``is_fast`` and
    ``unk_surface`` arguments.
    """

    def _factory(
        *,
        settings: TokenizationSettings | None = None,
        is_fast: bool = True,
        unk_surface: str | None = None,
    ) -> TiBERTTokenizer:
        resolved = settings or TokenizationSettings()

        def loader(_: TokenizationSettings) -> BackendTokenizer:
            return FakeBackendTokenizer(is_fast=is_fast, unk_surface=unk_surface)

        return TiBERTTokenizer(resolved, loader=loader)

    return _factory


@pytest.fixture
def tokenizer(make_tokenizer: Callable[..., TiBERTTokenizer]) -> TiBERTTokenizer:
    """A fake-backed TiBERTTokenizer with default (fast) behavior."""
    return make_tokenizer()