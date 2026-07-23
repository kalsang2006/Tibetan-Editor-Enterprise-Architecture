"""TEEA semantic analysis module (Language pipeline Stage 11).

Stage 11 turns the parsed, annotated sentence into the structure the rest of the
system reasons over. Figure 1 lists "Semantic Graph" as a Language Server
sub-module, Figure 2 gives the Language Server the responsibility "Semantic Graph
Construction", and the Level-1 Data Flow Diagram labels what the Language Server
hands the Plugin Runtime "Parsed Tokens / **Graph**". Figure 5 places it at stage
11 and states its three parts: *Context Graph · Meaning Representation · Intent
Analysis*.

Public API:

* :class:`SemanticAnalyzer` -- the abstraction downstream code depends on.
* :class:`TibetanSemanticAnalyzer` -- the lexicon-driven implementation.
* Domain models: :class:`SemanticGraph`, :class:`SemanticNode`,
  :class:`SemanticEdge`, :class:`SemanticRole`, :class:`RoleEvidence`,
  :class:`SemanticNodeKind`, :class:`SentenceIntent`, :class:`SentenceMood`,
  :class:`Polarity`.

The graph is **symbolic**, built deterministically from Stages 6 to 10. The
embedding-based semantics the architecture also describes -- Figure 6's "Semantic
Features" and "Similarity Scores", Figure 9's 768-dimensional Embedding Model,
Figure 7's AI-assisted "Semantic validation" -- belongs to the **AI Runtime**, a
different component that this repository does not implement. See ADR-013.

Typical usage, completing the analysis chain::

    from teea.nlp.semantics import SemanticRole, TibetanSemanticAnalyzer

    analyzer = TibetanSemanticAnalyzer()
    tree = parser.parse(tagger.tag(morphology.analyze(sentence.text)))
    graph = analyzer.analyze(
        tree,
        entities=recognizer.recognize(tree),
        terms=terminology.recognize(tree),
    )

    graph.predicates                     # the clause heads
    graph.predicates[0].lemma            # the dictionary headword, not the stem
    graph.arguments_of(0)                # who plays which role
    graph.of_role(SemanticRole.AGENT)    # the agents
    graph.intent.mood                    # asks, commands, or states
    graph.node_at_char(12)               # which concept covers an offset
"""

from __future__ import annotations

from teea.nlp.semantics.analyzer import TibetanSemanticAnalyzer
from teea.nlp.semantics.interfaces import SemanticAnalyzer
from teea.nlp.semantics.models import (
    Polarity,
    RoleEvidence,
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
    SemanticNodeKind,
    SemanticRole,
    SentenceIntent,
    SentenceMood,
)

__all__ = [
    "Polarity",
    "RoleEvidence",
    "SemanticAnalyzer",
    "SemanticEdge",
    "SemanticGraph",
    "SemanticNode",
    "SemanticNodeKind",
    "SemanticRole",
    "SentenceIntent",
    "SentenceMood",
    "TibetanSemanticAnalyzer",
]
