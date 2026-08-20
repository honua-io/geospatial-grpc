#!/usr/bin/env python3
"""Probe and validate the public BSR and nuget.org release coordinates."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from release_contract import SEMVER_RE
from verify_bsr_archive import ArchiveError, verify as verify_bsr
from verify_nuget_package import (
    PackageError,
    compare as compare_nuget,
    validate as validate_nuget,
    verify_source_payload,
)


class RegistryError(RuntimeError):
    """Raised when a public registry cannot prove the requested coordinate."""


BSR_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def download(
    url: str,
    destination: Path,
    *,
    attempts: int,
    delay_seconds: float,
) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "geospatial-grpc-release-verifier/1"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise RegistryError(f"GET {url} returned HTTP {response.status}")
                with partial.open("wb") as output:
                    shutil.copyfileobj(response, output)
            partial.replace(destination)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and attempt == attempts:
                partial.unlink(missing_ok=True)
                return False
            failure: Exception = exc
        except (OSError, urllib.error.URLError, RegistryError) as exc:
            failure = exc

        partial.unlink(missing_ok=True)
        if attempt < attempts:
            time.sleep(delay_seconds)
        else:
            raise RegistryError(
                f"GET {url} failed after {attempts} attempt(s): {failure}"
            ) from failure
    raise AssertionError("download attempt loop exited unexpectedly")


def probe(
    *,
    root: Path,
    version: str,
    local_nuget: Path,
    download_dir: Path,
    bsr_ref: str,
    attempts: int,
    delay_seconds: float,
    require_existing: bool,
) -> dict[str, object]:
    version_match = SEMVER_RE.fullmatch(version)
    if (
        version_match is None
        or version_match.group("prerelease") is not None
        or version_match.group("build") is not None
        or int(version_match.group("major")) == 0
    ):
        raise RegistryError(f"not a canonical stable version: {version!r}")
    if not BSR_REF_RE.fullmatch(bsr_ref):
        raise RegistryError(f"invalid BSR reference: {bsr_ref!r}")
    if not local_nuget.is_file():
        raise RegistryError(f"local NuGet package is missing: {local_nuget}")
    verify_source_payload(local_nuget, root)

    bsr_url = (
        "https://buf.build/honua-io/geospatial-grpc/archive/"
        f"{bsr_ref}.zip"
    )
    nuget_url = (
        "https://api.nuget.org/v3-flatcontainer/geospatial.grpc/"
        f"{version.lower()}/geospatial.grpc.{version.lower()}.nupkg"
    )
    bsr_archive = download_dir / f"geospatial-grpc-bsr-{bsr_ref}.zip"
    public_nuget = download_dir / f"Geospatial.Grpc.{version}.public.nupkg"

    bsr_exists = download(
        bsr_url,
        bsr_archive,
        attempts=attempts,
        delay_seconds=delay_seconds,
    )
    nuget_exists = download(
        nuget_url,
        public_nuget,
        attempts=attempts,
        delay_seconds=delay_seconds,
    )

    if require_existing and not bsr_exists:
        raise RegistryError(f"required BSR coordinate is missing: {bsr_url}")
    if require_existing and not nuget_exists:
        raise RegistryError(f"required nuget.org coordinate is missing: {nuget_url}")

    bsr_result: dict[str, object] = {
        "state": "present" if bsr_exists else "missing",
        "ref": bsr_ref,
        "url": bsr_url,
    }
    if bsr_exists:
        bsr_result.update(verify_bsr(root, bsr_archive))
        bsr_result["archive"] = str(bsr_archive)

    nuget_result: dict[str, object] = {
        "state": "present" if nuget_exists else "missing",
        "packageId": "Geospatial.Grpc",
        "version": version,
        "url": nuget_url,
    }
    if nuget_exists:
        public_result = validate_nuget(public_nuget, "Geospatial.Grpc", version)
        compare_nuget(local_nuget, public_nuget)
        verify_source_payload(public_nuget, root)
        nuget_result.update(public_result)
        nuget_result["package"] = str(public_nuget)

    return {
        "schemaVersion": 1,
        "bsr": bsr_result,
        "nuget": nuget_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--local-nuget", type=Path, required=True)
    parser.add_argument("--download-dir", type=Path, required=True)
    parser.add_argument("--bsr-ref")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--delay-seconds", type=float, default=10)
    parser.add_argument("--require-existing", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds cannot be negative")

    try:
        result = probe(
            root=args.root.resolve(),
            version=args.version,
            local_nuget=args.local_nuget.resolve(),
            download_dir=args.download_dir.resolve(),
            bsr_ref=args.bsr_ref or f"v{args.version}",
            attempts=args.attempts,
            delay_seconds=args.delay_seconds,
            require_existing=args.require_existing,
        )
    except (ArchiveError, PackageError, RegistryError, OSError) as exc:
        print(f"public registry verification error: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
