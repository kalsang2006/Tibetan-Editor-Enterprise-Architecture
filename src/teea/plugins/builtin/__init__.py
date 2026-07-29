"""Feature plugins shipped with TEEA.

Each module in this package implements a :class:`~teea.plugins.interfaces.FeaturePlugin`
that the :class:`~teea.plugins.runtime.SupervisedPluginRuntime` loads on startup.
"""

from __future__ import annotations

from teea.plugins.builtin.correction import CorrectionProvider
from teea.plugins.builtin.diagnostics import DocumentDiagnosticsPlugin
from teea.plugins.builtin.grammar import GrammarCheckerPlugin
from teea.plugins.builtin.plagiarism import PlagiarismDetectorPlugin
from teea.plugins.builtin.spelling import SpellCheckerPlugin

__all__ = [
    "CorrectionProvider",
    "DocumentDiagnosticsPlugin",
    "GrammarCheckerPlugin",
    "PlagiarismDetectorPlugin",
    "SpellCheckerPlugin",
]
