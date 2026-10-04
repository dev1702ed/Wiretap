"""python -m dcp_openlineage --events FILE.jsonl [--db PATH] [--run-scope SCOPE]
                            (--out FILE.jsonl | --post URL)

Reads recorded DCP events (a FileEmitter JSONL file and/or the backend's
SQLite event log), translates them to OpenLineage, and writes them to a JSONL
file or POSTs them to a lineage API such as Marquez. Exits non-zero on any
failure: this is a batch tool, not the monitor-only capture path.

--run-scope is "trace-process" (the default: one run per process per trace) or
"process" (one run per process); see translate.py.
"""

import argparse
import json
import os
import sys

from dcp_openlineage.translate import DEFAULT_RUN_SCOPE, RUN_SCOPES, to_openlineage
from dcp_openlineage.transport import TransportError, post_events


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dcp_openlineage", description="Translate DCP events to OpenLineage."
    )
    parser.add_argument("--events", help="DCP events, one JSON object per line")
    parser.add_argument("--db", help="the DCP backend's SQLite event log (needs the backend)")
    parser.add_argument(
        "--run-scope",
        choices=RUN_SCOPES,
        default=DEFAULT_RUN_SCOPE,
        help="one run per process per trace (default) or one run per process",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--out", help="write OpenLineage events here, one per line")
    target.add_argument("--post", metavar="URL", help="POST each event to URL/api/v1/lineage")
    args = parser.parse_args(argv)
    if not args.events and not args.db:
        parser.error("give --events, --db, or both")

    try:
        events = []
        if args.events:
            events += read_jsonl(args.events)
        if args.db:
            events += read_store(args.db)
        ol_events = to_openlineage(events, run_scope=args.run_scope)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: could not read DCP events: {exc!r}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    runs = len({event["run"]["runId"] for event in ol_events})
    if args.out:
        with open(args.out, "w", encoding="utf-8") as out:
            out.writelines(json.dumps(event) + "\n" for event in ol_events)
        print(f"wrote {len(ol_events)} OpenLineage events ({runs} runs) to {args.out}")
        return 0
    try:
        sent = post_events(args.post, ol_events)
    except TransportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"posted {sent} OpenLineage events ({runs} runs) to {args.post}")
    return 0


def read_jsonl(path: str) -> list[dict]:
    events = []
    with open(path, encoding="utf-8") as lines:
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: not JSON ({exc})") from exc
            if not isinstance(event, dict):
                raise TypeError(f"{path}:{number}: not a JSON object")
            events.append(event)
    return events


def read_store(path: str) -> list[dict]:
    try:
        from app.store import EventStore
    except ImportError as exc:
        raise ImportError("--db needs the DCP backend installed: pip install -e ./backend") from exc
    if not os.path.isfile(path):  # EventStore would create an empty log
        raise FileNotFoundError(f"no DCP event log at {path}")
    store = EventStore(path)
    try:
        return store.replay()
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
