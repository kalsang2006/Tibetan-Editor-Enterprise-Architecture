"""The Plugin Runtime abstractions (interfaces) for TEEA.

SRS 2.1 describes the product as "a **microkernel-based plugin engine**", and
these two protocols are that microkernel's boundary: :class:`FeaturePlugin` is
what an extension implements, :class:`PluginRuntime` is what the daemon calls.

Two contracts, opposite directions
----------------------------------
:class:`FeaturePlugin` is a contract the platform *requires* of others; every
other protocol in this repository is a contract the platform *offers*. That
difference is why its documentation is written as instructions to a plugin
author rather than as a description of shipped behaviour, and why the runtime
verifies what a plugin returns instead of trusting it.

No concrete plugin is shipped
-----------------------------
Figure 5 names eight -- Spell Checker, Grammar Checker, Translator, Summarizer,
Citation Assistant, Plagiarism Detector, Autocomplete, Style Checker -- and each
is its own component with its own requirements. The runtime is the component
that executes them, and it is complete without any of them existing, in the same
way that the Fusion Engine is complete without them (ADR-017). See ADR-018.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from teea.fusion import Suggestion
from teea.nlp.snapshot import DocumentSnapshot
from teea.plugins.models import PluginResults


@runtime_checkable
class FeaturePlugin(Protocol):
    """A feature that examines a document and recommends changes.

    Implementations are supplied by the caller and are never constructed by the
    runtime. Figure 5 has every plugin read "the centralized immutable snapshot
    concurrently", so an implementation must be safe to call from a worker thread
    and must not retain or mutate anything it is given -- the snapshot is shared
    with every other plugin examining the same document.
    """

    @property
    def name(self) -> str:
        """Stable identifier for this plugin.

        It is the identity the Fusion Engine weights by (ADR-017) and the name a
        failure is reported under, so it must be non-empty and unique among the
        plugins registered together. The runtime reads it once, when the plugin
        is registered, and uses that value for the rest of the plugin's life.
        """
        ...

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        """Recommend changes to the document the snapshot describes.

        Every returned suggestion must carry this plugin's own :attr:`name` as
        its source. The runtime rejects the whole outcome otherwise, because
        attribution decides how far the Fusion Engine trusts a recommendation
        and borrowing another plugin's name would borrow its trust.

        Spans must address the document, not a sentence: the snapshot's analyses
        are sentence-relative, and
        :meth:`~teea.nlp.snapshot.SentenceAnalysis.document_span` converts.

        Raising is permitted. NFR 5.3 requires the runtime to capture a fault
        rather than let it reach the host, so an exception becomes a recorded
        :class:`~teea.plugins.models.PluginFailure` and the other plugins are
        unaffected. It is not, however, a way to report "nothing found" -- return
        an empty iterable for that.

        Args:
            snapshot: The immutable analysis of the whole document.

        Returns:
            The suggestions, in any order.
        """
        ...


@runtime_checkable
class PluginRuntime(Protocol):
    """Executes the registered feature plugins over one document.

    Figure 2 gives this component "Execute Features & Load Plugins · Sandbox
    Extension Management · Lifecycle & Request Dispatching"; Figure 9 gives it
    "Sandbox Execution · Feature Dispatcher".

    Implementations must be safe to share across threads for read-only use: the
    daemon dispatches for many documents against one runtime.
    """

    @property
    def plugins(self) -> tuple[str, ...]:
        """The registered plugin names, in dispatch order."""
        ...

    def dispatch(self, snapshot: DocumentSnapshot) -> PluginResults:
        """Run every registered plugin over ``snapshot``.

        Implementations must be **total**: no plugin, however it misbehaves, may
        raise out of this call. That is NFR 5.3's requirement, and it is the
        whole reason the runtime exists as a component rather than as a loop in
        the daemon.

        Implementations must return **one outcome per registered plugin**,
        successful or not. Returning only what succeeded would leave the add-in
        unable to distinguish a plugin that found nothing from one that crashed.

        Results must be **deterministic**: the same snapshot and the same plugins
        must produce the same results whatever order the plugins finish in.

        Args:
            snapshot: The immutable analysis of the whole document.

        Returns:
            One outcome per plugin, ordered by plugin name.
        """
        ...


__all__ = ["FeaturePlugin", "PluginRuntime"]
