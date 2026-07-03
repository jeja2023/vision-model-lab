from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Vision Model Lab locally.")
    parser.add_argument("--host", "--hostname", "-HostName", dest="host", default="127.0.0.1")
    parser.add_argument("--port", "-Port", dest="port", type=int, default=8080)
    parser.add_argument("--skip-install", "-SkipInstall", dest="skip_install", action="store_true")
    parser.add_argument(
        "--skip-frontend-build",
        "-SkipFrontendBuild",
        dest="skip_frontend_build",
        action="store_true",
    )
    return parser.parse_args(argv)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if name:
            os.environ[name] = value


def venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def run(command: list[str | Path], *, cwd: Path) -> None:
    printable = " ".join(str(part) for part in command)
    print(f"[run] {printable}", flush=True)
    subprocess.run([str(part) for part in command], cwd=str(cwd), check=True)


def command_for_executable(executable: str, *args: str) -> list[str]:
    suffix = Path(executable).suffix.lower()
    if os.name == "nt" and suffix in {".bat", ".cmd"}:
        return ["cmd", "/c", executable, *args]
    return [executable, *args]


def ensure_virtualenv(root: Path) -> Path:
    python_path = venv_python(root)
    if python_path.exists():
        return python_path

    print("[setup] Creating .venv...", flush=True)
    run([sys.executable, "-m", "venv", ".venv"], cwd=root)
    if not python_path.exists():
        raise RuntimeError(f"Virtual environment Python was not created at {python_path}")
    return python_path


def ensure_frontend(root: Path, skip_build: bool) -> None:
    if skip_build:
        return

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        print("[warn] npm not found; skipping frontend build. Existing frontend/dist will be used if present.")
        return

    frontend = root / "frontend"
    if not frontend.exists():
        print("[warn] frontend directory not found; skipping frontend build.")
        return

    if not (frontend / "node_modules").exists():
        print("[setup] Installing frontend dependencies...", flush=True)
        run(command_for_executable(npm, "ci"), cwd=frontend)

    print("[setup] Building frontend...", flush=True)
    run(command_for_executable(npm, "run", "build"), cwd=frontend)


def configure_environment(root: Path) -> None:
    load_dotenv(root / ".env")

    if not os.environ.get("VMLAB_WORKSPACE") or os.environ["VMLAB_WORKSPACE"] == ".":
        os.environ["VMLAB_WORKSPACE"] = str(root)
    os.environ.setdefault("VMLAB_METADATA_DB", "artifacts/vision_model_lab.sqlite3")

    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "object-store").mkdir(parents=True, exist_ok=True)


def start_api(root: Path, python_path: Path, host: str, port: int) -> int:
    print("", flush=True)
    print("Vision Model Lab is starting...", flush=True)
    print(f"Management UI: http://{host}:{port}/", flush=True)
    print(f"OpenAPI:       http://{host}:{port}/docs", flush=True)
    print(f"Health:        http://{host}:{port}/health", flush=True)
    print("", flush=True)

    command = [
        str(python_path),
        "scripts/serve_api.py",
        "--host",
        host,
        "--port",
        str(port),
        "--metadata-db",
        os.environ["VMLAB_METADATA_DB"],
    ]
    try:
        return subprocess.call(command, cwd=str(root))
    except KeyboardInterrupt:
        return 130


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parent
    os.chdir(root)

    configure_environment(root)
    python_path = ensure_virtualenv(root)

    if not args.skip_install:
        print("[setup] Installing Python dependencies...", flush=True)
        run([python_path, "-m", "pip", "install", "-e", ".[dev]"], cwd=root)

    ensure_frontend(root, args.skip_frontend_build)

    print("[setup] Initializing metadata storage...", flush=True)
    run(
        [
            python_path,
            "-m",
            "vision_model_lab.cli",
            "storage",
            "migrate",
            "--uri",
            os.environ["VMLAB_METADATA_DB"],
        ],
        cwd=root,
    )

    return start_api(root, python_path, args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
