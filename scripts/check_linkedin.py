"""Opt-in career-context regression check using actual DDGS responses."""

from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finder.models import Person, Platform
from finder.search_engine import DDGSSearchEngine
from finder.service import FinderService


def main():
    names = sys.argv[1:] or ["Ross Ferguson"]
    service = FinderService(DDGSSearchEngine(timeout=5, max_attempts=1))
    report = []
    target = Path(__file__).resolve().parents[1] / "validation" / "linkedin-search.json"
    for name in names:
        print(f"Searching {name} with profession Senior Creative Producer", flush=True)
        result = service.search_platform(Person(name, "Senior Creative Producer"), Platform.LINKEDIN)
        report.append({"person": name, "profession": "Senior Creative Producer", **asdict(result)})
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{result.status.value}; queries: {len(result.runs)}; errors: {len(result.errors)}", flush=True)
        for candidate in result.candidates:
            print(f"  {candidate.url} | {candidate.job_title or '(role unavailable)'} | {candidate.company or '(company unavailable)'}", flush=True)
    print(f"Report saved to {target}", flush=True)


if __name__ == "__main__":
    main()
