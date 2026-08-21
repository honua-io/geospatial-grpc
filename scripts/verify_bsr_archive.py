#!/usr/bin/env python3
"""Compare a public BSR archive with the canonical local module content."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath


class ArchiveError(ValueError):
    """Raised when a BSR archive is incomplete or has drifted."""


def canonical_digest(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def local_module_files(root: Path) -> dict[str, bytes]:
    candidates = [root / "LICENSE", root / "README.md"]
    if (root / "buf.md").is_file():
        candidates.append(root / "buf.md")
    candidates.extend(sorted((root / "geospatial").glob("v*/*.proto")))

    missing = [str(path.relative_to(root)) for path in candidates if not path.is_file()]
    if missing:
        raise ArchiveError(f"local module files are missing: {', '.join(missing)}")

    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in candidates
    }


def archive_files(archive: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(archive) as package:
            result: dict[str, bytes] = {}
            for info in package.infolist():
                if info.is_dir():
                    continue
                name = PurePosixPath(info.filename).as_posix()
                if (
                    name.startswith("/")
                    or "\\" in name
                    or ".." in PurePosixPath(name).parts
                ):
                    raise ArchiveError(f"unsafe path in BSR archive: {info.filename}")
                if name in result:
                    raise ArchiveError(f"duplicate path in BSR archive: {name}")
                result[name] = package.read(info)
            return result
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"cannot read {archive}: {exc}") from exc


def verify(root: Path, archive: Path) -> dict[str, object]:
    expected = local_module_files(root)
    actual = archive_files(archive)
    if set(expected) != set(actual):
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        raise ArchiveError(
            f"BSR archive inventory drift; missing={missing}, unexpected={unexpected}"
        )

    changed = [name for name in sorted(expected) if expected[name] != actual[name]]
    if changed:
        raise ArchiveError(f"BSR archive content drift: {changed}")

    return {
        "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "moduleContentSha256": canonical_digest(actual),
        "fileCount": len(actual),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = verify(args.root.resolve(), args.archive.resolve())
    except ArchiveError as exc:
        print(f"BSR verification error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True) if args.json else result["moduleContentSha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
