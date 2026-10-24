"""Inspect or atomically update a managed endpoint traffic split."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=os.environ.get("ENDPOINT_RESOURCE"))
    parser.add_argument(
        "--set",
        nargs="*",
        metavar="DEPLOYED_ID=PERCENT",
        help="Replace the split. Omit to inspect without modifying it.",
    )
    parser.add_argument("--label", default="traffic-state")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not args.endpoint:
        parser.error("--endpoint or ENDPOINT_RESOURCE is required")

    adapter = get_adapter(config.load())
    before = adapter.endpoint_traffic(args.endpoint)
    after = before
    if args.set is not None:
        split: dict[str, int] = {}
        for item in args.set:
            deployed_id, separator, percentage = item.partition("=")
            if not separator:
                parser.error(f"invalid split item {item!r}; expected ID=PERCENT")
            split[deployed_id] = int(percentage)
        after = adapter.set_endpoint_traffic(args.endpoint, split)

    report = {
        "label": args.label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.endpoint,
        "before": before,
        "after": after,
    }
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
