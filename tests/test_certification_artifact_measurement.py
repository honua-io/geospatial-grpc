"""Archive hashing/coordinate controls, not evidence from published clients."""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location("artifact_measurement", Path(__file__).resolve().parents[1] / "scripts/measure_certification_artifacts.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def inputs(root):
    wheels, npm = root / "wheels", root / "npm"
    wheels.mkdir()
    npm.mkdir()
    nuget = root / "client.nupkg"
    with zipfile.ZipFile(nuget, "w") as archive:
        archive.writestr("Geospatial.Grpc.nuspec", '<package><metadata><id>Geospatial.Grpc</id><version>1.0.3</version></metadata></package>')
    wheel = wheels / "geospatial_grpc-1.0.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("geospatial_grpc-1.0.3.dist-info/METADATA", "Name: geospatial-grpc\nVersion: 1.0.3\n")
    tarball = npm / "honua-geospatial-grpc-1.0.3.tgz"
    metadata = json.dumps({"name": "@honua/geospatial-grpc", "version": "1.0.3"}).encode()
    with tarfile.open(tarball, "w:gz") as archive:
        entry = tarfile.TarInfo("package/package.json")
        entry.size = len(metadata)
        archive.addfile(entry, io.BytesIO(metadata))
    clients = []
    for lane, package, path in (("grpc-dotnet", "Geospatial.Grpc", nuget),
                                ("grpc-python", "geospatial-grpc", wheel),
                                ("grpc-typescript", "@honua/geospatial-grpc", tarball)):
        raw = path.read_bytes()
        digest = ("sha512-" + base64.b64encode(hashlib.sha512(raw).digest()).decode()
                  if lane == "grpc-typescript" else "sha256:" + hashlib.sha256(raw).hexdigest())
        clients.append({"client_lane": lane, "package": package, "client_version": "1.0.3",
                        "package_source": "https://registry.example/" + lane, "package_digest": digest})
    lock = {"packages": {"node_modules/@honua/geospatial-grpc": {
        "version": "1.0.3", "integrity": clients[2]["package_digest"]}}}
    return {"clients": clients}, nuget, wheels, npm, lock


class ArtifactMeasurementTests(unittest.TestCase):
    def test_measures_every_admitted_archive_and_retains_exact_digest_form(self):
        with tempfile.TemporaryDirectory() as directory:
            args = inputs(Path(directory))
            observed = MODULE.measure(*args)
            self.assertEqual("honua.grpc-client-artifacts/v1", observed["schema"])
            for client in args[0]["clients"]:
                actual = observed["clients"][client["client_lane"]]
                self.assertEqual(client["package_digest"], actual["package_digest"])
                self.assertEqual(client["package"], actual["package"])
                self.assertEqual("1.0.3", actual["package_version"])
                self.assertGreater(actual["archive_bytes"], 0)

    def test_repacked_archive_wrong_hash_or_absent_bytes_never_measure_as_governed(self):
        for lane in ("grpc-dotnet", "grpc-python", "grpc-typescript"):
            with self.subTest(lane=lane), tempfile.TemporaryDirectory() as directory:
                args = inputs(Path(directory))
                client = next(client for client in args[0]["clients"] if client["client_lane"] == lane)
                client["package_digest"] = "sha256:" + "0" * 64
                with self.assertRaisesRegex(ValueError, "measured installed archive"):
                    MODULE.measure(*args)
        with tempfile.TemporaryDirectory() as directory:
            args = inputs(Path(directory))
            args[1].unlink()
            with self.assertRaises(ValueError):
                MODULE.measure(*args)

    def test_archive_coordinate_and_locked_npm_integrity_are_independently_checked(self):
        for field, value in (("version", "9.9.9"), ("integrity", "sha512-wrong")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                args = inputs(Path(directory))
                args[4]["packages"]["node_modules/@honua/geospatial-grpc"][field] = value
                with self.assertRaisesRegex(ValueError, "npm locked install"):
                    MODULE.measure(*args)
        with tempfile.TemporaryDirectory() as directory:
            args = inputs(Path(directory))
            args[0]["clients"][0]["client_version"] = "9.9.9"
            with self.assertRaisesRegex(ValueError, "coordinate"):
                MODULE.measure(*args)

    def test_multiple_candidate_archives_cannot_be_selected_arbitrarily(self):
        with tempfile.TemporaryDirectory() as directory:
            args = inputs(Path(directory))
            (args[2] / "geospatial_grpc-9.9.9-py3-none-any.whl").write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                MODULE.measure(*args)


if __name__ == "__main__":
    unittest.main()
