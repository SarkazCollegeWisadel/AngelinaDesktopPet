from __future__ import annotations

import argparse
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


DEFAULT_ARCHIVE = "https://github.com/SarkazCollegeWisadel/AngelinaDesktopPet/archive/refs/heads/main.zip"
PROJECT_ENTRIES = (
    ".gitignore",
    "AngelinaDesktopPet.spec",
    "README.md",
    "angelina_pet",
    "assets",
    "build.ps1",
    "main.py",
    "pyproject.toml",
    "requirements.txt",
    "run.ps1",
    "tests",
    "tools",
)
IGNORED_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    "release",
    "settings.ini",
    "tmp",
}


def ensure_empty_output(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def ignored(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORED_NAMES or name.endswith((".pyc", ".log"))}


def copy_project(source: Path, output: Path, clean_assets: bool = False) -> None:
    missing = [entry for entry in PROJECT_ENTRIES if not (source / entry).exists()]
    if missing:
        raise SystemExit(f"Template is missing required entries: {', '.join(missing)}")
    for entry in PROJECT_ENTRIES:
        if clean_assets and entry == "assets":
            continue
        src = source / entry
        dst = output / entry
        if src.is_dir():
            shutil.copytree(src, dst, ignore=ignored)
        else:
            shutil.copy2(src, dst)


def download_template() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory(prefix="desktop-pet-template-")
    root = Path(temporary.name)
    archive = root / "template.zip"
    print(f"Downloading public template: {DEFAULT_ARCHIVE}")
    urllib.request.urlretrieve(DEFAULT_ARCHIVE, archive)
    with zipfile.ZipFile(archive) as opened:
        opened.extractall(root / "extracted")
    candidates = [path for path in (root / "extracted").iterdir() if path.is_dir()]
    if len(candidates) != 1:
        temporary.cleanup()
        raise SystemExit("Downloaded archive did not contain exactly one project root")
    return temporary, candidates[0]


def clean_character_assets(output: Path) -> None:
    source = output / "assets" / "source"
    processed = output / "assets" / "processed"
    if source.exists():
        shutil.rmtree(source)
    if processed.exists():
        shutil.rmtree(processed)
    for path in (source / "PNG", source / "GIF", source / "generated"):
        path.mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a clean Windows desktop pet project from AngelinaDesktopPet.")
    parser.add_argument("--output", required=True, type=Path, help="New or empty destination directory")
    parser.add_argument("--source", type=Path, help="Optional local AngelinaDesktopPet checkout")
    parser.add_argument("--clean-assets", action="store_true", help="Remove demo character assets and create empty source folders")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output.expanduser().resolve()
    ensure_empty_output(output)

    temporary: tempfile.TemporaryDirectory[str] | None = None
    try:
        if args.source:
            source = args.source.expanduser().resolve()
        else:
            temporary, source = download_template()
        copy_project(source, output, clean_assets=args.clean_assets)
        if args.clean_assets:
            clean_character_assets(output)
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise
    finally:
        if temporary is not None:
            temporary.cleanup()

    print(f"Scaffolded project: {output}")
    if args.clean_assets:
        print("Add PNG/GIF scenes and generated/office.png, then run tools/prepare_assets.py")
    else:
        print("Demo assets were retained; replace them only after reviewing the new character mapping")


if __name__ == "__main__":
    main()
