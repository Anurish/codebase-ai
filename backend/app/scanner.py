from pathlib import Path

from .config import settings


IGNORED_DIRS = {
    ".git",
    ".next",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    "coverage",

    # Local backup created during Phase 3 setup
    "backend-phase2-backup",

    # Other common generated folders
    ".cache",
    ".pytest_cache",
    "tmp",
    "temp",
}

EXTENSIONS = {
    ".php",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".py",
    ".java",
    ".go",
    ".rb",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".cs",
    ".sql",
    ".json",
    ".yml",
    ".yaml",
    ".md",
    ".css",
    ".scss",
    ".html",
}


def iter_source_files(root):
    base = Path(root)

    for path in base.rglob("*"):
        if (
            path.is_file()
            and path.suffix.lower() in EXTENSIONS
            and not any(part in IGNORED_DIRS for part in path.parts)
        ):
            try:
                if path.stat().st_size <= 500_000:
                    yield path
            except OSError:
                pass


def chunk_file(path, root, size=80, overlap=15):
    try:
        lines = path.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines()
    except OSError:
        return []

    relative_path = path.relative_to(root).as_posix()

    chunks = []
    step = max(1, size - overlap)

    for start in range(0, len(lines), step):
        end = min(len(lines), start + size)

        content = "\n".join(lines[start:end]).strip()

        if content:
            chunks.append(
                {
                    "path": relative_path,
                    "start_line": start + 1,
                    "end_line": end,
                    "content": content,
                }
            )

        if end == len(lines):
            break

    return chunks


def scan_repository(root):
    base = Path(root)

    files = 0
    chunks = []

    for path in iter_source_files(root):
        files += 1
        chunks.extend(chunk_file(path, base))

    return files, chunks