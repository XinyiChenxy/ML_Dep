import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from cloudlayer.factory import get_adapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=os.environ.get("ENDPOINT_RESOURCE"))
    args = parser.parse_args()
    if not args.endpoint:
        parser.error("--endpoint or ENDPOINT_RESOURCE in cloud.env is required")

    cfg = config.load()
    adapter = get_adapter(cfg)

    payloads = [
        {
            "temp_c": 78.4,
            "vibration_mm_s": 3.1,
            "pressure_kpa": 315.2,
            "hours_since_service": 4200.0,
            "load_pct": 68.0,
            "ambient_humidity": 55.0,
        },
        {
            "temp_c": 92.0,
            "vibration_mm_s": 4.2,
            "pressure_kpa": 330.0,
            "hours_since_service": 5000.0,
            "load_pct": 74.0,
            "ambient_humidity": 60.0,
        },
        {
            "temp_c": 65.0,
            "vibration_mm_s": 2.0,
            "pressure_kpa": 290.0,
            "hours_since_service": 1800.0,
            "load_pct": 52.0,
            "ambient_humidity": 48.0,
        },
    ]

    for i, payload in enumerate(payloads, 1):
        result = adapter.invoke(args.endpoint, payload)
        print(i, result)


if __name__ == "__main__":
    main()
