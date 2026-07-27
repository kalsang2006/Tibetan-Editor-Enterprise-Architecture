"""Invariants of the Suggestion Fusion Engine's value objects.

These models are the contract between the Plugin Runtime and the add-in, so their
guarantees are asserted rather than assumed: a patch whose operations overlapped,
or an operation that ran past the end of the document, would corrupt the user's
text at the moment it was applied.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.fusion import (
    DocumentPatch,
    EditOperation,
    RejectedSuggestion,
    RejectionReason,
    Suggestion,
    SuggestionPriority,
    UnifiedSuggestions,
)
from tests.fusion.conftest import DOCUMENT, make_suggestion, span

P = SuggestionPriority


# -- SuggestionPriority --------------------------------------------------------
def test_the_four_priority_classes_are_exactly_figure_7s() -> None:
    assert [p.value for p in P] == ["critical", "high", "medium", "low"]


def test_priorities_rank_in_the_order_figure_7_lists_them() -> None:
    """ "Critical, High, Medium, Low priority ordering & classification"."""
    assert [p.rank for p in P] == [0, 1, 2, 3]
    assert sorted(P, key=lambda p: p.rank) == list(P)


# -- Suggestion ----------------------------------------------------------------
def test_a_suggestion_carries_what_a_plugin_emits() -> None:
    """Figure 7: "Outputs: Suggestions, Score, Priority"."""
    item = make_suggestion(source="grammar", score=0.75, priority=P.HIGH, message="why")
    assert item.source == "grammar"
    assert item.score == 0.75
    assert item.priority is P.HIGH
    assert item.message == "why"
    assert item.is_edit is True
    assert item.is_advisory is False


def test_a_suggestion_without_a_replacement_is_an_advisory() -> None:
    """Figure 7's output package includes plagiarism warnings, which edit nothing."""
    item = make_suggestion(replacement=None)
    assert item.is_advisory is True
    assert item.is_edit is False


def test_a_deletion_is_an_edit() -> None:
    assert make_suggestion(char_start=0, char_end=3, replacement="").is_edit is True


def test_an_insertion_is_an_edit() -> None:
    assert make_suggestion(char_start=2, char_end=2, replacement="ཀ").is_edit is True


def test_a_suggestion_must_name_its_plugin() -> None:
    """Figure 7's collector must "preserve metadata"; an unnamed source loses it."""
    with pytest.raises(ValidationError, match="must name the plugin"):
        make_suggestion(source="")


def test_an_edit_that_changes_nothing_is_rejected() -> None:
    """An empty replacement over an empty range is not an edit at all."""
    with pytest.raises(ValidationError, match="cover a range or insert text"):
        make_suggestion(char_start=2, char_end=2, replacement="")


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_a_score_outside_the_unit_interval_is_rejected(score: float) -> None:
    with pytest.raises(ValidationError):
        make_suggestion(score=score)


def test_a_suggestion_is_immutable() -> None:
    item = make_suggestion()
    with pytest.raises(ValidationError):
        item.score = 0.1  # type: ignore[misc]


def test_a_suggestion_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Suggestion(
            source="x",
            span=span(0, 1),
            score=1.0,
            priority=P.LOW,
            rule_id="R1",  # type: ignore[call-arg]
        )


# -- Conflict detection (FR-7) -------------------------------------------------
def test_overlapping_edits_conflict() -> None:
    assert make_suggestion(char_start=0, char_end=4).conflicts_with(
        make_suggestion(char_start=2, char_end=6)
    )


def test_edits_that_only_touch_do_not_conflict() -> None:
    """Adjacency is what the Merge Engine consolidates; it is not a collision."""
    assert not make_suggestion(char_start=0, char_end=3).conflicts_with(
        make_suggestion(char_start=3, char_end=6)
    )


def test_disjoint_edits_do_not_conflict() -> None:
    assert not make_suggestion(char_start=0, char_end=2).conflicts_with(
        make_suggestion(char_start=8, char_end=10)
    )


def test_an_advisory_never_conflicts() -> None:
    """A plagiarism warning over a paragraph does not compete with a fix inside it."""
    warning = make_suggestion(char_start=0, char_end=10, replacement=None)
    fix = make_suggestion(char_start=2, char_end=4)
    assert not warning.conflicts_with(fix)
    assert not fix.conflicts_with(warning)


