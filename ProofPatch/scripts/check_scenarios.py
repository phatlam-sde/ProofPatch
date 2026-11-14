"""Run all scenarios through the backend with fixture or Gemini tests."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from backend.main import analyze
from backend.scenarios import list_scenarios


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixture", "gemini"), default="fixture")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    failures = 0
    for attempt in range(1, args.repeat + 1):
        for scenario in list_scenarios():
            try:
                report = analyze(mode=args.mode, scenario=scenario["id"])
            except HTTPException as error:
                failures += 1
                print(f"ERROR {scenario['id']} run {attempt}: {error.detail}", flush=True)
                continue
            matches = report["matches_expected"]
            failures += int(not matches)
            label = "MATCH" if matches else "MISMATCH"
            print(f"{label} {scenario['id']} run {attempt}: "
                  f"{report['base']['status']} -> {report['head']['status']} "
                  f"({report['verdict']})", flush=True)
            if not matches:
                print(report["test_source"], flush=True)
                print(report["base"]["output"], report["head"]["output"], flush=True)
    print(f"Finished with {failures} mismatches or errors.")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
