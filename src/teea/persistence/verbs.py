"""Verb lexicon, the fourth facet of Figure 2's Dictionary Repository.

Figure 2 describes the Dictionary Repository as a "Tibetan lexicon & **lemma
store**" and a "Morphological rules catalog". Stage 7 uses its surface/tag
statistics, Stage 9 its proper nouns and Stage 10 its terminology. Stage 11 needs
the part no earlier stage did: the **lemma** a verb form belongs to, and the
**argument structure** that verb is attested to take.

Where the data comes from
-------------------------
The project's authoritative data repository ships the digital edition of

    Hill, Nathan W. (2010) *A Lexicon of Tibetan Verb Stems as Reported by the
    Grammatical Tradition.* Munich: Bayerische Akademie der Wissenschaften.

as ``Data/tibetan-nlp-lexicon-of-tibetan-verb-stems-802ef02/``. Four of its files
are used, and the payload records which:

* ``verbs-with-lemmas.txt`` maps 75,624 inflected surface forms to their lemma,
  which is what turns a present, past, future or imperative stem into one
  predicate identity.
* ``lemmas.txt`` gives each lemma its **volition** and its **argument frame** --
  ``Erg-Abs``, ``Abs-Obl`` and so on -- as reported by the dictionary's
  ``<syntax>`` element.
* ``dictionary.xml`` carries ``<transitivity>``, which ``lemmas.txt`` does not
  emit and which roughly doubles the number of lemmas carrying usable argument
  information.
* ``cg3-lemmas.txt`` states the same entries as Constraint Grammar rules and is
  used as an independent cross-check when the payload is built.

This is the same publisher and the same repository directory whose Constraint
Grammars Stage 8 already derives its relation inventory from (ADR-009), so the
provenance chain for Tibetan argument structure is unchanged; Stage 11 reads the
lexical half of it rather than the syntactic half.

Nothing here is inferred. A frame this lexicon does not report is absent, not
guessed, and the consumer is expected to record that absence rather than fill it
in -- the same discipline Stage 6 applies to ambiguous affixes and Stage 8 to
unattachable morphemes.

Entries are stored pre-segmented into syllables, following
:mod:`teea.persistence.gazetteer` and :mod:`teea.persistence.terminology`,
because Stage 6 emits syllable-level morphemes and the consumer matches runs of
them.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from teea.core.errors import ConfigurationError

#: Location of the shipped verb lexicon, relative to this module.
DEFAULT_VERB_LEXICON_PATH: Final = Path(__file__).parent / "data" / "verb_frames.json"


@enum.unique
class ArgumentSlot(enum.Enum):
    """One argument position an attested verb frame licenses.

    The members are the case labels the source dictionary itself uses in its
    ``<syntax>`` element. They are deliberately *not* renamed to semantic role
    names here: this is the storage layer reporting what the lexicon says, and
    interpreting a case slot as a role is the language layer's job.
    """

    #: Ergative/agentive-marked argument. Its presence is what makes a Tibetan
    #: frame transitive.
    ERGATIVE = "erg"
    #: Absolutive argument -- unmarked, and the object of a transitive clause or
    #: the sole argument of an intransitive one.
    ABSOLUTIVE = "abs"
    #: Oblique argument, the *la don* of the grammatical tradition.
    OBLIQUE = "obl"
    #: Allative-marked argument.
    ALLATIVE = "all"
    #: Ablative-marked argument.
    ABLATIVE = "abl"
    #: Elative-marked argument.
    ELATIVE = "ela"
    #: Associative/comitative-marked argument.
    ASSOCIATIVE = "ass"
    #: Instrumental-marked argument.
    INSTRUMENTAL = "instr"


@enum.unique
class Transitivity(enum.Enum):
    """Whether a verb is attested as taking an agent distinct from its patient."""

    TRANSITIVE = "transitive"
    INTRANSITIVE = "intransitive"
    #: The lexicon reports both readings for the same lemma.
    BOTH = "both"
    #: The lexicon reports neither. Recorded rather than defaulted, so a consumer
    #: can tell "no evidence" apart from "evidence of intransitivity".
    UNKNOWN = "unknown"


@enum.unique
class Volition(enum.Enum):
    """Whether the subject is attested as acting deliberately.

    A grammatical category of Tibetan the source dictionary records explicitly.
    It is carried through because it is real, attested lexical information; it
    does not participate in argument-role assignment.
    """

    VOLUNTARY = "voluntary"
    INVOLUNTARY = "involuntary"
    #: The lexicon reports both readings for the same lemma.
    BOTH = "both"
    #: The lexicon reports neither.
    UNKNOWN = "unknown"


class VerbFrame(BaseModel):
    """What the lexicon reports about one verb lemma.

    Attributes:
        lemma: The dictionary headword, exactly as the lexicon writes it
            (with its trailing tsheg).
        frame: The argument frame verbatim, e.g. ``"Erg-Abs"``. Empty when the
            lexicon reports none. Kept as written rather than canonicalized, so
            the entry stays traceable to its source row.
        slots: The argument positions ``frame`` licenses, parsed once when the
            payload is built.
        transitivity: What the dictionary's ``<transitivity>`` element reports.
        volition: What the dictionary's ``<volition>`` element reports.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    lemma: str
    frame: str = ""
    slots: frozenset[ArgumentSlot] = frozenset()
    transitivity: Transitivity = Transitivity.UNKNOWN
    volition: Volition = Volition.UNKNOWN

    @property
    def has_agentive_slot(self) -> bool:
        """Whether the attested frame licenses an ergative argument."""
        return ArgumentSlot.ERGATIVE in self.slots

    @property
    def is_transitive(self) -> bool | None:
        """Whether this verb takes an agent distinct from its patient.

        Three-valued on purpose. ``None`` means the lexicon says nothing usable
        -- either it reports no argument information at all, or it reports both
        readings -- and a consumer must not treat that as a negative answer.

        The frame is preferred over the transitivity label because it is the more
        specific statement: a frame naming an ergative slot settles the question
        directly, whereas the label is a summary.

        Returns:
            ``True``, ``False``, or ``None`` when the lexicon does not decide.
        """
        if self.slots:
            return ArgumentSlot.ERGATIVE in self.slots
        if self.transitivity is Transitivity.TRANSITIVE:
            return True
        if self.transitivity is Transitivity.INTRANSITIVE:
            return False
        return None

    @property
    def is_informative(self) -> bool:
        """Whether this entry says anything about argument structure at all."""
        return bool(self.slots) or self.transitivity is not Transitivity.UNKNOWN


