"""Single entrypoint: ``python -m hotseat_core --mode classic|v2|v3``."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from typing import Any

from . import __version__
from .bridge import Bridge, serve
from .config import HotseatConfig, load_config
from .personas import MODES, get_persona_set, list_modes
from .providers import ProviderError, available_providers
from .runtime import HotseatRuntime
from .storage import SessionStore, StorageError
from .tuning import STYLE_PROFILES

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PROVIDER = 3
EXIT_INTERRUPTED = 130


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hotseat",
        description=(
            "The Hot Seat: put an idea, a decision, or a mess in front of a panel "
            "of AI personas and get a straight answer."
        ),
    )
    parser.add_argument("topic", nargs="*", help="The idea, decision, or situation.")
    parser.add_argument("-m", "--mode", default=None, help="classic, v2, v3, bmad, or arena (default: classic).")
    parser.add_argument("--variant", default=None, help="Mode variant, e.g. v3 panel|tribunal.")
    parser.add_argument("--provider", default=None, help="auto, ollama, demo, openrouter, ...")
    parser.add_argument("--model", default=None, help="Override the model for every persona.")
    parser.add_argument("--style", action="append", default=[], help="Style modifier (repeatable).")
    parser.add_argument("--statement", default="", help="v2: the volunteer's opening statement.")
    parser.add_argument("--constraint", action="append", default=[], help="Arena: constraint the rivals must respect (repeatable).")
    parser.add_argument("--system-directive", default="", help="Extra instruction for every persona.")
    parser.add_argument("--json-stream", action="store_true", help="Emit NDJSON events on stdout.")
    parser.add_argument("--no-save", action="store_true", help="Do not write the session to memory.")
    parser.add_argument("--list-modes", action="store_true", help="List modes and variants.")
    parser.add_argument("--list-personas", nargs="?", const="__all__", default=None, help="List personas (optionally for one mode).")
    parser.add_argument("--list-providers", action="store_true", help="List providers and key requirements.")
    parser.add_argument("--history", action="store_true", help="Print recent sessions.")
    parser.add_argument("--limit", type=int, default=10, help="History limit (default 10).")
    parser.add_argument("--repl", action="store_true", help="Interactive prompt loop.")
    parser.add_argument("--serve", action="store_true", help="Run the HTTP/SSE bridge.")
    parser.add_argument("--host", default=None, help="Bridge bind address (default 127.0.0.1).")
    parser.add_argument("--port", type=int, default=None, help="Bridge port (default 8765).")
    parser.add_argument("--token", default=None, help="Bridge bearer token (required off-loopback).")
    parser.add_argument("--allow-origin", action="append", default=[], help="Bridge CORS origin (repeatable).")
    parser.add_argument("--data-dir", default=None, help="Override the data directory.")
    parser.add_argument("--db", default=None, help="Override the SQLite path.")
    parser.add_argument("--version", action="version", version=f"hotseat {__version__}")
    return parser


def _config_from_args(args: argparse.Namespace) -> HotseatConfig:
    config = load_config()
    changes: dict[str, Any] = {}
    if args.data_dir:
        from pathlib import Path

        data_dir = Path(args.data_dir).expanduser()
        changes["data_dir"] = data_dir
        changes.setdefault("db_path", data_dir / "memory.db")
        changes.setdefault("session_log", data_dir / "sessions.log")
    if args.db:
        from pathlib import Path

        changes["db_path"] = Path(args.db).expanduser()
    return dataclasses.replace(config, **changes) if changes else config


def _flatten_styles(values: list[str]) -> tuple[str, ...]:
    styles: list[str] = []
    for value in values:
        styles.extend(part.strip() for part in value.split(",") if part.strip())
    return tuple(styles)


def _print_modes() -> None:
    for mode in list_modes():
        print(f"{mode['mode']:<8} {mode['label']}")
        print(f"         {mode['description']}")
        print(f"         variants: {', '.join(mode['variants'])}")
    print(f"\nStyles: {', '.join(STYLE_PROFILES)}")


def _print_personas(mode_filter: str) -> None:
    modes = list(MODES) if mode_filter in (None, "", "__all__") else [mode_filter]
    for mode in modes:
        if mode not in MODES:
            raise ValueError(f"Unknown mode '{mode}'. Choose: {', '.join(MODES)}.")
        for variant in MODES[mode]["variants"]:
            persona_set = get_persona_set(mode, variant)
            print(f"\n{mode}:{variant} — {persona_set.label}")
            for persona in persona_set.personas:
                print(
                    f"  {persona.key:<14} {persona.name:<28} "
                    f"model={persona.model} tokens={persona.max_tokens} temp={persona.temperature}"
                )
    print()


def _emit_factory(json_stream: bool):
    def emit(event: dict[str, Any]) -> None:
        if json_stream:
            sys.stdout.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()
            return
        kind = event.get("type")
        if kind == "session_start":
            print(f"\n{'=' * 62}")
            print(f"  THE HOT SEAT — {event.get('label')}")
            print(f"  {event.get('topic')}")
            print(f"{'=' * 62}")
        elif kind == "status":
            print(f"\n[{event.get('message')}]", file=sys.stderr)
        elif kind == "token_chunk":
            sys.stdout.write(str(event.get("text", "")))
            sys.stdout.flush()
        elif kind == "persona_turn":
            sys.stdout.write("\n\n")
            sys.stdout.flush()
        elif kind == "memory_saved":
            print(f"\n  saved → {event.get('path')} (#{event.get('memory_id')})", file=sys.stderr)
        elif kind == "error":
            print(f"\n  error: {event.get('message')}", file=sys.stderr)

    return emit


def _run_once(args: argparse.Namespace, config: HotseatConfig, topic: str) -> int:
    runtime = HotseatRuntime(config)
    store = runtime.store
    emit = _emit_factory(args.json_stream)
    options: dict[str, Any] = {}
    if args.statement:
        options["statement"] = args.statement
    if args.constraint:
        options["constraints"] = "; ".join(args.constraint)
    try:
        result = runtime.run_session(
            args.mode or "classic",
            topic,
            variant=args.variant,
            provider=args.provider,
            model=args.model,
            styles=_flatten_styles(args.style),
            system_directive=args.system_directive,
            options=options or None,
            emit=emit,
            save=not args.no_save,
        )
    except ProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_PROVIDER
    except (ValueError, StorageError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if not args.json_stream:
        if args.no_save:
            print("\n  (not saved)")
        elif result.memory_id is None:
            print(f"\n  memory: {store.db_path}")
        print()
    return EXIT_OK


def _repl(args: argparse.Namespace, config: HotseatConfig) -> int:
    print("The Hot Seat. Type an idea, 'history', or 'quit'.")
    while True:
        try:
            topic = input("\n  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return EXIT_OK
        if not topic:
            continue
        if topic.lower() in {"quit", "exit", "q"}:
            return EXIT_OK
        if topic.lower() == "history":
            print(SessionStore(config.db_path, config.session_log).history_text(limit=args.limit))
            continue
        status = _run_once(args, config, topic)
        if status not in (EXIT_OK, EXIT_PROVIDER):
            return status


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except BrokenPipeError:
        # A closed pipe (`| head`) is normal for a streaming CLI; exit quietly.
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        return EXIT_OK


def _main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        config = _config_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))

    if args.list_modes:
        _print_modes()
        return EXIT_OK
    if args.list_personas is not None:
        try:
            _print_personas(args.list_personas)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        return EXIT_OK
    if args.list_providers:
        print(json.dumps({"providers": available_providers()}, indent=2))
        return EXIT_OK
    if args.history:
        try:
            store = SessionStore(config.db_path, config.session_log)
            print(store.history_text(limit=args.limit))
        except StorageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        return EXIT_OK
    if args.serve:
        try:
            bridge = Bridge(config, token=args.token, allowed_origins=tuple(args.allow_origin))
            server = serve(
                bridge,
                host=args.host or config.bridge_host,
                port=args.port if args.port is not None else config.bridge_port,
            )
        except (ValueError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        host, port = server.server_address[:2]
        print(f"Hotseat bridge on http://{host}:{port} — contract: FRONTEND_CONTRACT.md", file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return EXIT_INTERRUPTED
        finally:
            server.server_close()
        return EXIT_OK

    topic = " ".join(args.topic).strip()
    if not topic and not sys.stdin.isatty():
        topic = sys.stdin.read().strip()
    if not topic:
        if args.repl or not args.topic:
            return _repl(args, config)
        parser.error("Provide a topic or use --repl.")
    return _run_once(args, config, topic)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
