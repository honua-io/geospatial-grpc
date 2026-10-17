#!/usr/bin/env python3
"""Measure the public archives actually admitted by the locked client installs."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def verify_payloads(payloads, installed_root):
    """Compare actual installed/runtime files with the measured public archive."""
    root = Path(installed_root).resolve(strict=True)
    if not payloads:
        raise ValueError("public archive has no selected runtime payload")
    measurements = {}
    for name, expected in payloads.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("archive runtime payload escapes its package")
        path = root / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError("installed runtime payload is missing or escapes its package")
        if path.read_bytes() != expected:
            raise ValueError("installed runtime payload differs from the measured public archive")
        measurements[relative.as_posix()] = hashlib.sha256(expected).hexdigest()
    return measurements


def measure(catalog, nuget, wheels, npm, lock, installed):
    clients = {row["client_lane"]: row for row in catalog["clients"]}
    paths = {"grpc-dotnet": nuget}
    wheel = list(wheels.glob("geospatial_grpc-*.whl"))
    tarballs = list(npm.glob("*.tgz"))
    if len(wheel) != 1 or len(tarballs) != 1:
        raise ValueError("each installed public client must have exactly one retained archive")
    paths.update({"grpc-python": wheel[0], "grpc-typescript": tarballs[0]})
    results = {}
    for lane, path in paths.items():
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 64 * 1024 * 1024:
            raise ValueError("public client archive is missing or exceeds its bound")
        data = path.read_bytes()
        client = clients[lane]
        digest = ("sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
                  if lane == "grpc-typescript" else "sha256:" + hashlib.sha256(data).hexdigest())
        if digest != client["package_digest"]:
            raise ValueError("measured installed archive differs from governed published package digest: " + lane)
        if lane == "grpc-dotnet":
            with zipfile.ZipFile(path) as archive:
                names = [name for name in archive.namelist() if name.endswith(".nuspec")]
                if len(names) != 1:
                    raise ValueError("NuGet archive has an ambiguous package manifest")
                metadata = ET.fromstring(archive.read(names[0]))
                coordinates = {node.tag.rsplit("}", 1)[-1]: node.text for node in metadata.iter()
                               if node.tag.rsplit("}", 1)[-1] in {"id", "version"}}
                package, version = coordinates.get("id"), coordinates.get("version")
                assets = json.loads(Path(installed[lane]["assets"]).read_text())
                target = assets["targets"]["net10.0"][f"{package}/{version}"]
                members = [name for name in target.get("runtime", {}) if name.endswith(".dll")]
                payloads = {Path(name).name: archive.read(name) for name in members}
                if len(payloads) != len(members):
                    raise ValueError("selected runtime assets have ambiguous basenames")
        elif lane == "grpc-python":
            with zipfile.ZipFile(path) as archive:
                names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
                if len(names) != 1:
                    raise ValueError("wheel has an ambiguous distribution manifest")
                metadata = archive.read(names[0]).decode()
                package = next((line[6:] for line in metadata.splitlines() if line.startswith("Name: ")), None)
                version = next((line[9:] for line in metadata.splitlines() if line.startswith("Version: ")), None)
                payloads = {name: archive.read(name) for name in archive.namelist()
                            if not name.endswith("/") and ".dist-info/" not in name}
        else:
            with tarfile.open(path, mode="r:gz") as archive:
                members = [member for member in archive.getmembers() if member.name == "package/package.json"]
                if len(members) != 1 or not members[0].isfile() or members[0].size > 1024 * 1024:
                    raise ValueError("npm archive has an ambiguous package manifest")
                metadata = json.load(archive.extractfile(members[0]))
                package, version = metadata.get("name"), metadata.get("version")
                members = [member for member in archive.getmembers() if not member.isdir()]
                if any(not member.isfile() or not member.name.startswith("package/") for member in members):
                    raise ValueError("npm runtime payload contains an unsupported link or member")
                payloads = {member.name[len("package/"):]: archive.extractfile(member).read() for member in members}
            locked_package = lock["packages"]["node_modules/@honua/geospatial-grpc"]
            if locked_package.get("integrity") != digest or locked_package.get("version") != version:
                raise ValueError("npm locked install does not bind the measured archive bytes")
        if (package, version) != (client["package"], client["client_version"]):
            raise ValueError("retained archive package/version differs from the installed coordinate: " + lane)
        runtime_files = verify_payloads(payloads, installed[lane]["root"])
        results[lane] = {"package": package, "package_version": version,
                         "package_source": client["package_source"], "package_digest": digest,
                         "archive_name": path.name, "archive_bytes": len(data), "runtime_files": runtime_files}
    return {"schema": "honua.grpc-client-artifacts/v1", "clients": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nuget", type=Path, required=True)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--npm", type=Path, required=True)
    parser.add_argument("--dotnet-assets", type=Path, required=True)
    parser.add_argument("--dotnet-output", type=Path, required=True)
    parser.add_argument("--python-installed", type=Path, required=True)
    parser.add_argument("--npm-installed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = measure(json.loads((ROOT / "certification/protocol-certification-catalog.v1.json").read_text()),
                    args.nuget, args.wheels, args.npm,
                    json.loads((ROOT / "certification/typescript/package-lock.json").read_text()),
                    {"grpc-dotnet": {"assets": args.dotnet_assets, "root": args.dotnet_output},
                     "grpc-python": {"root": args.python_installed}, "grpc-typescript": {"root": args.npm_installed}})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + "\n")


if __name__ == "__main__":
    main()
