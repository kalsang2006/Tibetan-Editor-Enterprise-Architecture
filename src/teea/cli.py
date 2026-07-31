"""TEEA command-line interface.

Provides ``teea analyze``, ``teea workflow``, ``teea format``, ``teea config``,
and ``teea health`` subcommands.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from teea.core.config import load_settings
from teea.core.logging import configure_logging, get_logger
from teea.workflow import (
    analyze_text,
    full_workflow,
    load_document,
    save_json,
    save_text,
    snapshot_to_text,
)

_logger = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="teea",
        description="Tibetan Editor Enterprise Architecture (TEEA) — NLP platform CLI",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-json",
        action="store_true",
        help="Emit logs as newline-delimited JSON",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    _add_analyze_parser(subparsers)
    _add_workflow_parser(subparsers)
    _add_format_parser(subparsers)
    _add_config_parser(subparsers)
    _add_health_parser(subparsers)
    _add_serve_parser(subparsers)
    _add_build_dataset_parser(subparsers)
    _add_plagiarism_parser(subparsers)

    return parser


def _add_plagiarism_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("plagiarism", help="Plagiarism detection and corpus index management")
    plag_sub = p.add_subparsers(dest="plagiarism_subcommand", help="Plagiarism subcommands")

    build_p = plag_sub.add_parser("build-index", help="Build BoCorpus plagiarism fingerprint index")
    build_p.add_argument("--corpus-path", default="Data/Corpus/BoCorpus/bo_corpus.parquet", help="Path to BoCorpus Parquet file")
    build_p.add_argument("--db-path", default="Data/Processed/teea.db", help="Path to target SQLite database")
    build_p.add_argument("--force", action="store_true", help="Rebuild everything from scratch, ignoring existing indexed documents")
    build_p.add_argument("--max-chunk-chars", type=int, default=100000, help="Maximum characters per chunk")
    build_p.add_argument("--batch-size", type=int, default=50, help="Batch size for SQLite writes")


def _add_build_dataset_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("build-dataset", help="Download openpecha/BoCorpus and build vocabulary/n-gram dataset artifacts")
    p.add_argument("--corpus-dir", default="Data/Corpus/BoCorpus", help="Directory for BoCorpus raw files")
    p.add_argument("--output-dir", default="Data/Processed", help="Output directory for processed vocabulary/n-grams")
    p.add_argument("--synthetic-dir", default="Data/SyntheticErrors", help="Output directory for synthetic errors")
    p.add_argument("--synthetic-count", type=int, default=10000, help="Number of synthetic error records to generate")
    p.add_argument("--max-rows", type=int, default=None, help="Maximum corpus rows to process (for testing/quick runs)")
    p.add_argument("--skip-download", action="store_true", help="Skip downloading parquet and process existing local file")


def _add_serve_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("serve", help="Start the HTTP bridge daemon")
    p.add_argument(
        "--host", default="127.0.0.1",
        help="Bind address (must be loopback, default: 127.0.0.1)",
    )
    p.add_argument(
        "--port", type=int, default=50505,
        help="Bind port (default: 50505)",
    )


def _add_analyze_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("analyze", help="Analyze a Tibetan text file")
    p.add_argument("file", help="Path to the Tibetan text file")
    p.add_argument("-o", "--output", help="Output file path (JSON)")
    p.add_argument("--text", action="store_true", help="Also output human-readable text report")


def _add_workflow_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("workflow", help="Run full analysis, plugin, fusion workflow")
    p.add_argument("file", help="Path to the Tibetan text file")
    p.add_argument("-o", "--output", help="Output file path (JSON)")
    p.add_argument("--text", action="store_true", help="Also output text report")


def _add_format_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("format", help="Analyze and save formatted report")
    p.add_argument("file", help="Path to the Tibetan text file")
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path (defaults to input + .analysis)",
    )
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _add_config_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("config", help="Show current configuration")
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _add_health_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("health", help="Run diagnostics and health check")
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _cmd_analyze(args: argparse.Namespace) -> int:
    text = load_document(args.file)
    snapshot = analyze_text(text)
    result = {
        "source": args.file,
        "char_count": len(text),
        "sentence_count": len(snapshot.analyses),
        "snapshot": snapshot.model_dump(mode="json"),
    }
    if args.output:
        save_json(args.output, result)
        print(f"Analysis saved to {args.output}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.text:
        print("\n--- Text Report ---\n")
        print(snapshot_to_text(snapshot))
    return 0


def _cmd_workflow(args: argparse.Namespace) -> int:
    result = full_workflow(
        args.file,
        output_json=args.output,
        output_text=args.text,
    )
    if not args.output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _cmd_format(args: argparse.Namespace) -> int:
    text = load_document(args.file)
    snapshot = analyze_text(text)
    output_path = args.output or (args.file + ".analysis")
    if args.json:
        data = {"source": args.file, "snapshot": snapshot.model_dump(mode="json")}
        save_json(output_path, data)
    else:
        report = snapshot_to_text(snapshot)
        save_text(output_path, report)
    print(f"Analysis saved to {output_path}")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    settings = load_settings()
    data = settings.model_dump(mode="json")
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("TEEA Configuration:")
        for key, value in data.items():
            print(f"  {key}: {value}")
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    from teea.daemon import create_daemon  # noqa: PLC0415

    daemon = create_daemon()
    diag = daemon.diagnose()
    if args.json:
        print(json.dumps(diag, indent=2, ensure_ascii=False))
    else:
        print("TEEA Health Check")
        print(f"  Version: {diag['version']}")
        print(f"  Plugins: {diag['plugins']['count']} registered")
        for name in diag['plugins']['names']:
            print(f"    - {name}")
        print(f"  AI Runtime: {'active' if diag['ai_runtime']['active'] else 'not configured'}")
        print(f"  IPC Server: {'serving' if diag['ipc']['serving'] else 'stopped'}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    """Start the TEEA Local FastAPI service on specified host and port."""
    from teea.service.server import run_service  # noqa: PLC0415

    print(f"Starting TEEA Local Service on http://{args.host}:{args.port}", flush=True)
    run_service(host=args.host, port=args.port)
    return 0


def _cmd_build_dataset(args: argparse.Namespace) -> int:
    """Download BoCorpus, process vocabulary/n-grams, and build synthetic dataset."""
    from teea.corpus.builder import BoCorpusPipeline

    print("Building Tibetan Dataset from openpecha/BoCorpus...", flush=True)
    pipeline = BoCorpusPipeline(
        corpus_dir=args.corpus_dir,
        processed_dir=args.output_dir,
        synthetic_dir=args.synthetic_dir,
    )
    result = pipeline.process(
        max_rows=args.max_rows,
        synthetic_count=args.synthetic_count,
        skip_download=args.skip_download,
    )

    print("\nDataset Artifacts Generated Successfully:")
    print(f"  Vocabulary: {result['vocab_path']}")
    print(f"  N-Grams:    {result['ngram_path']}")
    print(f"  Statistics: {result['stats_path']}")
    print(f"  Synthetic:  {result['synthetic_path']}")

    stats = result["stats"]
    print("\nCorpus Summary:")
    print(f"  Documents:       {stats['total_documents']}")
    print(f"  Characters:      {stats['total_characters']}")
    print(f"  Sentences:       {stats['total_sentences']}")
    print(f"  Total Syllables: {stats['total_syllables']}")
    print(f"  Unique Syllables:{stats['unique_syllables']}")
    print(f"  Type-Token Ratio:{stats['type_token_ratio']}")
    return 0


def _cmd_plagiarism(args: argparse.Namespace) -> int:
    sub = getattr(args, "plagiarism_subcommand", None)
    if sub != "build-index":
        print("Usage: teea plagiarism build-index [options]", file=sys.stderr)
        return 1

    from pathlib import Path  # noqa: PLC0415

    from teea.persistence import DatabaseManager, SqliteFingerprintRepository  # noqa: PLC0415
    from teea.plagiarism.corpus import BoCorpusLoader  # noqa: PLC0415
    from teea.plagiarism.index_builder import IndexBuilder  # noqa: PLC0415

    corpus_path = Path(args.corpus_path)
    if not corpus_path.exists():
        print(f"Error: Corpus Parquet file not found at '{corpus_path}'", file=sys.stderr)
        return 1

    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading BoCorpus from {corpus_path}...")
    loader = BoCorpusLoader(parquet_path=corpus_path, batch_size=args.batch_size)
    total_docs = loader.total_count()
    print(f"Indexing {total_docs:,} documents into {db_path}...")

    db = DatabaseManager(db_path)
    repo = SqliteFingerprintRepository(db)
    builder = IndexBuilder(loader=loader, repository=repo, batch_size=args.batch_size)

    def print_progress(current: int, total: int) -> None:
        if total > 0 and (current % 50 == 0 or current == total):
            pct = (current / total) * 100
            bar = "#" * int(pct // 2.5)
            print(f"\rIndexing... [{bar:<40}] {current}/{total} ({pct:.1f}%)", end="", flush=True)

    stats = builder.build(
        force=args.force,
        max_chunk_chars=args.max_chunk_chars,
        progress_callback=print_progress,
    )

    print("\nDone.")
    print(f"Indexed:              {stats.indexed_documents:,}")
    print(f"Skipped:              {stats.skipped_documents:,}")
    print(f"Failed:               {stats.failed_documents:,}")
    print(f"Fingerprints:         {stats.total_fingerprints:,}")
    print(f"Elapsed time:         {stats.elapsed_seconds:.2f}s")
    print(f"Average speed:        {stats.docs_per_second:.1f} docs/s")
    return 0


_COMMANDS: dict[str, object] = {
    "analyze": _cmd_analyze,
    "workflow": _cmd_workflow,
    "format": _cmd_format,
    "config": _cmd_config,
    "health": _cmd_health,
    "serve": _cmd_serve,
    "build-dataset": _cmd_build_dataset,
    "plagiarism": _cmd_plagiarism,
}


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the TEEA CLI.

    Args:
        argv: Command-line arguments. Defaults to sys.argv[1:].

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    configure_logging(level=args.log_level, json_output=args.log_json)

    handler = _COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(args)  # type: ignore[operator, no-any-return]
    except FileNotFoundError as exc:
        filename_str = f" — {exc.filename}" if exc.filename else ""
        print(f"Error: {exc}{filename_str}", file=sys.stderr)
        return 1
    except Exception as exc:
        from teea.core.errors import TEEAError  # noqa: PLC0415

        if isinstance(exc, TEEAError):
            print(f"Error: [{exc.code}] {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
