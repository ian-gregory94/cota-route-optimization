"""Command-line entry points.

    python -m cota_opt.cli download-gtfs [--refresh]
    python -m cota_opt.cli ingest-gtfs <path-to-zip> [--origin URL]
    python -m cota_opt.cli validate
    python -m cota_opt.cli baseline
    python -m cota_opt.cli report
    python -m cota_opt.cli rt-collect <vehicle_positions|trip_updates|alerts> <url>
    python -m cota_opt.cli sources
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .download import GTFS_SOURCE_KEY, download_gtfs, ingest_local_gtfs, unpack_gtfs
from .gtfs import load_feed, validate_feed
from .paths import data_processed, outputs_dir
from .registry import Registry, load_sources

log = logging.getLogger("cota_opt")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cota_opt")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("download-gtfs", help="fetch and register the official feed")
    p.add_argument("--refresh", action="store_true")

    p = sub.add_parser("ingest-gtfs", help="register an externally retrieved zip")
    p.add_argument("path")
    p.add_argument("--origin", default="manual retrieval")

    sub.add_parser("validate", help="parse and validate the registered feed")
    sub.add_parser("baseline", help="build all baseline tables")
    sub.add_parser("report", help="generate the baseline report")
    sub.add_parser("sources", help="show source registration status")

    p = sub.add_parser("rt-collect", help="one-shot GTFS-Realtime fetch")
    p.add_argument("feed", choices=["vehicle_positions", "trip_updates", "alerts"])
    p.add_argument("url")
    p.add_argument("--db", default=str(data_processed() / "realtime.sqlite"))

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    reg = Registry()

    if args.cmd == "download-gtfs":
        print(download_gtfs(reg, refresh=args.refresh))
    elif args.cmd == "ingest-gtfs":
        print(ingest_local_gtfs(Path(args.path), args.origin, reg))
    elif args.cmd == "validate":
        rep = validate_feed(load_feed(unpack_gtfs(reg)))
        print(json.dumps(rep.to_dict(), indent=2))
        return 1 if rep.errors else 0
    elif args.cmd == "baseline":
        from .baseline import build_baseline
        b = build_baseline(reg)
        print(json.dumps(b.system.to_dict(), indent=2, default=str))
    elif args.cmd == "report":
        from .baseline import build_baseline
        from .report import build_report
        paths = build_report(build_baseline(reg, write=False))
        print(paths["markdown"])
    elif args.cmd == "sources":
        for k, s in load_sources().items():
            rec = reg.get(k)
            mark = f"REGISTERED {rec.sha256[:12]}" if rec else s.status
            print(f"{k:34s} {mark:20s} {s.url}")
    elif args.cmd == "rt-collect":
        from .realtime import fetch_and_store
        print(fetch_and_store(args.feed, args.url, Path(args.db)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
