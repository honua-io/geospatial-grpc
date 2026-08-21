#!/usr/bin/env python3
"""Create deterministic registry evidence for a Geospatial.Grpc release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from release_contract import read_contract
from verify_bsr_archive import verify as verify_bsr
from verify_nuget_package import (
    compare as compare_nuget,
    validate as validate_nuget,
    validate_symbols,
    verify_source_payload,
)


GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
BSR_COMMIT_RE = re.compile(r"^[0-9a-f]{32}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_receipt(
    *,
    version: str,
    git_commit: str,
    bsr_commit: str,
    bsr_archive: Path,
    nuget_package: Path,
    public_nuget_package: Path,
    symbol_package_path: Path,
    public_consumption: Path,
    assets_dir: Path,
    root: Path,
    output: Path,
    workflow_run_url: str | None = None,
) -> dict[str, object]:
    root = root.resolve()
    contract = read_contract(root)
    if contract["version"] != version:
        raise ValueError(
            f"receipt version {version} does not match repository contract "
            f"{contract['version']}"
        )
    if not GIT_COMMIT_RE.fullmatch(git_commit):
        raise ValueError(f"invalid git commit: {git_commit!r}")
    if not BSR_COMMIT_RE.fullmatch(bsr_commit):
        raise ValueError(f"invalid BSR commit: {bsr_commit!r}")

    assets_dir = assets_dir.resolve()
    output = output.resolve()
    bsr_archive = bsr_archive.resolve()
    local_nuget_path = nuget_package.resolve()
    public_nuget_path = public_nuget_package.resolve()
    symbol_package_path = symbol_package_path.resolve()
    bsr = verify_bsr(root, bsr_archive)
    local_nuget = validate_nuget(
        local_nuget_path, "Geospatial.Grpc", version
    )
    public_nuget = validate_nuget(
        public_nuget_path, "Geospatial.Grpc", version
    )
    compare_nuget(local_nuget_path, public_nuget_path)
    local_source = verify_source_payload(local_nuget_path, root)
    public_source = verify_source_payload(public_nuget_path, root)
    symbol_package = validate_symbols(
        symbol_package_path, "Geospatial.Grpc", version
    )

    consumption = json.loads(public_consumption.read_text(encoding="utf-8"))
    expected_consumption = {
        "status": "passed",
        "credentialFree": True,
        "version": version,
        "bsrCommit": bsr_commit,
    }
    mismatches = {
        key: {"expected": value, "actual": consumption.get(key)}
        for key, value in expected_consumption.items()
        if consumption.get(key) != value
    }
    if mismatches:
        raise ValueError(f"public consumption receipt does not match release: {mismatches}")

    artifact_paths = sorted(
        path
        for path in assets_dir.iterdir()
        if path.is_file() and path.resolve() != output
    )

    receipt = {
        "schemaVersion": 1,
        "release": {
            "version": version,
            "tag": f"v{version}",
            "gitCommit": git_commit,
            "workflowRunUrl": workflow_run_url,
        },
        "bsr": {
            "module": "buf.build/honua-io/geospatial-grpc",
            "commit": bsr_commit,
            "immutableRef": f"buf.build/honua-io/geospatial-grpc:{bsr_commit}",
            "releaseLabel": f"v{version}",
            "archiveUrl": (
                "https://buf.build/honua-io/geospatial-grpc/archive/"
                f"{bsr_commit}.zip"
            ),
            **bsr,
        },
        "nuget": {
            "packageId": "Geospatial.Grpc",
            "version": version,
            "packageUrl": f"https://www.nuget.org/packages/Geospatial.Grpc/{version}",
            "payloadMatch": True,
            "localPackage": local_nuget,
            "publicPackage": public_nuget,
            "symbolPackage": symbol_package,
            "canonicalSource": {
                "payloadMatch": local_source == public_source,
                **local_source,
            },
        },
        "publicConsumption": consumption,
        "artifacts": [
            {"name": path.name, "sha256": sha256(path), "size": path.stat().st_size}
            for path in artifact_paths
        ],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--bsr-commit", required=True)
    parser.add_argument("--bsr-archive", type=Path, required=True)
    parser.add_argument("--nuget-package", type=Path, required=True)
    parser.add_argument("--public-nuget-package", type=Path, required=True)
    parser.add_argument("--symbol-package", type=Path, required=True)
    parser.add_argument("--public-consumption", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workflow-run-url")
    args = parser.parse_args()

    create_receipt(
        version=args.version,
        git_commit=args.git_commit,
        bsr_commit=args.bsr_commit,
        bsr_archive=args.bsr_archive,
        nuget_package=args.nuget_package,
        public_nuget_package=args.public_nuget_package,
        symbol_package_path=args.symbol_package,
        public_consumption=args.public_consumption,
        assets_dir=args.assets_dir,
        root=args.root,
        output=args.output,
        workflow_run_url=args.workflow_run_url,
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
