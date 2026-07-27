"""Unit, regression and edge-case tests for the Suggestion Fusion Engine.

Organised by Figure 7's seven stages, so a failure names the stage that broke.
Two properties are load-bearing and get their own sections: the engine must be
**order-independent**, because plugins report concurrently, and it must be
**total**, because NFR 5.3 forbids one misbehaving plugin from taking down the
rest.
"""

from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor

import pytest

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.fusion import (
    DEFAULT_PLUGIN_WEIGHT,
    PriorityRankedFusionEngine,
    RejectedSuggestion,
    RejectionReason,
    Suggestion,
    SuggestionFusionEngine,
    SuggestionPriority,
    UnifiedSuggestions,
)
from teea.fusion.engine import _canonical_key as canonical_key
from tests.fusion.conftest import DOCUMENT, make_suggestion

P = SuggestionPriority


def sources_of(package: UnifiedSuggestions) -> list[str]:
    """The surviving plugins, in rank order."""
    return [s.source for s in package.suggestions]


def reasons_of(package: UnifiedSuggestions) -> list[RejectionReason]:
    """Every rejection reason, in the order recorded."""
    return [r.reason for r in package.rejected]


# -- Contract and dependency injection ----------------------------------------
def test_satisfies_the_fusion_engine_protocol(
    engine: PriorityRankedFusionEngine,
) -> None:
    assert isinstance(engine, SuggestionFusionEngine)


def test_an_unweighted_plugin_is_trusted_normally(
    engine: PriorityRankedFusionEngine,
) -> None:
    assert engine.weight_of("anything") == DEFAULT_PLUGIN_WEIGHT


def test_plugin_weighting_scales_confidence() -> None:
    """Figure 7's Confidence Ranking: "Apply plugin weighting"."""
    weighted = PriorityRankedFusionEngine(plugin_weights={"style": 0.5})
    item = make_suggestion(source="style", score=0.8)
    assert weighted.weight_of("style") == 0.5
    assert weighted.confidence_of(item) == pytest.approx(0.4)


def test_confidence_is_clamped_to_the_unit_interval() -> None:
    """A weight above one must not produce a confidence above one."""
    weighted = PriorityRankedFusionEngine(plugin_weights={"spell": 5.0})
    assert weighted.confidence_of(make_suggestion(score=0.9)) == 1.0


def test_an_explicitly_empty_weighting_is_not_silently_replaced() -> None:
    """``is None``, not ``or``: an empty mapping is falsy.

    The same defect was found and fixed in Stages 07, 09 and 10.
    """
    assert PriorityRankedFusionEngine(plugin_weights={}).weight_of("spell") == 1.0


def test_the_weighting_is_copied_at_construction() -> None:
    """A caller mutating its own mapping afterwards must not change the engine."""
    weights = {"style": 0.5}
    configured = PriorityRankedFusionEngine(plugin_weights=weights)
    weights["style"] = 0.0
    assert configured.weight_of("style") == 0.5


def test_adjacent_merging_is_configurable() -> None:
    assert PriorityRankedFusionEngine().merge_adjacent is True
    assert PriorityRankedFusionEngine(merge_adjacent=False).merge_adjacent is False