def test_two_insertions_at_the_same_point_conflict() -> None:
    """Both would land at the same offset; only one can go first."""
    assert make_suggestion(char_start=4, char_end=4, replacement="ཀ").conflicts_with(
        make_suggestion(char_start=4, char_end=4, replacement="ཁ")
    )


def test_insertions_at_different_points_do_not_conflict() -> None:
    assert not make_suggestion(char_start=4, char_end=4, replacement="ཀ").conflicts_with(
        make_suggestion(char_start=6, char_end=6, replacement="ཁ")
    )


def test_an_insertion_inside_a_replaced_range_conflicts() -> None:
    """The range is about to be rewritten, so the insertion point vanishes."""
    insertion = make_suggestion(char_start=2, char_end=2, replacement="ཀ")
    replacement = make_suggestion(char_start=0, char_end=4)
    assert insertion.conflicts_with(replacement)
    assert replacement.conflicts_with(insertion)


def test_an_insertion_at_the_end_of_a_range_does_not_conflict() -> None:
    """The half-open convention: position 4 is outside ``[0, 4)``."""
    insertion = make_suggestion(char_start=4, char_end=4, replacement="ཀ")
    replacement = make_suggestion(char_start=0, char_end=4)
    assert not insertion.conflicts_with(replacement)
    assert not replacement.conflicts_with(insertion)


# -- RejectedSuggestion --------------------------------------------------------
@pytest.mark.parametrize("reason", [RejectionReason.SUPERSEDED, RejectionReason.DUPLICATE])
def test_losing_a_contest_must_name_the_winner(reason: RejectionReason) -> None:
    """A rejection the user might question has to say what beat it."""
    with pytest.raises(ValidationError, match="must name the suggestion that won"):
        RejectedSuggestion(suggestion=make_suggestion(), reason=reason)


@pytest.mark.parametrize("reason", [RejectionReason.INVALID_RANGE, RejectionReason.NO_OP])
def test_a_structural_rejection_cannot_name_a_winner(reason: RejectionReason) -> None:
    with pytest.raises(ValidationError, match="cannot name a winner"):
        RejectedSuggestion(
            suggestion=make_suggestion(),
            reason=reason,
            superseded_by=make_suggestion(source="other"),
        )


def test_a_rejection_keeps_the_suggestion_unchanged() -> None:
    item = make_suggestion(message="preserved")
    rejected = RejectedSuggestion(suggestion=item, reason=RejectionReason.NO_OP)
    assert rejected.suggestion is item
    assert rejected.suggestion.message == "preserved"


# -- EditOperation -------------------------------------------------------------
def test_an_operation_names_every_plugin_that_produced_it() -> None:
    operation = EditOperation(span=span(0, 3), replacement="ཀ", sources=("spell", "grammar"))
    assert operation.sources == ("spell", "grammar")


def test_an_operation_must_name_a_source() -> None:
    with pytest.raises(ValidationError, match="must name its source"):
        EditOperation(span=span(0, 3), replacement="ཀ", sources=())


def test_an_operation_must_change_something() -> None:
    with pytest.raises(ValidationError, match="must change something"):
        EditOperation(span=span(2, 2), replacement="", sources=("spell",))


# -- DocumentPatch -------------------------------------------------------------
def test_an_empty_patch_leaves_the_document_alone() -> None:
    patch = DocumentPatch(source=DOCUMENT)
    assert patch.is_empty is True
    assert len(patch) == patch.num_operations == 0
    assert patch.apply() == DOCUMENT


def test_a_patch_applies_its_operations_in_order() -> None:
    patch = DocumentPatch(
        source=DOCUMENT,
        operations=(
            EditOperation(span=span(0, 3), replacement="ཀ", sources=("a",)),
            EditOperation(span=span(8, 11), replacement="ཁ", sources=("b",)),
        ),
    )
    assert patch.apply() == "ཀ" + DOCUMENT[3:8] + "ཁ" + DOCUMENT[11:]
    assert patch.num_operations == 2
    assert patch.is_empty is False


def test_a_patch_can_delete_and_insert() -> None:
    patch = DocumentPatch(
        source=DOCUMENT,
        operations=(
            EditOperation(span=span(0, 3), replacement="", sources=("a",)),
            EditOperation(span=span(4, 4), replacement="ཀ", sources=("b",)),
        ),
    )
    assert patch.apply() == DOCUMENT[3:4] + "ཀ" + DOCUMENT[4:]


