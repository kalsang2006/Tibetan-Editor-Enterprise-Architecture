"""TEEA command-line interface.

Provides ``teea analyze``, ``teea workflow``, ``teea format``, ``teea config``,
and ``teea health`` subcommands.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from typing import Any

from teea.core.config import load_settings
from teea.core.logging import configure_logging, get_logger
from teea.daemon import create_daemon
from teea.transport import serve_http
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

    return parser


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
    """Start the combined HTTP+SSE bridge, then wait for SIGINT/SIGTERM."""
    daemon = create_daemon()

    server = serve_http(
        builder=daemon.builder,
        plugins=daemon.plugins,
        fusion=daemon.fusion,
        host=args.host,
        port=args.port,
    )
    print(f"TEEA daemon listening on {server.base_url}", flush=True)

    shutdown_event = threading.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        print(f"\nReceived signal {signum}, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        daemon.stop()
        print("TEEA daemon stopped.")
    return 0


_COMMANDS: dict[str, object] = {
    "analyze": _cmd_analyze,
    "workflow": _cmd_workflow,
    "format": _cmd_format,
    "config": _cmd_config,
    "health": _cmd_health,
    "serve": _cmd_serve,
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
        print(f"Error: file not found — {exc.filename}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