# -- Totality (NFR 5.3) --------------------------------------------------------
def test_no_suggestions_fuse_to_an_empty_package(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(document, [])
    assert package.is_empty
    assert package.patch.is_empty
    assert package.patch.apply() == document


def test_an_empty_document_is_handled(engine: PriorityRankedFusionEngine) -> None:
    package = engine.fuse("", [make_suggestion()])
    assert package.is_empty
    assert reasons_of(package) == [RejectionReason.INVALID_RANGE]


def test_a_plugin_emitting_only_garbage_cannot_break_the_others(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """NFR 5.3: one faulty plugin must not take the rest down."""
    good = make_suggestion(source="spell", char_start=0, char_end=3)
    package = engine.fuse(
        document,
        [
            good,
            make_suggestion(source="broken", char_start=900, char_end=950),
            make_suggestion(source="broken", char_start=800, char_end=801),
        ],
    )
    assert sources_of(package) == ["spell"]
    assert reasons_of(package) == [RejectionReason.INVALID_RANGE] * 2


def test_fusing_accepts_any_iterable(engine: PriorityRankedFusionEngine, document: str) -> None:
    """Plugins report as a stream, so a generator must work as well as a list."""
    items = (
        make_suggestion(source=f"p{i}", char_start=i * 4, char_end=i * 4 + 2) for i in range(3)
    )
    assert engine.fuse(document, items).num_suggestions == 3


# -- 2. Suggestion Validator ---------------------------------------------------
def test_a_range_past_the_end_of_the_document_is_removed(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(document, [make_suggestion(char_start=15, char_end=40)])
    assert package.is_empty
    assert reasons_of(package) == [RejectionReason.INVALID_RANGE]
    assert package.rejected[0].superseded_by is None


def test_a_replacement_identical_to_the_text_is_removed(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """Asking the user to approve a change that is not one wastes their attention."""
    package = engine.fuse(
        document, [make_suggestion(char_start=0, char_end=3, replacement=document[0:3])]
    )
    assert package.is_empty
    assert reasons_of(package) == [RejectionReason.NO_OP]


def test_an_identical_suggestion_is_filtered(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """Two plugins proposing the same edit is one edit, not two."""
    item = make_suggestion(source="spell")
    package = engine.fuse(document, [item, item])
    assert package.num_suggestions == 1
    assert reasons_of(package) == [RejectionReason.DUPLICATE]
    assert package.rejected[0].superseded_by == package.suggestions[0]


def test_the_same_edit_at_a_different_score_is_still_a_duplicate(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """Score is metadata about one recommendation, not part of its identity."""
    package = engine.fuse(
        document,
        [make_suggestion(score=0.9), make_suggestion(score=0.2)],
    )
    assert package.num_suggestions == 1
    assert reasons_of(package) == [RejectionReason.DUPLICATE]


def test_the_same_edit_from_a_different_plugin_is_not_a_duplicate(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """They agree, which is information; conflict resolution decides between them."""
    package = engine.fuse(
        document, [make_suggestion(source="spell"), make_suggestion(source="grammar")]
    )
    assert package.num_suggestions == 1
    assert reasons_of(package) == [RejectionReason.SUPERSEDED]


def test_an_advisory_is_never_a_no_op(engine: PriorityRankedFusionEngine, document: str) -> None:
    """It proposes no replacement, so it cannot equal the text it covers."""
    package = engine.fuse(document, [make_suggestion(char_start=0, char_end=3, replacement=None)])
    assert package.num_suggestions == 1


# -- 3. Conflict Resolution Engine (FR-7) -------------------------------------
def test_the_higher_priority_edit_wins(engine: PriorityRankedFusionEngine, document: str) -> None:
    """The Priority Manager is applied last, so its classification dominates."""
    package = engine.fuse(
        document,
        [
            make_suggestion(source="spell", char_start=0, char_end=4, score=1.0, priority=P.LOW),
            make_suggestion(
                source="grammar", char_start=2, char_end=6, score=0.1, priority=P.CRITICAL
            ),
        ],
    )
    assert sources_of(package) == ["grammar"]
    winner = package.rejected[0].superseded_by
    assert winner is not None
    assert winner.source == "grammar"


def test_confidence_breaks_a_priority_tie(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(
        document,
        [
            make_suggestion(source="spell", char_start=0, char_end=4, score=0.4),
            make_suggestion(source="grammar", char_start=2, char_end=6, score=0.8),
        ],
    )
    assert sources_of(package) == ["grammar"]


def test_plugin_weighting_can_decide_a_conflict(document: str) -> None:
    """A distrusted plugin loses to a trusted one even at a higher raw score."""
    weighted = PriorityRankedFusionEngine(plugin_weights={"style": 0.2})
    package = weighted.fuse(
        document,
        [
            make_suggestion(source="style", char_start=0, char_end=4, score=1.0),
            make_suggestion(source="spell", char_start=2, char_end=6, score=0.5),
        ],
    )
    assert sources_of(package) == ["spell"]


def test_the_patch_never_contains_overlapping_operations(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """FR-7, stated as the property that matters at the moment of application."""
    package = engine.fuse(
        document,
        [
            make_suggestion(source=f"p{i}", char_start=i, char_end=i + 5, score=0.5)
            for i in range(8)
        ],
    )
    previous = 0
    for operation in package.patch.operations:
        assert operation.span.char_start >= previous
        previous = operation.span.char_end


def test_advisories_survive_alongside_the_edits_they_cover(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(
        document,
        [
            make_suggestion(
                source="plagiarism", char_start=0, char_end=12, replacement=None, priority=P.LOW
            ),
            make_suggestion(source="spell", char_start=2, char_end=5, priority=P.HIGH),
        ],
    )
    assert sorted(sources_of(package)) == ["plagiarism", "spell"]
    assert package.rejected == ()
    assert package.patch.num_operations == 1


def test_many_advisories_over_the_same_range_all_survive(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(
        document,
        [
            make_suggestion(source=f"p{i}", char_start=0, char_end=8, replacement=None)
            for i in range(4)
        ],
    )
    assert package.num_suggestions == 4
    assert package.patch.is_empty


# -- 4. Merge Engine -----------------------------------------------------------
def test_adjacent_edits_are_consolidated(engine: PriorityRankedFusionEngine, document: str) -> None:
    """Figure 7: "Combine adjacent edits · Consolidate recommendations"."""
    package = engine.fuse(
        document,
        [
            make_suggestion(source="spell", char_start=0, char_end=3, replacement="ཀ"),
            make_suggestion(source="grammar", char_start=3, char_end=6, replacement="ཁ"),
        ],
    )
    assert package.patch.num_operations == 1
    operation = package.patch.operations[0]
    assert operation.replacement == "ཀཁ"
    assert operation.sources == ("spell", "grammar")
    assert operation.span.char_start == 0
    assert operation.span.char_end == 6
    assert package.patch.apply() == "ཀཁ" + document[6:]


def test_consolidation_can_be_switched_off(document: str) -> None:
    """A task pane may want each suggestion separately acceptable."""
    separate = PriorityRankedFusionEngine(merge_adjacent=False)
    package = separate.fuse(
        document,
        [
            make_suggestion(source="spell", char_start=0, char_end=3, replacement="ཀ"),
            make_suggestion(source="grammar", char_start=3, char_end=6, replacement="ཁ"),
        ],
    )
    assert package.patch.num_operations == 2
    assert package.patch.apply() == "ཀཁ" + document[6:]


def test_non_adjacent_edits_stay_separate(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(
        document,
        [
            make_suggestion(source="spell", char_start=0, char_end=3),
            make_suggestion(source="grammar", char_start=8, char_end=11),
        ],
    )
    assert package.patch.num_operations == 2


def test_an_insertion_is_not_consolidated_into_its_neighbour(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """Merging an insertion would move it, changing where the user sees the change."""
    package = engine.fuse(
        document,
        [
            make_suggestion(source="spell", char_start=0, char_end=3, replacement="ཀ"),
            make_suggestion(source="auto", char_start=3, char_end=3, replacement="ཁ"),
        ],
    )
    assert package.patch.num_operations == 2
    assert package.patch.apply() == "ཀཁ" + document[3:]


def test_three_adjacent_edits_consolidate_into_one(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(
        document,
        [
            make_suggestion(source="a", char_start=0, char_end=2, replacement="ཀ"),
            make_suggestion(source="b", char_start=2, char_end=4, replacement="ཁ"),
            make_suggestion(source="c", char_start=4, char_end=6, replacement="ག"),
        ],
    )
    assert package.patch.num_operations == 1
    assert package.patch.operations[0].sources == ("a", "b", "c")
    assert package.patch.apply() == "ཀཁག" + document[6:]


def test_advisories_contribute_no_operation(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(document, [make_suggestion(char_start=0, char_end=8, replacement=None)])
    assert package.num_suggestions == 1
    assert package.patch.is_empty
    assert package.patch.apply() == document


# -- 5 + 6. Confidence Ranking and Priority Manager ---------------------------
def test_survivors_are_ranked_by_priority_then_confidence(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(
        document,
        [
            make_suggestion(source="low", char_start=0, char_end=2, priority=P.LOW, score=1.0),
            make_suggestion(
                source="medium", char_start=3, char_end=5, priority=P.MEDIUM, score=0.1
            ),
            make_suggestion(
                source="critical", char_start=6, char_end=8, priority=P.CRITICAL, score=0.1
            ),
            make_suggestion(source="high", char_start=9, char_end=11, priority=P.HIGH, score=0.1),
        ],
    )
    assert sources_of(package) == ["critical", "high", "medium", "low"]


def test_equal_priority_ranks_by_confidence_descending(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    package = engine.fuse(
        document,
        [
            make_suggestion(source="weak", char_start=0, char_end=2, score=0.2),
            make_suggestion(source="strong", char_start=3, char_end=5, score=0.9),
            make_suggestion(source="middling", char_start=6, char_end=8, score=0.5),
        ],
    )
    assert sources_of(package) == ["strong", "middling", "weak"]


def test_a_tie_is_broken_deterministically(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """Without a total order the task pane would differ between identical runs."""
    items = [
        make_suggestion(source="b", char_start=0, char_end=2, score=0.5),
        make_suggestion(source="a", char_start=3, char_end=5, score=0.5),
    ]
    assert sources_of(engine.fuse(document, items)) == ["b", "a"]
    assert sources_of(engine.fuse(document, list(reversed(items)))) == ["b", "a"]


def test_a_surviving_suggestion_is_returned_unchanged(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """Figure 7's collector must "preserve metadata"; ranking must not rewrite it."""
    item = make_suggestion(source="spell", score=0.37, message="keep me")
    package = engine.fuse(document, [item])
    assert package.suggestions[0] is item


# -- Order independence --------------------------------------------------------
def shuffled_corpus() -> list[Suggestion]:
    """A mixed batch exercising every stage at once."""
    return [
        make_suggestion(source="spell", char_start=0, char_end=3, priority=P.HIGH),
        make_suggestion(
            source="grammar", char_start=2, char_end=6, score=0.95, priority=P.CRITICAL
        ),
        make_suggestion(source="style", char_start=8, char_end=12, priority=P.MEDIUM),
        make_suggestion(source="spell", char_start=0, char_end=3, priority=P.HIGH),
        make_suggestion(
            source="lint", char_start=4, char_end=7, replacement=DOCUMENT[4:7], priority=P.LOW
        ),
        make_suggestion(source="broken", char_start=100, char_end=120, priority=P.LOW),
        make_suggestion(
            source="plagiarism", char_start=0, char_end=8, replacement=None, priority=P.LOW
        ),
        make_suggestion(source="auto", char_start=12, char_end=12, replacement="ཀ", priority=P.LOW),
    ]


def test_arrival_order_does_not_change_the_result(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """Plugins report concurrently, so the result must be a function of the set."""
    items = shuffled_corpus()
    expected = engine.fuse(document, items)
    generator = random.Random(20260722)
    for _ in range(200):
        shuffled = items[:]
        generator.shuffle(shuffled)
        assert engine.fuse(document, shuffled) == expected


def test_fusion_is_deterministic(engine: PriorityRankedFusionEngine, document: str) -> None:
    items = shuffled_corpus()
    assert engine.fuse(document, items) == engine.fuse(document, items)


def test_the_engine_holds_no_state_between_calls(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    engine.fuse(document, shuffled_corpus())
    assert engine.fuse(document, []).is_empty


def test_concurrent_fusion_matches_serial_fusion(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """The daemon fuses for many documents at once against one engine."""
    batches = [shuffled_corpus()[: n + 1] for n in range(8)] * 4
    serial = [engine.fuse(document, batch) for batch in batches]
    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent = list(pool.map(lambda b: engine.fuse(document, b), batches))
    assert concurrent == serial


# -- Conflict resolution: correctness and cost of the sorted-claims index ------
def reference_resolve(
    engine: PriorityRankedFusionEngine,
    accepted: list[Suggestion],
    rejected: list[RejectedSuggestion],
) -> tuple[Suggestion, ...]:
    """The obvious scan the sorted index replaced, kept as a test oracle.

    Readable, obviously correct, and quadratic in the number of survivors. The
    shipped resolver must agree with it on every input.
    """
    survivors: list[Suggestion] = []
    claimed: list[Suggestion] = []
    for item in sorted(accepted, key=engine._rank_key):
        if item.is_advisory:
            survivors.append(item)
            continue
        winner = next((h for h in claimed if h.conflicts_with(item)), None)
        if winner is not None:
            rejected.append(
                RejectedSuggestion(
                    suggestion=item,
                    reason=RejectionReason.SUPERSEDED,
                    superseded_by=winner,
                )
            )
            continue
        claimed.append(item)
        survivors.append(item)
    return tuple(sorted(survivors, key=canonical_key))


def random_batch(generator: random.Random, size: int) -> list[Suggestion]:
    """A batch mixing overlaps, insertions, advisories and duplicates."""
    items: list[Suggestion] = []
    for index in range(size):
        start = generator.randrange(0, len(DOCUMENT) - 5)
        end = start + generator.randrange(0, 4)
        items.append(
            make_suggestion(
                source=f"p{index % 4}",
                char_start=start,
                char_end=end,
                replacement="ཀ" if generator.random() < 0.8 else None,
                score=round(generator.random(), 3),
                priority=list(P)[generator.randrange(4)],
            )
        )
    return items


def test_the_sorted_claim_index_agrees_with_a_naive_scan(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """Equivalence is what pins this optimisation, not a timing assertion.

    Comparing every candidate against every claim is quadratic in the number of
    survivors -- 6,400 realistic suggestions took 11.3 seconds that way, against
    85 ms for the sorted index. Speed belongs in the engineering record; what a
    test can assert without becoming flaky is that the two agree.
    """
    generator = random.Random(20260722)
    for _ in range(300):
        batch = random_batch(generator, generator.randrange(0, 30))
        collected = engine._collect(batch)
        expected_rejected: list[RejectedSuggestion] = []
        actual_rejected: list[RejectedSuggestion] = []
        accepted = list(engine._validate(document, collected, []))

        expected = reference_resolve(engine, accepted, expected_rejected)
        actual = engine._resolve(accepted, actual_rejected)

        assert actual == expected
        assert actual_rejected == expected_rejected


def test_conflict_resolution_does_not_degrade_quadratically(
    engine: PriorityRankedFusionEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A work-based complexity guard, in place of a wall-clock assertion.

    Scattered, non-overlapping suggestions are the realistic case -- a spell
    checker flags separate words -- and they are also the worst case for a scan
    over claimed ranges, because every one of them survives to be scanned again.
    Counting comparisons rather than timing them keeps the guard deterministic,
    the discipline this project adopted after an earlier stage's wall-clock test
    proved flaky.
    """
    calls = 0
    original = Suggestion.conflicts_with

    def counting(self: Suggestion, other: Suggestion) -> bool:
        nonlocal calls
        calls += 1
        return original(self, other)

    monkeypatch.setattr(Suggestion, "conflicts_with", counting)

    text = "ཀ" * 4_000
    offsets = utf8_byte_offsets(text)
    batch = [
        Suggestion(
            source=f"p{index}",
            span=TextSpan(
                char_start=index * 4,
                char_end=index * 4 + 2,
                byte_start=offsets[index * 4],
                byte_end=offsets[index * 4 + 2],
            ),
            replacement="ཁ",
            score=0.5,
            priority=P.MEDIUM,
        )
        for index in range(900)
    ]

    package = engine.fuse(text, batch)
    assert package.num_suggestions == 900
    # Two neighbours are examined per candidate, so the bound is linear. A scan
    # would need roughly 900 * 900 / 2 = 405,000 comparisons.
    assert calls <= 4 * len(batch), calls


# -- End to end ----------------------------------------------------------------
def test_a_realistic_batch_fuses_into_an_applicable_patch(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """Every stage in one pass, checked by applying the result."""
    package = engine.fuse(document, shuffled_corpus())

    assert package.num_suggestions == 4
    # grammar is CRITICAL, style MEDIUM; plagiarism and auto are both LOW at equal
    # confidence, so the deterministic tie-break puts the earlier span first.
    assert sources_of(package) == ["grammar", "style", "plagiarism", "auto"]
    assert sorted(r.value for r in reasons_of(package)) == [
        "duplicate",
        "invalid_range",
        "no_op",
        "superseded",
    ]
    assert package.patch.apply() != document
    assert len(package.edits) == 3
    assert len(package.advisories) == 1


def test_a_patch_built_from_many_edits_still_applies(
    engine: PriorityRankedFusionEngine, document: str
) -> None:
    """The document must survive a full-width rewrite without corruption."""
    items = [
        make_suggestion(source=f"p{i}", char_start=i, char_end=i + 1, replacement="ཀ", score=0.5)
        for i in range(0, len(document), 2)
    ]
    package = engine.fuse(document, items)
    applied = package.patch.apply()
    assert len(applied) == len(document)
    assert applied.count("ཀ") >= len(items)