def test_a_patch_applies_to_its_own_document_only() -> None:
    """``apply`` takes no argument, so a patch cannot be aimed at the wrong text."""
    patch = DocumentPatch(source=DOCUMENT)
    assert patch.apply() == patch.source


def test_overlapping_operations_are_rejected() -> None:
    """Applying both would corrupt the range the second one addressed."""
    with pytest.raises(ValidationError, match="overlaps the one before it"):
        DocumentPatch(
            source=DOCUMENT,
            operations=(
                EditOperation(span=span(0, 5), replacement="ཀ", sources=("a",)),
                EditOperation(span=span(3, 8), replacement="ཁ", sources=("b",)),
            ),
        )


def test_an_operation_past_the_end_of_the_document_is_rejected() -> None:
    with pytest.raises(ValidationError, match="extends past the document"):
        DocumentPatch(
            source=DOCUMENT,
            operations=(EditOperation(span=span(50, 60), replacement="ཀ", sources=("a",)),),
        )


def test_adjacent_operations_are_allowed() -> None:
    """Touching end to start is not overlapping."""
    patch = DocumentPatch(
        source=DOCUMENT,
        operations=(
            EditOperation(span=span(0, 3), replacement="ཀ", sources=("a",)),
            EditOperation(span=span(3, 6), replacement="ཁ", sources=("b",)),
        ),
    )
    assert patch.apply() == "ཀཁ" + DOCUMENT[6:]


# -- UnifiedSuggestions --------------------------------------------------------
def unified() -> UnifiedSuggestions:
    """A package with one edit, one advisory and one rejection."""
    edit = make_suggestion(source="spell", priority=P.HIGH)
    advisory = make_suggestion(
        source="plagiarism", char_start=8, char_end=12, replacement=None, priority=P.LOW
    )
    return UnifiedSuggestions(
        suggestions=(edit, advisory),
        patch=DocumentPatch(
            source=DOCUMENT,
            operations=(EditOperation(span=span(0, 3), replacement="ཀཀཀ", sources=("spell",)),),
        ),
        rejected=(
            RejectedSuggestion(
                suggestion=make_suggestion(source="style"),
                reason=RejectionReason.SUPERSEDED,
                superseded_by=edit,
            ),
        ),
    )


def test_the_package_separates_edits_from_advisories() -> None:
    package = unified()
    assert [s.source for s in package.edits] == ["spell"]
    assert [s.source for s in package.advisories] == ["plagiarism"]
    assert len(package) == package.num_suggestions == 2
    assert package.num_rejected == 1
    assert package.is_empty is False


def test_the_package_can_be_filtered_the_way_a_task_pane_needs() -> None:
    package = unified()
    assert [s.source for s in package.of_priority(P.HIGH)] == ["spell"]
    assert package.of_priority(P.CRITICAL) == ()
    assert [s.source for s in package.of_source("plagiarism")] == ["plagiarism"]
    assert package.of_source("absent") == ()
    assert len(package.rejected_for(RejectionReason.SUPERSEDED)) == 1
    assert package.rejected_for(RejectionReason.NO_OP) == ()


def test_an_empty_package_is_valid() -> None:
    package = UnifiedSuggestions(patch=DocumentPatch(source=DOCUMENT))
    assert package.is_empty is True
    assert package.edits == package.advisories == ()
    assert package.num_suggestions == package.num_rejected == 0


def test_the_package_is_immutable() -> None:
    package = unified()
    with pytest.raises(ValidationError):
        package.suggestions = ()  # type: ignore[misc]


# -- Serialization -------------------------------------------------------------
def test_the_package_round_trips_through_json() -> None:
    """The add-in receives this across the IPC boundary."""
    package = unified()
    restored = UnifiedSuggestions.model_validate_json(package.model_dump_json())
    assert restored == package
    assert restored.patch.apply() == package.patch.apply()


def test_the_package_dumps_to_plain_data() -> None:
    dumped = unified().model_dump(mode="json")
    assert dumped["suggestions"][0]["priority"] == "high"
    assert dumped["rejected"][0]["reason"] == "superseded"
    assert dumped["patch"]["operations"][0]["sources"] == ["spell"]
