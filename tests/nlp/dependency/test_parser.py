"""Unit tests for :class:`~teea.nlp.dependency.parser.TibetanDependencyParser`.

Three concerns, in order of weight.

**Guarantees.** The parser promises a single rooted, acyclic tree covering every
input morpheme with its span unchanged, for any input. That is asserted over the
whole reference corpus, not just on chosen examples, because the guarantee is
what downstream stages recurse over.

**Linguistic behaviour.** Attachment is driven by case marking, following the
Tibetan constraint grammars in the authoritative data repository. The cases here
are hand-constructed so the expected analysis is unambiguous: an agentive marks
the agent, an unmarked nominal is the absolutive, a genitive marks a possessor,
modifiers follow their head noun, and the clause head is the final verb.

**Honest limits.** There is no Tibetan dependency treebank in the project's data
repository, so no attachment-accuracy figure (UAS/LAS) can be reported. What is
measured instead is the *unresolved rate* -- how often no rule applies -- which
is the quality signal actually available.
"""

from __future__ import annotations

import itertools

import pytest

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.dependency import (
    DependencyParser,
    DependencyRelation,
    DependencyTree,
    TibetanDependencyParser,
)
from teea.nlp.morphology import Morpheme, MorphemeKind, TibetanMorphologicalAnalyzer
from teea.nlp.postagging import (
    HmmPosTagger,
    PosCategory,
    TaggedMorpheme,
    TaggedText,
    coarse_category,
)

TSHEG = "་"


# -- Helpers ------------------------------------------------------------------
def build(*pairs: tuple[str, str]) -> TaggedText:
    """Build a TaggedText directly from ``(surface, tag)`` pairs.

    Constructing Stage 7 output by hand isolates the parser from the tagger, so
    a syntactic expectation cannot fail because the tagger chose a different
    part of speech. The surfaces are joined with a tsheg, as Tibetan writes
    them, and every span is exact.
    """
    source = TSHEG.join(surface for surface, _ in pairs) + TSHEG
    offsets = utf8_byte_offsets(source)
    morphemes: list[TaggedMorpheme] = []
    cursor = 0
    for surface, tag in pairs:
        start, end = cursor, cursor + len(surface)
        morphemes.append(
            TaggedMorpheme(
                morpheme=Morpheme(
                    text=surface,
                    span=TextSpan(
                        char_start=start,
                        char_end=end,
                        byte_start=offsets[start],
                        byte_end=offsets[end],
                    ),
                    kind=MorphemeKind.ROOT,
                ),
                tag=tag,
                category=coarse_category(tag),
            )
        )
        cursor = end + len(TSHEG)
    return TaggedText(source=source, morphemes=tuple(morphemes))


def relation_of(tree: DependencyTree, text: str) -> DependencyRelation:
    """Return the relation of the (unique) node whose surface is ``text``."""
    matches = [node for node in tree.nodes if node.text == text]
    assert len(matches) == 1, f"{text!r} is not unique in {tree.relations}"
    return matches[0].relation


def head_text(tree: DependencyTree, text: str) -> str | None:
    matches = [node for node in tree.nodes if node.text == text]
    assert len(matches) == 1
    head = tree.head_of(matches[0].index)
    return None if head is None else head.text


def assert_is_a_tree(tree: DependencyTree, expected_nodes: int) -> None:
    """Structural guarantees, re-derived rather than trusted."""
    assert tree.num_nodes == expected_nodes
    roots = [n for n in tree.nodes if n.is_root]
    assert len(roots) == 1
    for node in tree.nodes:
        seen: set[int] = set()
        current = node.index
        while not tree.nodes[current].is_root:
            assert current not in seen, "cycle"
            seen.add(current)
            current = tree.nodes[current].head
        assert current == roots[0].index


# -- Protocol and configuration -----------------------------------------------
def test_satisfies_the_dependency_parser_protocol(
    dependency_parser: TibetanDependencyParser,
) -> None:
    assert isinstance(dependency_parser, DependencyParser)


def test_genitive_attachment_flag_reflects_construction() -> None:
    assert TibetanDependencyParser().attach_genitive_to_following_nominal is True
    assert (
        TibetanDependencyParser(
            attach_genitive_to_following_nominal=False
        ).attach_genitive_to_following_nominal
        is False
    )


# -- Totality -----------------------------------------------------------------
def test_an_empty_input_yields_an_empty_tree(
    dependency_parser: TibetanDependencyParser,
) -> None:
    tree = dependency_parser.parse(TaggedText(source=""))
    assert tree.is_empty
    assert tree.root is None
    assert tree.source == ""


def test_a_single_morpheme_becomes_the_root(
    dependency_parser: TibetanDependencyParser,
) -> None:
    tree = dependency_parser.parse(build(("ཁྱིམ", "n.count")))
    assert_is_a_tree(tree, 1)
    assert tree.root is not None
    assert tree.root.text == "ཁྱིམ"


