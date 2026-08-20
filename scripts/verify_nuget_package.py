#!/usr/bin/env python3
"""Validate a Geospatial.Grpc package and compare registry-signed content."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath


# nuget.org repository-signs packages. These OPC/signature entries may differ
# from the locally packed unsigned artifact while the package payload remains
# identical. Everything else is compared byte-for-byte.
SIGNING_ENTRIES = {".signature.p7s", "[Content_Types].xml", "_rels/.rels"}


class PackageError(ValueError):
    """Raised when package identity or content is invalid."""


def package_files(package_path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(package_path) as package:
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
                    raise PackageError(f"unsafe path in package: {info.filename}")
                if name in result:
                    raise PackageError(f"duplicate path in package: {name}")
                result[name] = package.read(info)
            return result
    except (OSError, zipfile.BadZipFile) as exc:
        raise PackageError(f"cannot read {package_path}: {exc}") from exc


def semantic_files(files: dict[str, bytes]) -> dict[str, bytes]:
    return {
        name: content
        for name, content in files.items()
        if name not in SIGNING_ENTRIES and not name.startswith("package/services/metadata/")
    }


def canonical_digest(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(semantic_files(files).items()):
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def package_identity(files: dict[str, bytes]) -> tuple[str, str]:
    nuspecs = sorted(name for name in files if name.lower().endswith(".nuspec"))
    if len(nuspecs) != 1:
        raise PackageError(f"expected one .nuspec, found {nuspecs}")
    try:
        root = ET.fromstring(files[nuspecs[0]])
    except ET.ParseError as exc:
        raise PackageError(f"invalid nuspec: {exc}") from exc

    def metadata_value(name: str) -> str | None:
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] == name:
                return element.text
        return None

    package_id = metadata_value("id")
    version = metadata_value("version")
    if not package_id or not version:
        raise PackageError("nuspec does not contain package id and version")
    return package_id.strip(), version.strip()


def validate(
    package_path: Path,
    expected_id: str,
    expected_version: str,
) -> dict[str, object]:
    files = package_files(package_path)
    package_id, version = package_identity(files)
    if package_id != expected_id or version != expected_version:
        raise PackageError(
            f"package identity {package_id} {version} does not match "
            f"{expected_id} {expected_version}"
        )

    required = {
        "README.md",
        "lib/netstandard2.0/Geospatial.Grpc.dll",
    }
    missing = sorted(required - set(files))
    if missing:
        raise PackageError(f"package is missing required entries: {missing}")
    if not any(name.startswith("proto/geospatial/v1/") and name.endswith(".proto") for name in files):
        raise PackageError("package contains no proto/geospatial/v1/*.proto files")

    return {
        "packageId": package_id,
        "version": version,
        "rawSha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
        "contentSha256": canonical_digest(files),
        "fileCount": len(files),
    }


def validate_symbols(
    package_path: Path,
    expected_id: str,
    expected_version: str,
) -> dict[str, object]:
    files = package_files(package_path)
    package_id, version = package_identity(files)
    if package_id != expected_id or version != expected_version:
        raise PackageError(
            f"symbol package identity {package_id} {version} does not match "
            f"{expected_id} {expected_version}"
        )

    pdb_path = "lib/netstandard2.0/Geospatial.Grpc.pdb"
    if pdb_path not in files:
        raise PackageError(f"symbol package is missing required entry: {pdb_path}")
    unexpected_binaries = sorted(
        name for name in files if name.lower().endswith((".dll", ".exe"))
    )
    if unexpected_binaries:
        raise PackageError(
            f"symbol package contains runtime binaries: {unexpected_binaries}"
        )

    nuspec_name = next(name for name in files if name.lower().endswith(".nuspec"))
    try:
        nuspec = ET.fromstring(files[nuspec_name])
    except ET.ParseError as exc:  # pragma: no cover - package_identity caught this
        raise PackageError(f"invalid symbol nuspec: {exc}") from exc
    package_types = {
        element.attrib.get("name")
        for element in nuspec.iter()
        if element.tag.rsplit("}", 1)[-1] == "packageType"
    }
    if "SymbolsPackage" not in package_types:
        raise PackageError("symbol package nuspec is not a SymbolsPackage")

    return {
        "packageId": package_id,
        "version": version,
        "rawSha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
        "contentSha256": canonical_digest(files),
        "fileCount": len(files),
    }


def verify_source_payload(package_path: Path, root: Path) -> dict[str, object]:
    files = package_files(package_path)
    expected: dict[str, bytes] = {"README.md": (root / "README.md").read_bytes()}
    expected.update(
        {
            f"proto/{path.relative_to(root).as_posix()}": path.read_bytes()
            for path in sorted((root / "geospatial" / "v1").glob("*.proto"))
        }
    )
    actual = {
        name: content
        for name, content in files.items()
        if name == "README.md" or name.startswith("proto/geospatial/v1/")
    }
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        raise PackageError(
            f"canonical source inventory drift; missing={missing}, "
            f"unexpected={unexpected}"
        )
    changed = [name for name in sorted(expected) if expected[name] != actual[name]]
    if changed:
        raise PackageError(f"canonical source payload drift: {changed}")
    return {
        "sourceContentSha256": canonical_digest(actual),
        "sourceFileCount": len(actual),
    }


def compare(expected: Path, actual: Path) -> None:
    expected_files = semantic_files(package_files(expected))
    actual_files = semantic_files(package_files(actual))
    if set(expected_files) != set(actual_files):
        missing = sorted(set(expected_files) - set(actual_files))
        unexpected = sorted(set(actual_files) - set(expected_files))
        raise PackageError(
            f"package inventory drift; missing={missing}, unexpected={unexpected}"
        )
    changed = [
        name
        for name in sorted(expected_files)
        if expected_files[name] != actual_files[name]
    ]
    if changed:
        raise PackageError(f"package payload drift: {changed}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--symbol-package", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--compare", type=Path, help="registry copy to compare")
    parser.add_argument("--id", default="Geospatial.Grpc")
    parser.add_argument("--version", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = validate(args.package.resolve(), args.id, args.version)
        if args.root:
            result["sourcePayload"] = verify_source_payload(
                args.package.resolve(), args.root.resolve()
            )
        if args.symbol_package:
            result["symbolPackage"] = validate_symbols(
                args.symbol_package.resolve(), args.id, args.version
            )
        if args.compare:
            validate(args.compare.resolve(), args.id, args.version)
            compare(args.package.resolve(), args.compare.resolve())
    except PackageError as exc:
        print(f"NuGet verification error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True) if args.json else result["contentSha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
