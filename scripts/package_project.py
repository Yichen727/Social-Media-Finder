"""Create a distributable ZIP without environments, caches, or search history."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [ROOT / name for name in (
        "app.py", "bootstrap.py", "requirements.txt", "run.bat", "run.command", "README.md",
        ".gitignore", ".streamlit/config.toml", "validation/REPORT.md",
    )]
    for folder in ("finder", "tests", "scripts"):
        files.extend(sorted((ROOT / folder).glob("*.py")))
    target = ROOT / "dist" / "Social-Media-Finder.zip"
    target.parent.mkdir(exist_ok=True)
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            entry = ZipInfo("Social Media Finder/" + relative)
            entry.create_system = 3
            entry.external_attr = (0o100755 if relative == "run.command" else 0o100644) << 16
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes())
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert (archive.getinfo("Social Media Finder/run.command").external_attr >> 16) & 0o111
    print(f"Created {target} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