# -- Root selection (Tibetan is verb-final) -----------------------------------
def test_the_final_verb_heads_the_sentence(
    dependency_parser: TibetanDependencyParser,
) -> None:
    tree = dependency_parser.parse(
        build(("ཁྱིམ", "n.count"), ("བཟོས", "v.past"), ("སོང", "v.past"))
    )
    assert tree.root is not None
    assert tree.root.text == "སོང", "Tibetan is verb-final; the last verb heads"


def test_a_verbless_fragment_is_headed_by_its_last_nominal(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """Headings and list items have no verb but must still form a tree."""
    tree = dependency_parser.parse(build(("མི", "n.count"), ("ཁྱིམ", "n.count")))
    assert_is_a_tree(tree, 2)
    assert tree.root is not None
    assert tree.root.text == "ཁྱིམ"


def test_an_auxiliary_does_not_head_the_clause(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """Auxiliaries support a main verb rather than heading one."""
    tree = dependency_parser.parse(
        build(("ཁྱིམ", "n.count"), ("བཟོས", "v.past"), ("ཡིན", "v.cop"))
    )
    assert tree.root is not None
    assert tree.root.text == "བཟོས"
    assert relation_of(tree, "ཡིན") is DependencyRelation.AUX


def test_a_deverbal_noun_does_not_head_the_clause(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """The constraint grammars count VerbForm=Vnoun among Head_NOUN."""
    tree = dependency_parser.parse(build(("འགྲོ་བ", "n.v.invar"), ("སོང", "v.past")))
    assert tree.root is not None
    assert tree.root.text == "སོང"


# -- Subject and object detection (Figure 5) ----------------------------------
def test_an_agentive_marked_nominal_is_the_agent(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """SETPARENT Head_NOUN (1* (Case=Agn)) TO (*1 (VERB)) -> arg1."""
    tree = dependency_parser.parse(
        build(("མི", "n.count"), ("ཀྱིས", "case.agn"), ("ཁྱིམ", "n.count"), ("བཟོས", "v.past"))
    )
    assert relation_of(tree, "མི") is DependencyRelation.ARG1
    assert head_text(tree, "མི") == "བཟོས"
    assert [n.text for n in tree.subjects] == ["མི"]


def test_ergative_alignment_makes_the_absolutive_an_object_when_an_agent_is_present(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """Tibetan is ergative-absolutive.

    With an agentive present the clause is transitive, so the unmarked nominal
    is the patient rather than a second subject.
    """
    tree = dependency_parser.parse(
        build(("མི", "n.count"), ("ཀྱིས", "case.agn"), ("ཁྱིམ", "n.count"), ("བཟོས", "v.past"))
    )
    assert relation_of(tree, "ཁྱིམ") is DependencyRelation.ARG2
    assert [n.text for n in tree.objects] == ["ཁྱིམ"]


def test_ergative_alignment_makes_the_absolutive_a_subject_when_no_agent_is_present(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """The same unmarked form is the *subject* of an intransitive clause.

    Labelling the absolutive as an object unconditionally would mislabel the
    subject of every intransitive sentence in the language.
    """
    tree = dependency_parser.parse(build(("ཁྱིམ", "n.count"), ("སོང", "v.past")))
    assert relation_of(tree, "ཁྱིམ") is DependencyRelation.ARG1
    assert tree.objects == ()


@pytest.mark.parametrize("case_tag", ["case.all", "case.term"])
def test_allative_and_terminative_mark_a_goal(
    dependency_parser: TibetanDependencyParser, case_tag: str
) -> None:
    tree = dependency_parser.parse(
        build(("ཁྱིམ", "n.count"), ("ལ", case_tag), ("སོང", "v.past"))
    )
    assert relation_of(tree, "ཁྱིམ") is DependencyRelation.ARG3


@pytest.mark.parametrize(
    "case_tag", ["case.loc", "case.abl", "case.ela", "case.ass", "case.comp"]
)
def test_remaining_cases_are_obliques(
    dependency_parser: TibetanDependencyParser, case_tag: str
) -> None:
    tree = dependency_parser.parse(
        build(("ཁྱིམ", "n.count"), ("ན", case_tag), ("སོང", "v.past"))
    )
    assert relation_of(tree, "ཁྱིམ") is DependencyRelation.OBL


def test_a_case_particle_attaches_to_the_nominal_it_marks(
    dependency_parser: TibetanDependencyParser,
) -> None:
    tree = dependency_parser.parse(
        build(("ཁྱིམ", "n.count"), ("ལ", "case.all"), ("སོང", "v.past"))
    )
    assert relation_of(tree, "ལ") is DependencyRelation.CASE
    assert head_text(tree, "ལ") == "ཁྱིམ"


# -- Nominal-internal structure -----------------------------------------------
def test_a_genitive_possessor_attaches_to_the_following_nominal(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """Tibetan places the possessor before the possessed."""
    tree = dependency_parser.parse(
        build(("མི", "n.count"), ("འི", "case.gen"), ("ཁྱིམ", "n.count"), ("མཐོང", "v.past"))
    )
    assert relation_of(tree, "མི") is DependencyRelation.NMOD_POSS
    assert head_text(tree, "མི") == "ཁྱིམ"


def test_genitive_attachment_can_be_redirected_to_the_clause_head() -> None:
    parser = TibetanDependencyParser(attach_genitive_to_following_nominal=False)
    tree = parser.parse(
        build(("མི", "n.count"), ("འི", "case.gen"), ("ཁྱིམ", "n.count"), ("མཐོང", "v.past"))
    )
    assert head_text(tree, "མི") == "མཐོང"


def test_a_trailing_genitive_with_nothing_to_modify_becomes_oblique(
    dependency_parser: TibetanDependencyParser,
) -> None:
    tree = dependency_parser.parse(
        build(("མི", "n.count"), ("འི", "case.gen"), ("སོང", "v.past"))
    )
    assert relation_of(tree, "མི") is DependencyRelation.OBL
    assert_is_a_tree(tree, 3)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("adj", DependencyRelation.AMOD),
        ("num.card", DependencyRelation.NUMMOD),
        ("d.dem", DependencyRelation.DET),
    ],
)
def test_modifiers_attach_to_the_preceding_head_noun(
    dependency_parser: TibetanDependencyParser, tag: str, expected: DependencyRelation
) -> None:
    """SETPARENT (ADJ|NUM|DET) TO (-1* Head_NOUN ...): Tibetan is noun-initial."""
    tree = dependency_parser.parse(
        build(("ཁྱིམ", "n.count"), ("ཆེན", tag), ("སོང", "v.past"))
    )
    assert relation_of(tree, "ཆེན") is expected
    assert head_text(tree, "ཆེན") == "ཁྱིམ"


def test_a_case_particle_after_a_modifier_still_marks_the_head_noun(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """The particle may be separated from its host by modifiers."""
    tree = dependency_parser.parse(
        build(
            ("མི", "n.count"),
            ("ཆེན", "adj"),
            ("ཀྱིས", "case.agn"),
            ("ཁྱིམ", "n.count"),
            ("བཟོས", "v.past"),
        )
    )
    assert relation_of(tree, "མི") is DependencyRelation.ARG1
    assert relation_of(tree, "ཁྱིམ") is DependencyRelation.ARG2


# -- Clause-level material ----------------------------------------------------
@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("cv.sem", DependencyRelation.MARK),
        ("neg", DependencyRelation.NEG),
        ("adv.temp", DependencyRelation.ADVMOD),
        ("punc", DependencyRelation.PUNCT),
    ],
)
def test_clause_level_material_attaches_to_the_root(
    dependency_parser: TibetanDependencyParser, tag: str, expected: DependencyRelation
) -> None:
    tree = dependency_parser.parse(build(("ཁྱིམ", "n.count"), ("ཡང", tag), ("སོང", "v.past")))
    assert relation_of(tree, "ཡང") is expected
    assert head_text(tree, "ཡང") == "སོང"


def test_a_subordinate_verb_is_marked(dependency_parser: TibetanDependencyParser) -> None:
    tree = dependency_parser.parse(
        build(("བཟོས", "v.past"), ("ནས", "cv.ela"), ("སོང", "v.past"))
    )
    assert tree.root is not None
    assert tree.root.text == "སོང"
    assert relation_of(tree, "བཟོས") is DependencyRelation.MARK


def test_an_unclassifiable_morpheme_is_recorded_as_unresolved(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """Recorded honestly rather than given a plausible-looking relation."""
    tree = dependency_parser.parse(build(("xyz", "dunno"), ("སོང", "v.past")))
    assert relation_of(tree, "xyz") is DependencyRelation.DEP
    assert tree.num_unresolved == 1


# -- Guarantees over the real corpus ------------------------------------------
def test_every_corpus_sentence_yields_one_well_formed_tree(
    dependency_parser: TibetanDependencyParser,
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    corpus_sentences: list[str],
) -> None:
    for sentence in corpus_sentences:
        tagged = pos_tagger.tag(morphological_analyzer.analyze(sentence))
        tree = dependency_parser.parse(tagged)
        assert_is_a_tree(tree, tagged.num_morphemes)


def test_spans_survive_parsing_unchanged(
    dependency_parser: TibetanDependencyParser,
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    corpus_sentences: list[str],
) -> None:
    """Stage 8 adds structure; it never re-segments or re-tags."""
    for sentence in corpus_sentences:
        tagged = pos_tagger.tag(morphological_analyzer.analyze(sentence))
        tree = dependency_parser.parse(tagged)

        assert tree.source == tagged.source
        for before, after in zip(tagged.morphemes, tree.nodes, strict=True):
            assert after.morpheme is before
            assert after.span == before.span
            assert after.tag == before.tag
        encoded = sentence.encode("utf-8")
        for node in tree.nodes:
            span = node.span
            assert sentence[span.char_start : span.char_end] == node.text
            assert encoded[span.byte_start : span.byte_end] == node.text.encode("utf-8")


def test_node_order_matches_surface_order(
    dependency_parser: TibetanDependencyParser,
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    corpus_sentences: list[str],
) -> None:
    for sentence in corpus_sentences[:25]:
        tree = dependency_parser.parse(
            pos_tagger.tag(morphological_analyzer.analyze(sentence))
        )
        for previous, current in itertools.pairwise(tree.nodes):
            assert previous.span.char_end <= current.span.char_start


def test_the_unresolved_rate_stays_low_on_real_text(
    dependency_parser: TibetanDependencyParser,
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    corpus_sentences: list[str],
) -> None:
    """The quality signal available without a treebank.

    No Tibetan dependency treebank exists in the project's data repository, so
    attachment accuracy cannot be measured. What can be measured is how often no
    rule applies at all: 3.37% on this fixture, 3.05% over the full 65,925-node
    corpus. The ceiling is set well above both so it catches a grammar
    regression rather than normal variation.
    """
    total = unresolved = 0
    for sentence in corpus_sentences:
        tree = dependency_parser.parse(
            pos_tagger.tag(morphological_analyzer.analyze(sentence))
        )
        total += tree.num_nodes
        unresolved += tree.num_unresolved

    assert total > 900, f"expected a substantial sample, got {total} nodes"
    assert unresolved / total <= 0.08, f"{unresolved}/{total}"


def test_parsing_is_deterministic(
    dependency_parser: TibetanDependencyParser,
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    corpus_sentences: list[str],
) -> None:
    tagged = pos_tagger.tag(morphological_analyzer.analyze(corpus_sentences[5]))
    assert dependency_parser.parse(tagged) == dependency_parser.parse(tagged)


# -- Adversarial input --------------------------------------------------------
@pytest.mark.parametrize(
    "pairs",
    [
        (("ལ", "case.all"),),  # a bare case particle with nothing to mark
        (("ལ", "case.all"), ("ན", "case.loc")),  # only particles
        (("།", "punc"),),  # only punctuation
        (("ཡང", "cv.sem"),),  # only a converb
        (("xyz", "dunno"),),  # only an unknown
    ],
)
def test_degenerate_sequences_still_produce_one_tree(
    dependency_parser: TibetanDependencyParser, pairs: tuple[tuple[str, str], ...]
) -> None:
    """Input with no nominal and no verb must still be a tree, not a forest."""
    tagged = build(*pairs)
    tree = dependency_parser.parse(tagged)
    assert_is_a_tree(tree, len(pairs))


def test_a_long_flat_sequence_of_nominals_is_handled(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """Every nominal attaching to one verb is the common Tibetan shape."""
    pairs = (*(("ཁྱིམ", "n.count") for _ in range(200)), ("སོང", "v.past"))
    tree = dependency_parser.parse(build(*pairs))
    assert_is_a_tree(tree, len(pairs))


def test_only_punctuation_and_particles_never_loses_a_morpheme(
    dependency_parser: TibetanDependencyParser,
) -> None:
    pairs = (("།", "punc"), ("ལ", "case.all"), ("ཡང", "cv.sem"), ("།", "punc"))
    tree = dependency_parser.parse(build(*pairs))
    assert tree.num_nodes == len(pairs)
    assert_is_a_tree(tree, len(pairs))


def test_every_pos_category_can_be_parsed(
    dependency_parser: TibetanDependencyParser,
) -> None:
    """No coarse class may crash the parser or vanish from the output."""
    representative = {
        PosCategory.NOUN: "n.count",
        PosCategory.VERB: "v.past",
        PosCategory.ADJECTIVE: "adj",
        PosCategory.PARTICLE: "case.all",
        PosCategory.PRONOUN: "p.pers",
        PosCategory.NUMERAL: "num.card",
        PosCategory.ADVERB: "adv.temp",
        PosCategory.DETERMINER: "d.dem",
        PosCategory.PUNCTUATION: "punc",
        PosCategory.INTERJECTION: "interj",
        PosCategory.UNKNOWN: "dunno",
    }
    for category, tag in representative.items():
        assert coarse_category(tag) is category, f"premise for {category}"
        tree = dependency_parser.parse(build(("ཁྱིམ", "n.count"), ("x", tag), ("སོང", "v.past")))
        assert_is_a_tree(tree, 3)
