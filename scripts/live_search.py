"""Opt-in real network check. Not collected by the offline test suite."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finder.models import Person, Platform
from finder.public_evidence import PublicEvidenceVerifier
from finder.search_engine import DDGSSearchEngine
from finder.service import FinderService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*", default=["Emma Watson", "Elon Musk", "Christopher Nolan"])
    parser.add_argument("--output", default="validation/live-search.json")
    parser.add_argument("--platforms", nargs="+", choices=[p.name.lower() for p in Platform],
                        default=[p.name.lower() for p in Platform])
    parser.add_argument("--repeat", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--fresh", action="store_true", help="Disable reuse of earlier follower observations.")
    parser.add_argument("--no-reference-check", action="store_true", help="Skip reference-page verification for metric diagnostics.")
    args = parser.parse_args()
    service = FinderService(DDGSSearchEngine(), None if args.no_reference_check else PublicEvidenceVerifier())
    report = []
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    for iteration in range(1, args.repeat + 1):
        for name in args.names:
            for platform_name in dict.fromkeys(args.platforms):
                platform = Platform[platform_name.upper()]
                print(f"Round {iteration}: searching {name} / {platform.value}...", flush=True)
                if args.fresh:
                    service.follower_cache.clear()
                result = service.search_platform(Person(name), platform)
                report.append({"person": name, "iteration": iteration, **asdict(result)})
                target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                known = sum(candidate.follower_count is not None for candidate in result.candidates)
                print(f"  {len(result.candidates)} candidates, {known} with followers, {len(result.errors)} query errors", flush=True)
    print(f"Report saved to {target}", flush=True)


if __name__ == "__main__":
    main()