@runtime_checkable
class VerbLexiconRepository(Protocol):
    """Read-only lookup of attested Tibetan verb lemmas and argument frames.

    Implementations must be safe to share across threads for read-only use.
    """

    @property
    def max_length(self) -> int:
        """Longest surface form, in syllables, bounding a matcher's lookahead."""
        ...

    def lookup(self, syllables: Sequence[str]) -> tuple[VerbFrame, ...]:
        """Return every lemma this run of syllables can be a stem of.

        More than one result means the surface is genuinely ambiguous between
        distinct dictionary entries. The tuple is returned rather than a single
        best guess so the consumer can decide, and can record that a choice was
        impossible instead of silently making one.

        Args:
            syllables: A run of syllables, without tsheg separators.

        Returns:
            The matching frames in a stable order; empty when the run is not an
            attested verb form.
        """
        ...

    def __len__(self) -> int:
        """Number of distinct surface forms known to the lexicon."""
        ...


class InMemoryVerbLexicon:
    """A read-only verb lexicon held entirely in memory.

    Satisfies the :class:`VerbLexiconRepository` protocol. Immutable after
    construction and safe to share across threads.

    Args:
        path: Location of the JSON payload. Defaults to the lexicon shipped with
            the package.

    Raises:
        ConfigurationError: If the payload is missing, unreadable, or malformed.
            Failing here is deliberate, matching every other repository: a Stage
            11 that silently found no argument structure would look like a
            document with no predicates.
    """

    def __init__(self, path: Path | None = None) -> None:
        source = path or DEFAULT_VERB_LEXICON_PATH
        payload = self._load(source)

        self._provenance: Mapping[str, Any] = dict(payload.get("provenance", {}))
        frames = tuple(VerbFrame.model_validate(entry) for entry in payload["lemmas"])
        self._frames = frames

        surfaces: dict[tuple[str, ...], tuple[VerbFrame, ...]] = {}
        for entry in payload["surfaces"]:
            key = tuple(entry[0])
            if not key:
                continue
            surfaces[key] = tuple(frames[index] for index in entry[1])
        self._surfaces = surfaces
        self._max_length = max((len(key) for key in surfaces), default=0)

    @staticmethod
    def _load(source: Path) -> dict[str, Any]:
        """Read and structurally validate the payload."""
        # UnicodeDecodeError is a ValueError rather than an OSError, so a
        # truncated payload would otherwise escape untyped.
        try:
            raw = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigurationError(
                "Verb lexicon data could not be read.",
                context={"path": str(source)},
                cause=exc,
            ) from exc

        try:
            payload: Any = json.loads(raw)
        except ValueError as exc:
            raise ConfigurationError(
                "Verb lexicon data is not valid JSON.",
                context={"path": str(source)},
                cause=exc,
            ) from exc

        if not isinstance(payload, dict):
            raise ConfigurationError(
                "Verb lexicon data must be a JSON object.",
                context={"path": str(source), "actual_type": type(payload).__name__},
            )

        missing = {"lemmas", "surfaces"} - set(payload)
        if missing:
            raise ConfigurationError(
                "Verb lexicon data is missing required sections.",
                context={"path": str(source), "missing": sorted(missing)},
            )
        for section in ("lemmas", "surfaces"):
            if not isinstance(payload[section], list):
                raise ConfigurationError(
                    f"Verb lexicon {section} must be a list.",
                    context={"path": str(source)},
                )
        return payload

    @property
    def provenance(self) -> Mapping[str, Any]:
        """Which lexicon the entries came from, and on what basis."""
        return self._provenance

    @property
    def max_length(self) -> int:
        """Longest surface form, in syllables."""
        return self._max_length

    @property
    def num_lemmas(self) -> int:
        """Number of distinct dictionary entries."""
        return len(self._frames)

    @property
    def num_with_argument_structure(self) -> int:
        """Entries reporting a frame or a transitivity, the usable subset."""
        return sum(1 for frame in self._frames if frame.is_informative)

    def lookup(self, syllables: Sequence[str]) -> tuple[VerbFrame, ...]:
        """Return every lemma this run of syllables can be a stem of."""
        return self._surfaces.get(tuple(syllables), ())

    def __len__(self) -> int:
        """Number of distinct surface forms known to the lexicon."""
        return len(self._surfaces)


@lru_cache(maxsize=1)
def default_verb_lexicon() -> InMemoryVerbLexicon:
    """Return the process-wide shared verb lexicon, loading it once.

    Parsing the payload costs real time and every request needs the same
    read-only data, so it is loaded lazily and cached rather than rebuilt.
    """
    return InMemoryVerbLexicon()


__all__ = [
    "DEFAULT_VERB_LEXICON_PATH",
    "ArgumentSlot",
    "InMemoryVerbLexicon",
    "Transitivity",
    "VerbFrame",
    "VerbLexiconRepository",
    "Volition",
    "default_verb_lexicon",
]
