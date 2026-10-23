"""Lab 5 Task 4 — prove the portability seam is real.

    python scripts/portability_swap_check.py --second-provider gcp

Exercises upload, download, and invoke against a SECOND provider's adapter. You are not
migrating the whole system; you are proving the seam exists.

If this fails while `make portability-audit` passes, you have found something worth
writing about: the leak was in configuration or in an assumption, not in an import.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--second-provider", required=True, choices=["aws", "azure", "gcp"])
    ap.add_argument("--blob-uri", default=os.environ.get("SECOND_BLOB_URI"))
    ap.add_argument("--region", default=os.environ.get("SECOND_REGION"))
    ap.add_argument("--project-id", default=os.environ.get("SECOND_PROJECT_ID"))
    ap.add_argument("--endpoint", default=os.environ.get("SECOND_ENDPOINT"))
    args = ap.parse_args()

    primary = config.load(strict=False)
    if primary.provider == args.second_provider:
        print("The second provider must differ from CLOUD_PROVIDER.")
        return 1

    print(f"primary   {primary.provider}")
    print(f"secondary {args.second_provider}\n")

    # Same Config object, different adapter. If your code needs more than this to switch,
    # say so in the write-up — that IS the finding.
    overrides = {"provider": args.second_provider}
    for field, value in (
        ("blob_uri", args.blob_uri),
        ("region", args.region),
        ("project_id", args.project_id),
    ):
        if value:
            overrides[field] = value
    swapped = config.Config(**{**primary.__dict__, **overrides})
    adapter = get_adapter(swapped)

    results: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.txt"
        probe.write_text("itcs355 portability probe\n")

        uploaded_uri = None
        downloaded = Path(tmp) / "back.txt"

        def invoke_second():
            if not args.endpoint:
                raise ValueError("set SECOND_ENDPOINT to the second provider endpoint")
            return adapter.invoke(args.endpoint, {"rows": []})

        calls = (
            ("upload", lambda: adapter.upload(str(probe), "portability/probe.txt")),
            ("download", lambda: adapter.download(str(uploaded_uri), str(downloaded))),
            ("invoke", invoke_second),
        )
        for name, call in calls:
            try:
                value = call()
                if name == "upload":
                    uploaded_uri = value
                if name == "download" and downloaded.read_bytes() != probe.read_bytes():
                    raise ValueError("downloaded bytes differ from uploaded probe")
                results[name] = "PASS"
            except NotImplementedError:
                results[name] = "NOT IMPLEMENTED"
            except Exception as exc:
                results[name] = f"FAIL — {type(exc).__name__}: {exc}"

    for name, outcome in results.items():
        print(f"  [{outcome.split(' —')[0]:<16}] {name}  {outcome.partition('— ')[2]}")

    print("\nWrite-up (Lab 5 Task 4), half a page:")
    print("  - which method was hardest to port, and why")
    print("  - one place the abstraction genuinely leaked and could not be hidden")
    print("  - what a full migration would cost in engineering days")
    print("  - was building this abstraction worth it? A well-argued 'no' scores full marks.")

    return 0 if all(v == "PASS" for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
