"""Executable architecture constraints for TEEA.

The decisions in ``docs/ARCHITECTURE_DECISIONS.md`` are only worth recording if
they cannot silently erode. This module turns the ones that are mechanically
checkable into tests, so a violation fails the build rather than waiting to be
noticed in review.

Each test names the document or ADR clause it enforces. These assertions are
about *structure*, not behaviour: they parse the source tree rather than
importing and exercising it, so they stay fast and cannot be satisfied by
accident.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
PACKAGE = SRC / "teea"


def iter_modules() -> Iterator[tuple[str, Path]]:
    """Yield ``(dotted_name, path)`` for every module in the package."""
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(SRC).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        yield ".".join(parts), path


def internal_imports(path: Path) -> set[str]:
    """Return the ``teea.*`` modules imported by the file at ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("teea"):
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.startswith("teea"))
    return found


MODULES = dict(iter_modules())
IMPORTS = {name: internal_imports(path) for name, path in MODULES.items()}


# -- Layering (Figure 1: one-directional flow) --------------------------------
def test_the_package_is_not_empty() -> None:
    """Guard every other test here against a silently empty module list."""
    assert len(MODULES) > 10


def test_core_never_imports_the_nlp_layer() -> None:
    """``core`` is the foundation; depending upward would invert the layering."""
    violations = {
        name: sorted(target for target in targets if target.startswith("teea.nlp"))
        for name, targets in IMPORTS.items()
        if name.startswith("teea.core")
    }
    assert not any(violations.values()), violations


def test_the_internal_import_graph_is_acyclic() -> None:
    """A cycle would make module import order significant and fragile."""
    colour: dict[str, int] = dict.fromkeys(IMPORTS, 0)
    cycles: list[list[str]] = []

    def visit(node: str, stack: list[str]) -> None:
        colour[node] = 1
        stack.append(node)
        for target in IMPORTS.get(node, ()):
            if target not in colour:
                continue
            if colour[target] == 1:
                cycles.append([*stack[stack.index(target) :], target])
            elif colour[target] == 0:
                visit(target, stack)
        stack.pop()
        colour[node] = 2

    for name in list(colour):
        if colour[name] == 0:
            visit(name, [])
    assert not cycles, cycles


def test_persistence_never_imports_the_language_layer() -> None:
    """Storage sits *beneath* the runtime layer in Figures 1 and 2.

    The Language Server reads from the Dictionary Repository; the repository
    knows nothing about language processing. Inverting that would make the
    storage layer un-substitutable, which is the whole reason its interface is
    stated separately.
    """
    violations = {
        name: sorted(target for target in targets if target.startswith("teea.nlp"))
        for name, targets in IMPORTS.items()
        if name.startswith("teea.persistence")
    }
    assert not any(violations.values()), violations


def test_stage_4_does_not_depend_on_stage_5() -> None:
    """Sentence segmentation precedes tokenization in Figure 5.

    ``teea.nlp.segmentation`` must depend only on ``teea.core``; importing the
    tokenization package would couple an earlier stage to a later one.
    """
    for name, targets in IMPORTS.items():
        if not name.startswith("teea.nlp.segmentation"):
            continue
        leaked = sorted(t for t in targets if t.startswith("teea.nlp.tokenization"))
        assert not leaked, f"{name} imports {leaked}"


#: The Figure 5 pipeline order, as packages. ``tokenization`` owns stages 2, 3
#: and 5; every other package owns exactly one stage.
STAGE_ORDER = (
    "teea.nlp.segmentation",  # stage 4
    "teea.nlp.tokenization",  # stages 2, 3, 5
    "teea.nlp.morphology",  # stage 6
    "teea.nlp.postagging",  # stage 7
    "teea.nlp.dependency",  # stage 8
    "teea.nlp.ner",  # stage 9
    "teea.nlp.terminology",  # stage 10
    "teea.nlp.semantics",  # stage 11
    "teea.nlp.snapshot",  # stage 12
)


