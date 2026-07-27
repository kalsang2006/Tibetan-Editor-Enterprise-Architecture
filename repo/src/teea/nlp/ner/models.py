"""Immutable domain models produced by named entity recognition.

These are the value objects that cross the boundary out of Stage 9 of the
language processing pipeline. Figure 5 states the stage as *"Named Entity
Recognition · Person, Place, Org · Religious & Cultural entities"*.

Entities are untyped, deliberately
----------------------------------
Figure 5 names five entity types, but **no available data source distinguishes
them**: the annotated corpora tag every name simply ``n.prop``, and all 3,000
proper-noun entries in the classical lexicon are likewise untyped. Rather than
ship an ``EntityType`` enum whose members no code path can populate, this module
models what the evidence supports -- entity *spans* -- and leaves typing to a
future stage that has a typed gazetteer to work from. Adding a type is then an
additive field, not a redesign. See ADR-011.

An entity is a run of morphemes
-------------------------------
Tibetan names routinely span several syllables and may contain internal
grammatical particles: the corpus annotates ``འཛམ་བུ འི་ གླིང་`` as one name
across three tokens, the middle of which is a genitive. So an entity is modelled
as a contiguous run of Stage 6 morphemes, not as a single token, and carries the
:class:`~teea.core.types.TextSpan` covering the whole run.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teea.core.types import TextSpan
from teea.nlp.postagging import TaggedMorpheme


@enum.unique
class EntityEvidence(enum.Enum):
    """Why a run of morphemes was recognised as a name.

    Recorded because the two sources have different reliability, and a consumer
    that wants to act only on high-confidence names -- a citation assistant, say
    -- needs to tell them apart without re-deriving the analysis.
    """

    #: The exact surface run appears in the proper-noun gazetteer.
    GAZETTEER = "gazetteer"
    #: The part-of-speech tagger labelled the morphemes as proper nouns.
    TAGGER = "tagger"
    #: Both sources agree, which is the strongest signal available.
    BOTH = "both"


class NamedEntity(BaseModel):
    """A contiguous run of morphemes recognised as a name.

    Attributes:
        text: The surface text of the entity, exactly as it appears.
        span: Character/byte extent of ``text`` in the sentence.
        start_index: Index of the first morpheme of the run.
        end_index: Index one past the last morpheme of the run.
        evidence: What led to the recognition.
        morphemes: The morphemes the entity spans.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    span: TextSpan
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    evidence: EntityEvidence
    morphemes: tuple[TaggedMorpheme, ...]

    @model_validator(mode="after")
    def _validate_consistency(self) -> NamedEntity:
        if not self.text:
            raise ValueError("an entity must not be empty")
        if self.end_index <= self.start_index:
            raise ValueError("end_index must be greater than start_index")
        if len(self.morphemes) != self.end_index - self.start_index:
            raise ValueError(
                f"expected {self.end_index - self.start_index} morphemes, got {len(self.morphemes)}"
            )
        first, last = self.morphemes[0], self.morphemes[-1]
        if self.span.char_start != first.span.char_start:
            raise ValueError("span must start at the first morpheme")
        if self.span.char_end != last.span.char_end:
            raise ValueError("span must end at the last morpheme")
        return self

    @property
    def num_morphemes(self) -> int:
        """How many morphemes the entity spans."""
        return len(self.morphemes)

    @property
    def is_multi_morpheme(self) -> bool:
        """Whether the entity spans more than one morpheme."""
        return len(self.morphemes) > 1

    @property
    def syllables(self) -> tuple[str, ...]:
        """The surface of each morpheme the entity spans."""
        return tuple(m.text for m in self.morphemes)


class EntityAnnotation(BaseModel):
    """Every named entity found in one sentence.

    Attributes:
        source: The text that was analysed, exactly as supplied.
        entities: The entities found, in surface order, never overlapping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    entities: tuple[NamedEntity, ...] = ()

    @model_validator(mode="after")
    def _validate_consistency(self) -> EntityAnnotation:
        previous_end = -1
        for position, entity in enumerate(self.entities):
            if entity.start_index < previous_end:
                raise ValueError("entity spans must not overlap")
            if entity.span.char_end > len(self.source):
                raise ValueError(f"entity {position} span exceeds the source text")
            if self.source[entity.span.char_start : entity.span.char_end] != entity.text:
                raise ValueError(f"entity {position} span does not select its own text")
            previous_end = entity.end_index
        return self

    def __len__(self) -> int:
        """Number of entities."""
        return len(self.entities)

    @property
    def num_entities(self) -> int:
        """Number of entities."""
        return len(self.entities)

    @property
    def is_empty(self) -> bool:
        """Whether the sentence contains no recognised entity."""
        return not self.entities

    @property
    def texts(self) -> tuple[str, ...]:
        """The surface text of each entity, in order."""
        return tuple(entity.text for entity in self.entities)

    def of_evidence(self, evidence: EntityEvidence) -> tuple[NamedEntity, ...]:
        """Return the entities recognised on a particular basis."""
        return tuple(entity for entity in self.entities if entity.evidence is evidence)

    def entity_at_char(self, char_index: int) -> NamedEntity | None:
        """Return the entity whose span contains ``char_index``.

        The primitive the add-in needs to decide whether an offset the user
        clicked falls inside a name.

        Args:
            char_index: Character offset into :attr:`source`.

        Returns:
            The covering entity, or ``None``.
        """
        for entity in self.entities:
            if entity.span.char_start <= char_index < entity.span.char_end:
                return entity
        return None

    def covers_morpheme(self, index: int) -> bool:
        """Whether the morpheme at ``index`` lies inside a recognised entity."""
        return any(entity.start_index <= index < entity.end_index for entity in self.entities)


__all__ = ["EntityAnnotation", "EntityEvidence", "NamedEntity"]
