from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from app.github import _extract_source_files, parse_github_repository
from app.scanner import scan_repository


class GitHubRepositoryTests(unittest.TestCase):
    def test_repository_identity_includes_branch(self):
        main = parse_github_repository(
            "https://github.com/Owner/Repository.git?tab=readme",
            "main",
        )
        feature = parse_github_repository(
            "https://github.com/owner/repository",
            "feature/next",
        )

        self.assertEqual(main[2], "https://github.com/Owner/Repository")
        self.assertNotEqual(main[3], feature[3])

    def test_rejects_non_github_or_non_repository_urls(self):
        invalid_urls = (
            "http://github.com/owner/repository",
            "https://github.com.evil.test/owner/repository",
            "https://github.com/owner/repository/tree/main",
        )
        for github_url in invalid_urls:
            with self.subTest(github_url=github_url):
                with self.assertRaises(ValueError):
                    parse_github_repository(github_url, "main")

    def test_rejects_invalid_branch_names(self):
        for branch in ("", "../main", "main//next", "-option", "main.lock"):
            with self.subTest(branch=branch):
                with self.assertRaises(ValueError):
                    parse_github_repository(
                        "https://github.com/owner/repository",
                        branch,
                    )

    def test_extracts_supported_files_and_skips_ignored_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / "repository.zip"
            destination = temp_path / "repository"
            destination.mkdir()

            with ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "repository-main/src/app.py",
                    'print("ok")\n',
                )
                archive.writestr(
                    "repository-main/node_modules/generated.js",
                    "ignored",
                )

            _extract_source_files(archive_path, destination)

            self.assertEqual(
                (destination / "src" / "app.py").read_text(),
                'print("ok")\n',
            )
            self.assertFalse(
                (destination / "node_modules" / "generated.js").exists()
            )

    def test_rejects_archive_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / "repository.zip"
            destination = temp_path / "repository"
            destination.mkdir()

            with ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "repository-main/../../escaped.py",
                    "unsafe",
                )

            with self.assertRaises(ValueError):
                _extract_source_files(archive_path, destination)
            self.assertFalse((temp_path / "escaped.py").exists())

    def test_scans_source_under_temporary_directory_root(self):
        with tempfile.TemporaryDirectory(prefix="codebase-ai-tmp-") as temp_dir:
            repository = Path(temp_dir) / "repository"
            source_directory = repository / "src"
            source_directory.mkdir(parents=True)
            (source_directory / "app.py").write_text(
                'print("indexed")\n',
                encoding="utf-8",
            )
            (source_directory / "__init__.py").write_text(
                "",
                encoding="utf-8",
            )

            file_count, chunks = scan_repository(repository)

            self.assertEqual(file_count, 1)
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0]["path"], "src/app.py")


if __name__ == "__main__":
    unittest.main()
