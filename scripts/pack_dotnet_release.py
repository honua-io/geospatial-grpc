"""Pack and verify the exact tag-derived .NET artifact without publishing."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from verify_nuget_package import validate, verify_source_payload, validate_symbols


def version_from_tag(tag: str) -> str:
    # NuGet discards build metadata when identifying versions. Reject it so
    # distinct tags cannot silently address the same package coordinate.
    numeric = r"(?:0|[1-9][0-9]*)"
    identifier = rf"(?:{numeric}|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    pattern = rf"v{numeric}\.{numeric}\.{numeric}(?:-{identifier}(?:\.{identifier})*)?"
    if re.fullmatch(pattern, tag) is None:
        raise ValueError("Expected vMAJOR.MINOR.PATCH[-PRERELEASE], without build metadata")
    return tag[1:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, default=Path("nupkgs"))
    args = parser.parse_args()
    version = version_from_tag(args.tag)
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if list(output.glob("*.nupkg")) or list(output.glob("*.snupkg")):
        raise ValueError("Use an output directory without existing NuGet packages")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    subprocess.run(
        [
            "dotnet", "pack", "src/Geospatial.Grpc/Geospatial.Grpc.csproj",
            "--configuration", "Release", "--output", str(output),
            f"-p:Version={version}", f"-p:PackageVersion={version}",
            "-p:TreatWarningsAsErrors=true", "-p:ContinuousIntegrationBuild=true",
            f"-p:RepositoryCommit={commit}",
        ],
        cwd=root, check=True,
    )
    package = output / f"Geospatial.Grpc.{version}.nupkg"
    symbols = output / f"Geospatial.Grpc.{version}.snupkg"
    validate(package, "Geospatial.Grpc", version)
    verify_source_payload(package, root)
    validate_symbols(symbols, "Geospatial.Grpc", version)
    print(f"Verified Geospatial.Grpc {version} from {commit}")


if __name__ == "__main__":
    main()