@pytest.mark.parametrize("position", range(len(STAGE_ORDER)))
def test_no_stage_imports_a_later_stage(position: int) -> None:
    """Figures 1 and 5 both mandate one-directional flow.

    Each stage consumes its predecessors' output and nothing else. A stage
    reaching forward would make the pipeline order a fiction and would let a
    later stage's changes break an earlier one. This generalises the Stage 4 /
    Stage 5 rule above to the whole chain, so a new stage is covered the moment
    it is added to ``STAGE_ORDER``.
    """
    package = STAGE_ORDER[position]
    later = STAGE_ORDER[position + 1 :]
    for name, targets in IMPORTS.items():
        if not name.startswith(package):
            continue
        leaked = sorted(t for t in targets if t.startswith(later))
        assert not leaked, f"{name} imports {leaked}"


def test_the_fusion_engine_never_imports_the_language_layer() -> None:
    """Figure 3 routes plugin results into the Fusion Engine, not parsed text.

    The engine is a peer of the Language Server in Figure 1's Runtime Layer, and
    Figure 7 shows it consuming what the Feature Plugins Layer emits. Fusion is
    arithmetic over document ranges; making it depend on linguistics would tie a
    presentation-side component to the analysis chain and put the whole NLP layer
    on the critical path of every keystroke.
    """
    violations = {
        name: sorted(target for target in targets if target.startswith("teea.nlp"))
        for name, targets in IMPORTS.items()
        if name.startswith("teea.fusion")
    }
    assert not any(violations.values()), violations


def test_the_language_layer_never_imports_the_fusion_engine() -> None:
    """The dependency must not exist in either direction.

    Figure 5's pipeline ends at the snapshot; what consumes it is above the
    Language Server. A stage reaching into the Fusion Engine would invert that.
    """
    violations = {
        name: sorted(target for target in targets if target.startswith("teea.fusion"))
        for name, targets in IMPORTS.items()
        if name.startswith("teea.nlp") or name.startswith("teea.persistence")
    }
    assert not any(violations.values()), violations


#: Runtime Layer components, from Figure 1, in dependency order. Each may use the
#: ones before it; none may reach forward.
RUNTIME_LAYERS = (
    "teea.ai", "teea.fusion", "teea.ipc", "teea.nlp",
    "teea.plagiarism", "teea.plugins",
)


def test_the_ipc_layer_depends_only_on_core() -> None:
    """Figure 3 puts the Local IPC Layer at P3, in front of everything.

    It routes to handlers the daemon registers; it must not know what they call.
    An IPC layer that imported the Language Server would make the transport
    boundary depend on the analysis chain, and every future handler -- plugin,
    AI, fusion -- would inherit that coupling.
    """
    forbidden = ("teea.nlp", "teea.fusion", "teea.plugins", "teea.ai", "teea.persistence")
    violations = {
        name: sorted(t for t in targets if t.startswith(forbidden))
        for name, targets in IMPORTS.items()
        if name.startswith("teea.ipc")
    }
    assert not any(violations.values()), violations


def test_nothing_else_imports_the_ipc_layer() -> None:
    """Every component must be usable, and testable, without the boundary.

    The daemon composes IPC with the rest; the rest does not reach for IPC. This
    is what lets the whole analysis stack run in-process with no transport at
    all, as every other test module does.

    ``teea.transport`` is the one deliberate exception, and it is scoped by
    ``test_the_transport_layer_may_only_reuse_ipc_models`` to
    ``teea.ipc.models`` alone: a second HTTP boundary reusing ADR-020's wire
    vocabulary (``IpcRequest``, ``IpcResponse``, ``IpcFault``) is the
    specification's own "reuse existing shapes, do not build parallel
    messaging infrastructure" instruction, not a new coupling to the protocol
    engine those models happen to live beside.
    """
    violations = {
        name: sorted(t for t in targets if t.startswith("teea.ipc"))
        for name, targets in IMPORTS.items()
        if not name.startswith("teea.ipc")
        and name != "teea.daemon"
        and not name.startswith("teea.transport")
    }
    assert not any(violations.values()), violations


