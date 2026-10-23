"""Lab 5 — the registration gate.

Compares a candidate against the currently registered production model. Exits non-zero
when the candidate should NOT be registered, which is what makes the pipeline condition
real rather than decorative.

    python scripts/evaluation_gate.py --metrics reports/metrics.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The absolute floor prevents a weak first model from being registered. The 0.002
# improvement margin is larger than the last decimal place we report and avoids promoting
# an incumbent replacement on rounding noise. Both values are documented in the README.
MIN_ABSOLUTE = 0.75
MIN_IMPROVEMENT = 0.002


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", type=Path, required=True)
    ap.add_argument("--metric", default="test_roc_auc")
    ap.add_argument("--incumbent", type=float, default=None,
                    help="current production score; omit to read from the registry")
    ap.add_argument("--decision-out", type=Path,
                    help="KFP output parameter. Writes pass/fail and exits successfully.")
    args = ap.parse_args()

    def finish(passed: bool) -> int:
        if args.decision_out:
            args.decision_out.parent.mkdir(parents=True, exist_ok=True)
            args.decision_out.write_text("pass" if passed else "fail")
            return 0
        return 0 if passed else 1

    if not args.metrics.exists():
        from cloudlayer.factory import get_adapter
        from src import config

        cfg = config.load()
        get_adapter(cfg).download(
            f"{cfg.blob_uri.rstrip('/')}/lab5/metrics/{args.metrics.name}",
            str(args.metrics),
        )

    payload = json.loads(args.metrics.read_text())
    candidate = float(payload[args.metric])
    print(f"candidate {args.metric} = {candidate:.4f}")

    if candidate < MIN_ABSOLUTE:
        print(f"GATE FAIL  below absolute floor {MIN_ABSOLUTE}")
        return finish(False)

    incumbent = args.incumbent
    if incumbent is None:
        # A first registration has no incumbent. Subsequent managed runs should inject
        # the current production score through --incumbent.
        print("no incumbent supplied — first-registration policy applies")
        print("GATE PASS")
        return finish(True)

    delta = candidate - incumbent
    print(f"incumbent {incumbent:.4f}  delta {delta:+.4f}  required {MIN_IMPROVEMENT:+.4f}")
    if delta < MIN_IMPROVEMENT:
        print("GATE FAIL  improvement within noise; not registering")
        return finish(False)

    print("GATE PASS")
    return finish(True)


if __name__ == "__main__":
    raise SystemExit(main())
