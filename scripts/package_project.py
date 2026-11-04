"""Create a colleague-ready ZIP containing only application runtime files."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    "app.py", "bootstrap.py", "requirements.txt", "run.bat", "run.command", "README.md",
    ".streamlit/config.toml",
)


def main():
    files = [ROOT / name for name in RUNTIME_FILES]
    files.extend(sorted(path for path in (ROOT / "finder").rglob("*.py") if "__pycache__" not in path.parts))
    for path in [*files, ROOT / "finder" / "__init__.py"]:
        if not path.is_file():
            raise FileNotFoundError(f"Required runtime file is missing: {path}")
    target = ROOT / "dist" / "Social-Media-Finder.zip"
    target.parent.mkdir(exist_ok=True)
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            entry = ZipInfo("Social Media Finder/" + relative)
            entry.create_system = 3
            entry.external_attr = (0o100755 if relative == "run.command" else 0o100644) << 16
            entry.compress_type = ZIP_DEFLATED
            content = path.read_bytes()
            if relative == "run.command":
                content = content.replace(b"\r\n", b"\n")
            archive.writestr(entry, content)
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert (archive.getinfo("Social Media Finder/run.command").external_attr >> 16) & 0o111
        assert b"\r\n" not in archive.read("Social Media Finder/run.command")
    print(f"Created {target} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
