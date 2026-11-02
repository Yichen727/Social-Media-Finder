"""Shared first-run installer and launcher. Only the project .venv is modified."""

import argparse
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".venv"
PYTHON = ENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command):
    subprocess.run([str(part) for part in command], cwd=ROOT, check=True)


def prepare() -> Path:
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required. Install it from https://www.python.org/downloads/.")
    if not PYTHON.exists():
        if ENV.exists():
            raise RuntimeError("The .venv folder is incomplete. Rename it to .venv-old and launch again.")
        print("Creating the project's private Python environment…", flush=True)
        venv.EnvBuilder(with_pip=True).create(ENV)
    requirements = ROOT / "requirements.txt"
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = ENV / ".requirements.sha256"
    # Check distributions and version constraints without importing heavy UI modules.
    probe = """
import importlib.metadata as m
from pathlib import Path
from packaging.requirements import Requirement
import sys
assert sys.version_info >= (3, 11)
for line in Path(sys.argv[1]).read_text().splitlines():
    if not line.strip() or line.lstrip().startswith('#'):
        continue
    req = Requirement(line)
    assert m.version(req.name) in req.specifier, req.name
"""
    check = subprocess.run([str(PYTHON), "-c", probe, str(requirements)], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    installed = check.returncode == 0
    unchanged = marker.exists() and marker.read_text().strip() == fingerprint
    if not installed:
        print("Installing required packages into .venv. The first launch needs internet access…", flush=True)
        run([PYTHON, "-m", "pip", "install", "--disable-pip-version-check", "-r", requirements])
        run([PYTHON, "-c", probe, requirements])
    else:
        print("Dependencies are ready.", flush=True)
    if not installed or not unchanged:
        marker.write_text(fingerprint, encoding="utf-8")
    return PYTHON


def launch(python: Path):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", 8501))
        except OSError:
            sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    print(f"Starting Social Media Finder at {url}\nKeep this window open. Press Ctrl+C to stop.", flush=True)
    process = subprocess.Popen([str(python), "-m", "streamlit", "run", str(ROOT / "app.py"),
                                "--server.address=127.0.0.1", f"--server.port={port}",
                                "--server.headless=true", "--browser.gatherUsageStats=false"], cwd=ROOT)
    try:
        # Bypass system proxies for the loopback readiness check only.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("The app stopped during startup. See the error above.")
            try:
                with opener.open(url + "/_stcore/health", timeout=1) as response:
                    ready = response.status == 200
                if ready:
                    webbrowser.open(url)
                    break
            except OSError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("The app did not become ready within 30 seconds.")
        if process.wait() != 0:
            raise RuntimeError("The app exited with an error. See the messages above.")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true", help="Install/check dependencies without starting the app.")
    options = parser.parse_args()
    try:
        python = prepare()
        if not options.prepare_only:
            launch(python)
    except KeyboardInterrupt:
        print("\nSocial Media Finder stopped.")
    except Exception as exc:
        print(f"\nCould not start Social Media Finder: {exc}\nCheck your internet connection and Python installation.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
