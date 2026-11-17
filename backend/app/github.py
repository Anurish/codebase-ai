from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Generator
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import BadZipFile, ZipFile

from .scanner import EXTENSIONS, IGNORED_DIRS


MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 100_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_SOURCE_FILES = 25_000
MAX_SOURCE_BYTES = 250 * 1024 * 1024
MAX_SOURCE_FILE_BYTES = 500_000


class GitHubDownloadError(RuntimeError):
    pass


def parse_github_repository(github_url: str, branch: str):
    parsed = urlparse(github_url.strip())
    path = parsed.path
    if path.endswith("/"):
        path = path[:-1]
    if path.startswith("/"):
        path = path[1:]
    path_parts = path.split("/")

    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or len(path_parts) != 2
    ):
        raise ValueError(
            "Enter a public GitHub repository URL such as "
            "https://github.com/owner/repository."
        )

    owner, repository_name = path_parts
    if repository_name.endswith(".git"):
        repository_name = repository_name[:-4]

    valid_segment = re.compile(r"[A-Za-z0-9_.-]+")
    if (
        not valid_segment.fullmatch(owner)
        or not valid_segment.fullmatch(repository_name)
        or owner in {".", ".."}
        or repository_name in {".", ".."}
    ):
        raise ValueError("The GitHub repository URL is invalid.")

    if (
        not branch
        or len(branch) > 255
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch)
        or "//" in branch
        or ".." in branch
        or branch.endswith("/")
        or any(
            part.startswith(".") or part.endswith(".") or part.endswith(".lock")
            for part in branch.split("/")
        )
    ):
        raise ValueError("Enter a valid branch name.")

    canonical_url = f"https://github.com/{owner}/{repository_name}"
    repository_id = (
        f"github.com/{owner.lower()}/{repository_name.lower()}@{branch}"
    )
    return owner, repository_name, canonical_url, repository_id


class _CodeloadRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        target = urlparse(url)
        if (
            target.scheme != "https"
            or target.hostname != "codeload.github.com"
            or target.port is not None
            or target.username is not None
            or target.password is not None
        ):
            raise HTTPError(
                url,
                code,
                "GitHub archive redirected to an untrusted host",
                headers,
                response,
            )
        return super().redirect_request(
            request,
            response,
            code,
            message,
            headers,
            url,
        )


def _download_archive(owner: str, repository_name: str, branch: str, archive_path: Path):
    encoded_branch = quote(branch, safe="/")
    archive_url = (
        f"https://codeload.github.com/{owner}/{repository_name}/zip/"
        f"refs/heads/{encoded_branch}"
    )
    request = Request(
        archive_url,
        headers={"User-Agent": "Codebase-AI"},
    )
    opener = build_opener(_CodeloadRedirectHandler())

    with opener.open(request, timeout=30) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_ARCHIVE_BYTES:
            raise ValueError("The GitHub archive exceeds the 100 MB download limit.")

        downloaded = 0
        with archive_path.open("wb") as archive_file:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                downloaded += len(block)
                if downloaded > MAX_ARCHIVE_BYTES:
                    raise ValueError(
                        "The GitHub archive exceeds the 100 MB download limit."
                    )
                archive_file.write(block)


def _extract_source_files(archive_path: Path, destination: Path) -> None:
    try:
        with ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("The GitHub archive contains too many files.")

            total_uncompressed_bytes = sum(entry.file_size for entry in entries)
            if total_uncompressed_bytes > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise ValueError(
                    "The GitHub archive expands beyond the allowed size."
                )

            roots = set()
            candidates = []

            for entry in entries:
                raw_name = entry.filename
                if "\\" in raw_name:
                    raise ValueError("The GitHub archive contains an invalid path.")

                archive_path_parts = raw_name.split("/")
                if (
                    raw_name.startswith("/")
                    or any(part in {"", ".", ".."} for part in archive_path_parts[:-1])
                    or (archive_path_parts[-1] in {".", ".."})
                ):
                    raise ValueError("The GitHub archive contains an invalid path.")

                entry_path = PurePosixPath(raw_name)
                if entry_path.is_absolute() or len(entry_path.parts) < 2:
                    continue
                roots.add(entry_path.parts[0])
                relative_parts = entry_path.parts[1:]
                if not relative_parts or entry.is_dir():
                    continue
                if any(part in IGNORED_DIRS for part in relative_parts):
                    continue
                if Path(relative_parts[-1]).suffix.lower() not in EXTENSIONS:
                    continue
                if entry.file_size > MAX_SOURCE_FILE_BYTES:
                    continue
                candidates.append((entry, relative_parts))

            if len(roots) != 1:
                raise ValueError("The GitHub archive has an unexpected directory layout.")
            if len(candidates) > MAX_SOURCE_FILES:
                raise ValueError("The GitHub repository contains too many source files.")

            total_source_bytes = sum(entry.file_size for entry, _ in candidates)
            if total_source_bytes > MAX_SOURCE_BYTES:
                raise ValueError("The repository source files exceed the allowed size.")

            destination_resolved = destination.resolve()
            for entry, relative_parts in candidates:
                target = destination.joinpath(*relative_parts)
                if not target.resolve().is_relative_to(destination_resolved):
                    raise ValueError("The GitHub archive contains an invalid path.")
                target.parent.mkdir(parents=True, exist_ok=True)

                written = 0
                with archive.open(entry) as source, target.open("wb") as output:
                    while True:
                        block = source.read(64 * 1024)
                        if not block:
                            break
                        written += len(block)
                        if written > MAX_SOURCE_FILE_BYTES:
                            raise ValueError(
                                "A source file in the GitHub archive is too large."
                            )
                        output.write(block)
                if written != entry.file_size:
                    raise BadZipFile("GitHub archive entry size did not match its header.")
    except BadZipFile as exc:
        raise ValueError("GitHub returned an invalid repository archive.") from exc


@contextmanager
def download_public_repository(
    owner: str,
    repository_name: str,
    branch: str,
) -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory(prefix="codebase-ai-github-") as temp_dir:
        temp_path = Path(temp_dir)
        archive_path = temp_path / "repository.zip"
        repository_path = temp_path / "repository"

        try:
            _download_archive(owner, repository_name, branch, archive_path)
            repository_path.mkdir()
            _extract_source_files(archive_path, repository_path)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise GitHubDownloadError(
                f"Unable to download the public GitHub repository: {exc}"
            ) from exc
        except ValueError as exc:
            raise GitHubDownloadError(str(exc)) from exc

        yield repository_path
