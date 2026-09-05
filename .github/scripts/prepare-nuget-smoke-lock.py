"""Bind the reviewed consumer dependency lock to a verified release artifact."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def prepare(package: Path, version: str, output: Path) -> None:
    template = Path(__file__).resolve().parents[1] / "requirements/dotnet-smoke.lock.json"
    lock = json.loads(template.read_text(encoding="utf-8"))
    release = lock["dependencies"]["net10.0"]["Geospatial.Grpc"]
    with ZipFile(package) as archive:
        # NuGet locks use the unsigned content hash even after repository
        # signing. Always derive it from the verified unsigned build artifact.
        if ".signature.p7s" in archive.namelist():
            raise ValueError("Use the unsigned build artifact for NuGet's content hash")
        nuspecs = [name for name in archive.namelist() if name.endswith(".nuspec")]
        if len(nuspecs) != 1:
            raise ValueError("Expected exactly one package manifest")
        metadata = ET.fromstring(archive.read(nuspecs[0])).find("{*}metadata")
    if metadata is None:
        raise ValueError("Missing package metadata")
    if metadata.findtext("{*}id") != "Geospatial.Grpc" or metadata.findtext("{*}version") != version:
        raise ValueError("Release artifact identity does not match the consumer")
    groups = metadata.findall("{*}dependencies/{*}group")
    if len(groups) != 1 or groups[0].get("targetFramework") != ".NETStandard2.0":
        raise ValueError("Dependency target changed; review and regenerate the smoke lock")
    dependencies = {dep.attrib["id"]: dep.attrib["version"] for dep in groups[0]}
    if dependencies != release["dependencies"]:
        raise ValueError("Release dependencies changed; review and regenerate the smoke lock")
    release["requested"] = f"[{version}, )"
    release["resolved"] = version
    release["contentHash"] = base64.b64encode(hashlib.sha512(package.read_bytes()).digest()).decode("ascii")
    output.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.package, args.version, args.output)
