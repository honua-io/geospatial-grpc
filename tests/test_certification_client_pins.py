"""The certification lanes install exactly the governed, published client bytes.

The catalog names each lane's governed package, version and published digest.
These checks bind the three installers to them: the pip requirement hash, the
npm lockfile integrity and the NuGet lockfile content hash. pip
--require-hashes, npm ci and NuGet locked-mode restore then refuse any other
bytes, so an executed lane report cannot come from a repacked or
source-generated client.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "certification" / "protocol-certification-catalog.v1.json"
REQUIREMENTS = ROOT / ".github" / "requirements" / "protocol-certification.txt"
NPM_LOCK = ROOT / "certification" / "typescript" / "package-lock.json"
NPM_PACKAGE = ROOT / "certification" / "typescript" / "package.json"
DOTNET_PROJECT = ROOT / "certification" / "dotnet" / "GrpcCertificationRunner.csproj"
DOTNET_LOCK = ROOT / "certification" / "dotnet" / "packages.lock.json"


class CertificationClientPinTests(unittest.TestCase):
    def setUp(self) -> None:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.clients = {client["client_lane"]: client for client in catalog["clients"]}

    def test_every_lane_is_a_published_release(self):
        for lane, client in self.clients.items():
            with self.subTest(lane=lane):
                self.assertEqual("published", client["publication_state"])
                self.assertRegex(client["client_version"], r"^[0-9]+\.[0-9]+\.[0-9]+$")
                self.assertTrue(client["package_digest"].startswith(("sha256:", "sha512-")))

    def test_python_requirement_pins_the_governed_wheel(self):
        client = self.clients["grpc-python"]
        text = REQUIREMENTS.read_text(encoding="utf-8")
        match = re.search(
            rf"^{re.escape(client['package'])}==(?P<version>\S+)\s*\\\s*\n\s*--hash=(?P<hash>sha256:[0-9a-f]{{64}})\s*$",
            text, re.MULTILINE)
        self.assertIsNotNone(match, "geospatial-grpc requirement with exactly one wheel hash")
        self.assertEqual(client["client_version"], match["version"])
        self.assertEqual(client["package_digest"], match["hash"])

    def test_typescript_lock_pins_the_governed_tarball(self):
        client = self.clients["grpc-typescript"]
        package = json.loads(NPM_PACKAGE.read_text(encoding="utf-8"))
        self.assertEqual(client["client_version"], package["dependencies"][client["package"]])
        locked = json.loads(NPM_LOCK.read_text(encoding="utf-8"))["packages"][f"node_modules/{client['package']}"]
        self.assertEqual(client["client_version"], locked["version"])
        self.assertEqual(client["package_digest"], locked["integrity"])

    def test_dotnet_lock_pins_the_governed_nupkg(self):
        client = self.clients["grpc-dotnet"]
        project = DOTNET_PROJECT.read_text(encoding="utf-8")
        self.assertIn(f'<PackageReference Include="{client["package"]}" Version="{client["client_version"]}" />', project)
        self.assertIn("<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>", project)
        self.assertIn("<RestoreLockedMode Condition=\"'$(CI)' == 'true'\">true</RestoreLockedMode>", project)
        locked = json.loads(DOTNET_LOCK.read_text(encoding="utf-8"))["dependencies"]["net10.0"][client["package"]]
        self.assertEqual(client["client_version"], locked["resolved"])
        self.assertEqual(client["package_lock_hash"], locked["contentHash"])


if __name__ == "__main__":
    unittest.main()
