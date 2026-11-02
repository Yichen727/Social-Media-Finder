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
    args = parser.parse_args()
    service = FinderService(DDGSSearchEngine(timeout=5, max_attempts=1), PublicEvidenceVerifier())
    report = []
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        for platform in Platform:
            print(f"Searching {name} / {platform.value}…", flush=True)
            result = service.search_platform(Person(name), platform)
            report.append({"person": name, **asdict(result)})
            target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  {result.status.value}: {len(result.candidates)} candidate(s), {len(result.errors)} query error(s)", flush=True)
    print(f"Report saved to {target}", flush=True)


if __name__ == "__main__":
    main()