def test_the_transport_layer_may_only_reuse_ipc_models() -> None:
    """``teea.transport`` may share ADR-020's wire shapes, never its engine.

    The one exception ``test_nothing_else_imports_the_ipc_layer`` carves out is
    for ``teea.ipc.models`` alone. Importing ``teea.ipc.server``,
    ``teea.ipc.client``, ``teea.ipc.transport`` or ``teea.ipc.codec`` would
    couple a second transport boundary to the first one's protocol engine --
    exactly the coupling neither boundary needs, and the reason ``teea.ipc``
    holds its message models in their own module in the first place.
    """
    allowed = "teea.ipc.models"
    violations = {
        name: sorted(t for t in targets if t.startswith("teea.ipc") and t != allowed)
        for name, targets in IMPORTS.items()
        if name.startswith("teea.transport")
    }
    assert not any(violations.values()), violations


def test_the_transport_layer_never_imports_persistence() -> None:
    """``teea.transport`` bridges the add-in to the runtime layer, not storage.

    A bridge in this package calls straight into the collaborators a caller
    hands it -- the Language Server, the Plugin Runtime, the Fusion Engine, the
    AI Runtime -- never into the Dictionary Repository. Reaching into
    persistence directly would duplicate the daemon's own composition role
    instead of staying a thin adapter over handlers someone else built.
    """
    violations = {
        name: sorted(t for t in targets if t.startswith("teea.persistence"))
        for name, targets in IMPORTS.items()
        if name.startswith("teea.transport")
    }
    assert not any(violations.values()), violations


def test_nothing_imports_the_transport_layer() -> None:
    """Nothing the transport bridges to may depend on the bridge itself.

    Every collaborator a bridge serves must stay testable and constructible
    with no HTTP server ever started.  The one exception is ``teea.cli``,
    which is the daemon entry point that composes the transport for the
    ``serve`` subcommand.
    """
    violations = {
        name: sorted(t for t in targets if t.startswith("teea.transport"))
        for name, targets in IMPORTS.items()
        if not name.startswith("teea.transport") and name != "teea.cli"
    }
    assert not any(violations.values()), violations


def test_the_ipc_layer_ships_no_socket_transport() -> None:
    """ADR-020: the wire is behind the Transport protocol, not implemented here.

    ``socket`` is already banned package-wide as a network client; this states
    the same rule as an IPC-specific guarantee, so a future named-pipe adapter is
    added as a separate, explicitly-reviewed component rather than sliding in.
    """
    forbidden = {"socket", "socketserver", "asyncio", "grpc", "multiprocessing"}
    for name, path in MODULES.items():
        if not name.startswith("teea.ipc"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & forbidden), f"{name} imports a transport dependency"


def test_the_ai_runtime_depends_only_on_core() -> None:
    """Figure 6's AI Runtime is domain-agnostic infrastructure.

    A plugin holds a runtime and calls it; the dependency runs from the plugin to
    the runtime, never the reverse. If the AI Runtime imported the Language
    Server or the Fusion Engine it would couple an inference orchestrator to the
    thing that consumes it, and the "swappable adapter" of SRS 3.3 would leak the
    whole analysis layer into every model backend.
    """
    forbidden = ("teea.nlp", "teea.fusion", "teea.plugins", "teea.persistence")
    violations = {
        name: sorted(t for t in targets if t.startswith(forbidden))
        for name, targets in IMPORTS.items()
        if name.startswith("teea.ai")
    }
    assert not any(violations.values()), violations


def test_nothing_below_the_ai_runtime_imports_it() -> None:
    """The AI Runtime sits beside the Language Server, consumed from above.

    The Language Server, the Fusion Engine and persistence must all be usable,
    and testable, without an AI Runtime -- ADR-013 kept embeddings out of Stage
    11 precisely so the analysis chain owes nothing to a model.
    """
    below = ("teea.nlp", "teea.fusion", "teea.persistence", "teea.core")
    violations = {
        name: sorted(t for t in targets if t.startswith("teea.ai"))
        for name, targets in IMPORTS.items()
        if name.startswith(below)
    }
    assert not any(violations.values()), violations


def test_nothing_below_the_plugin_runtime_imports_it() -> None:
    """SRS 2.1 calls the product a microkernel-based plugin engine.

    The Plugin Runtime composes the Language Server's output with the Fusion
    Engine's input; both must remain usable, and testable, without it. A
    dependency the other way would make the microkernel a prerequisite for the
    components it exists to connect.
    """
    application = {
        "teea.cli",
        "teea.daemon",
        "teea.workflow",
        "teea.__main__",
        "teea.transport.analysis_server",
        "teea.transport.http_server",
        "teea.engine",
        "teea.service",
        "teea.service.app",
        "teea.service.endpoints",
        "teea.service.server",
    }
    violations = {
        name: sorted(target for target in targets if target.startswith("teea.plugins"))
        for name, targets in IMPORTS.items()
        if not name.startswith("teea.plugins") and name not in application
    }
    assert not any(violations.values()), violations


