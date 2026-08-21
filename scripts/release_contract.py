#!/usr/bin/env python3
"""Validate the version contract shared by schema, package, fixtures, and tag."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?P<prerelease>-(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*)(?:\."
    r"(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?P<build>\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
PACKAGE_RE = re.compile(r"^\s*package\s+geospatial\.v(?P<major>\d+)\s*;", re.MULTILINE)


class ContractError(ValueError):
    """Raised when release coordinates disagree."""


def read_contract(root: Path) -> dict[str, object]:
    project = root / "src" / "Geospatial.Grpc" / "Geospatial.Grpc.csproj"
    fixture_version_file = root / "conformance" / "VERSION"

    try:
        project_version = ET.parse(project).findtext("./PropertyGroup/Version")
    except (ET.ParseError, OSError) as exc:
        raise ContractError(f"cannot read {project}: {exc}") from exc

    if not project_version:
        raise ContractError(f"{project} does not define <Version>")
    project_version = project_version.strip()

    try:
        fixture_version = fixture_version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ContractError(f"cannot read {fixture_version_file}: {exc}") from exc

    if project_version != fixture_version:
        raise ContractError(
            "version drift: Geospatial.Grpc is "
            f"{project_version}, but conformance/VERSION is {fixture_version}"
        )

    match = SEMVER_RE.fullmatch(project_version)
    if not match:
        raise ContractError(f"{project_version!r} is not canonical SemVer")

    proto_majors: set[int] = set()
    proto_files = sorted((root / "geospatial").glob("v*/*.proto"))
    if not proto_files:
        raise ContractError("no geospatial/v*/*.proto files were found")

    for proto in proto_files:
        package = PACKAGE_RE.search(proto.read_text(encoding="utf-8"))
        if package is None:
            raise ContractError(f"{proto} does not declare package geospatial.v<MAJOR>")
        proto_majors.add(int(package.group("major")))

    if len(proto_majors) != 1:
        raise ContractError(f"release contains multiple protocol majors: {sorted(proto_majors)}")

    version_major = int(match.group("major"))
    protocol_major = next(iter(proto_majors))
    is_prerelease = match.group("prerelease") is not None

    # The only documented exception is the historical v0.x-alpha stabilization
    # window. Stable releases and all post-v1 prereleases align their SemVer
    # major with the proto package major.
    if not (version_major == 0 and is_prerelease) and version_major != protocol_major:
        raise ContractError(
            f"release major {version_major} does not match geospatial.v{protocol_major}"
        )

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(
        rf"^## v{re.escape(project_version)}\s*$", changelog, re.MULTILINE
    ):
        raise ContractError(f"CHANGELOG.md has no '## v{project_version}' release entry")

    return {
        "version": project_version,
        "tag": f"v{project_version}",
        "protocolPackage": f"geospatial.v{protocol_major}",
        "protocolMajor": protocol_major,
        "releaseMajor": version_major,
        "prerelease": is_prerelease,
        "buildMetadata": match.group("build") is not None,
    }


def validate_tag(contract: dict[str, object], tag: str) -> None:
    expected = contract["tag"]
    if tag != expected:
        raise ContractError(f"tag {tag!r} does not match the required release tag {expected!r}")


def validate_stable(contract: dict[str, object]) -> None:
    if (
        int(contract["releaseMajor"]) == 0
        or bool(contract["prerelease"])
        or bool(contract["buildMetadata"])
    ):
        raise ContractError(
            f"{contract['version']} is not a canonical stable release version"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of scripts/)",
    )
    parser.add_argument("--tag", help="release tag to compare with the derived version")
    parser.add_argument(
        "--require-stable",
        action="store_true",
        help="reject prerelease/build metadata and a zero major",
    )
    parser.add_argument("--json", action="store_true", help="write the contract as JSON")
    args = parser.parse_args()

    try:
        contract = read_contract(args.root.resolve())
        if args.tag:
            validate_tag(contract, args.tag)
        if args.require_stable:
            validate_stable(contract)
    except (ContractError, OSError) as exc:
        print(f"release contract error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(contract, sort_keys=True))
    else:
        print(
            f"release contract valid: {contract['tag']} "
            f"({contract['protocolPackage']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