def test_no_feature_module_depends_on_another() -> None:
    """Figure 1's Runtime Layer components are peers, not a chain of features.

    ``teea.fusion`` merges ranges and ``teea.nlp`` analyses language; neither
    needs the other, and coupling them would put the whole NLP layer on the
    critical path of every suggestion merge.
    """
    for name, targets in IMPORTS.items():
        if name.startswith("teea.fusion"):
            assert not [t for t in targets if t.startswith("teea.nlp")], name
        if name.startswith("teea.nlp"):
            assert not [t for t in targets if t.startswith("teea.fusion")], name


def test_every_top_level_package_is_a_known_architectural_layer() -> None:
    """Guard the layering tests against a new package that escapes them all."""
    known = {
        "teea.core",
        "teea.corpus",
        "teea.persistence",
        "teea.plagiarism",
        "teea.transport",
        *RUNTIME_LAYERS,
        "teea.__main__",
        "teea.cli",
        "teea.daemon",
        "teea.workflow",
        "teea.engine",
        "teea.service",
    }
    packages = {".".join(name.split(".")[:2]) for name in MODULES if name.count(".") >= 1}
    assert packages - {"teea"} == known, packages


def test_every_pipeline_package_is_listed_in_the_stage_order() -> None:
    """Guard the test above against a new stage that quietly escapes it."""
    packages = {
        ".".join(name.split(".")[:3])
        for name in MODULES
        if name.startswith("teea.nlp.") and name.count(".") >= 3
    }
    assert packages == set(STAGE_ORDER), packages.symmetric_difference(STAGE_ORDER)


# -- ADR-001: Stage 03 has no module of its own -------------------------------
def test_no_separate_document_cleaning_package_exists() -> None:
    """ADR-001: Stage 03 is an activity of the normalization component."""
    assert not (PACKAGE / "nlp" / "cleaning").exists()
    assert not (PACKAGE / "nlp" / "document_cleaning").exists()


# -- ADR-002: offline-first ---------------------------------------------------
FORBIDDEN_NETWORK_MODULES = frozenset(
    {"requests", "httpx", "aiohttp", "urllib.request", "socket", "supabase"}
)


@pytest.mark.parametrize(("name", "path"), sorted(MODULES.items()))
def test_no_module_takes_a_network_dependency(name: str, path: Path) -> None:
    """ADR-002: SRS v5.1 is offline-first; the superseded v1.0 spec was not.

    ``transformers`` may download a model on first use, which is expected and
    cache-backed; what must never appear is a direct HTTP client or a cloud SDK.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not (imported & FORBIDDEN_NETWORK_MODULES), f"{name} imports a network client"


# -- ADR-004 consequence 4: shared character classes live in core.types -------
SHARED_CHARACTER_CLASSES = ("SHAD_CHARS", "TSHEG_CHARS", "LINE_BREAK_CHARS")


@pytest.mark.parametrize("constant", SHARED_CHARACTER_CLASSES)
def test_shared_character_classes_are_defined_exactly_once(constant: str) -> None:
    """No stage may redefine a shared character class locally.

    Stage 2 and Stage 4 must agree on what a line break is, and Stage 4 and
    Stage 5 must agree on what a shad is. A local copy is how they would drift.
    """
    definitions = [
        name
        for name, path in MODULES.items()
        if any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == constant for target in node.targets
            )
            for node in ast.parse(path.read_text(encoding="utf-8")).body
        )
    ]
    assert definitions == ["teea.core.types"], definitions


@pytest.mark.parametrize("constant", SHARED_CHARACTER_CLASSES)
def test_no_module_defines_a_private_copy_of_a_shared_class(constant: str) -> None:
    """The private-underscore variants were the original duplication."""
    private = f"_{constant}"
    offenders = [
        name for name, path in MODULES.items() if private in path.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders
