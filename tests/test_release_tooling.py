from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_contract = load_script("release_contract")
verify_bsr_archive = load_script("verify_bsr_archive")
verify_nuget_package = load_script("verify_nuget_package")
create_release_receipt = load_script("create_release_receipt")
check_public_registry = load_script("check_public_registry")


class ReleaseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src" / "Geospatial.Grpc").mkdir(parents=True)
        (self.root / "conformance").mkdir()
        (self.root / "geospatial" / "v1").mkdir(parents=True)
        (self.root / "src" / "Geospatial.Grpc" / "Geospatial.Grpc.csproj").write_text(
            "<Project><PropertyGroup><Version>1.0.0</Version></PropertyGroup></Project>",
            encoding="utf-8",
        )
        (self.root / "conformance" / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        (self.root / "geospatial" / "v1" / "test.proto").write_text(
            'syntax = "proto3";\npackage geospatial.v1;\n', encoding="utf-8"
        )
        (self.root / "CHANGELOG.md").write_text("## v1.0.0\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_stable_contract_and_tag_match(self) -> None:
        contract = release_contract.read_contract(self.root)
        self.assertEqual("v1.0.0", contract["tag"])
        release_contract.validate_tag(contract, "v1.0.0")

    def test_fixture_drift_fails(self) -> None:
        (self.root / "conformance" / "VERSION").write_text("1.0.1\n", encoding="utf-8")
        with self.assertRaisesRegex(release_contract.ContractError, "version drift"):
            release_contract.read_contract(self.root)

    def test_stable_major_must_match_proto_package(self) -> None:
        project = self.root / "src" / "Geospatial.Grpc" / "Geospatial.Grpc.csproj"
        project.write_text(
            "<Project><PropertyGroup><Version>2.0.0</Version></PropertyGroup></Project>",
            encoding="utf-8",
        )
        (self.root / "conformance" / "VERSION").write_text("2.0.0\n", encoding="utf-8")
        (self.root / "CHANGELOG.md").write_text("## v2.0.0\n", encoding="utf-8")
        with self.assertRaisesRegex(release_contract.ContractError, "does not match"):
            release_contract.read_contract(self.root)

    def test_build_metadata_is_not_a_publishable_stable_coordinate(self) -> None:
        project = self.root / "src" / "Geospatial.Grpc" / "Geospatial.Grpc.csproj"
        project.write_text(
            "<Project><PropertyGroup><Version>1.0.0+local</Version></PropertyGroup></Project>",
            encoding="utf-8",
        )
        (self.root / "conformance" / "VERSION").write_text(
            "1.0.0+local\n", encoding="utf-8"
        )
        (self.root / "CHANGELOG.md").write_text(
            "## v1.0.0+local\n", encoding="utf-8"
        )
        contract = release_contract.read_contract(self.root)
        with self.assertRaisesRegex(
            release_contract.ContractError, "not a canonical stable"
        ):
            release_contract.validate_stable(contract)


class BsrArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        (self.root / "geospatial" / "v1").mkdir(parents=True)
        (self.root / "LICENSE").write_bytes(b"license\n")
        (self.root / "README.md").write_bytes(b"readme\n")
        (self.root / "geospatial" / "v1" / "test.proto").write_bytes(b"package geospatial.v1;\n")
        self.archive = Path(self.temp.name) / "module.zip"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_archive(self, *, proto: bytes = b"package geospatial.v1;\n") -> None:
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("LICENSE", b"license\n")
            archive.writestr("README.md", b"readme\n")
            archive.writestr("geospatial/v1/test.proto", proto)

    def test_exact_public_archive_passes(self) -> None:
        self.write_archive()
        result = verify_bsr_archive.verify(self.root, self.archive)
        self.assertEqual(3, result["fileCount"])

    def test_schema_drift_fails(self) -> None:
        self.write_archive(proto=b"package geospatial.v1; // drift\n")
        with self.assertRaisesRegex(verify_bsr_archive.ArchiveError, "content drift"):
            verify_bsr_archive.verify(self.root, self.archive)


class NugetPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.local = Path(self.temp.name) / "local.nupkg"
        self.remote = Path(self.temp.name) / "remote.nupkg"

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def write_package(
        path: Path,
        *,
        dll: bytes = b"assembly",
        signed: bool = False,
        symbols: bool = False,
        readme: bytes = b"readme",
        proto: bytes = b"schema",
    ) -> None:
        with zipfile.ZipFile(path, "w") as package:
            package_type = (
                "<packageTypes><packageType name=\"SymbolsPackage\"/></packageTypes>"
                if symbols
                else ""
            )
            package.writestr(
                "Geospatial.Grpc.nuspec",
                "<package><metadata><id>Geospatial.Grpc</id>"
                f"<version>1.0.0</version>{package_type}</metadata></package>",
            )
            if symbols:
                package.writestr("lib/netstandard2.0/Geospatial.Grpc.pdb", b"symbols")
            else:
                package.writestr("README.md", readme)
                package.writestr("lib/netstandard2.0/Geospatial.Grpc.dll", dll)
                package.writestr("proto/geospatial/v1/test.proto", proto)
            package.writestr("[Content_Types].xml", b"signed" if signed else b"unsigned")
            package.writestr("_rels/.rels", b"signed" if signed else b"unsigned")
            if signed:
                package.writestr(".signature.p7s", b"repository signature")

    def test_repository_signature_differences_are_accepted(self) -> None:
        self.write_package(self.local)
        self.write_package(self.remote, signed=True)
        verify_nuget_package.validate(self.local, "Geospatial.Grpc", "1.0.0")
        verify_nuget_package.compare(self.local, self.remote)

    def test_payload_drift_fails(self) -> None:
        self.write_package(self.local)
        self.write_package(self.remote, dll=b"different", signed=True)
        with self.assertRaisesRegex(verify_nuget_package.PackageError, "payload drift"):
            verify_nuget_package.compare(self.local, self.remote)

    def test_symbol_package_identity_and_portable_pdb_are_required(self) -> None:
        symbols = Path(self.temp.name) / "Geospatial.Grpc.1.0.0.snupkg"
        self.write_package(symbols, symbols=True)
        result = verify_nuget_package.validate_symbols(
            symbols, "Geospatial.Grpc", "1.0.0"
        )
        self.assertEqual("1.0.0", result["version"])

        invalid = Path(self.temp.name) / "invalid.snupkg"
        self.write_package(invalid)
        with self.assertRaisesRegex(
            verify_nuget_package.PackageError, "missing required entry"
        ):
            verify_nuget_package.validate_symbols(
                invalid, "Geospatial.Grpc", "1.0.0"
            )

    def test_canonical_proto_payload_drift_fails(self) -> None:
        root = Path(self.temp.name) / "repo"
        (root / "geospatial" / "v1").mkdir(parents=True)
        (root / "README.md").write_bytes(b"readme")
        (root / "geospatial" / "v1" / "test.proto").write_bytes(b"schema")
        self.write_package(self.local, proto=b"different")
        with self.assertRaisesRegex(
            verify_nuget_package.PackageError, "canonical source payload drift"
        ):
            verify_nuget_package.verify_source_payload(self.local, root)


class ReleaseReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        (self.root / "src" / "Geospatial.Grpc").mkdir(parents=True)
        (self.root / "conformance").mkdir()
        (self.root / "geospatial" / "v1").mkdir(parents=True)
        (self.root / "assets").mkdir()
        (self.root / "src" / "Geospatial.Grpc" / "Geospatial.Grpc.csproj").write_text(
            "<Project><PropertyGroup><Version>1.0.0</Version></PropertyGroup></Project>",
            encoding="utf-8",
        )
        (self.root / "conformance" / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        (self.root / "CHANGELOG.md").write_text("## v1.0.0\n", encoding="utf-8")
        (self.root / "LICENSE").write_bytes(b"license\n")
        (self.root / "README.md").write_bytes(b"readme")
        proto = b'syntax = "proto3";\npackage geospatial.v1;\n'
        (self.root / "geospatial" / "v1" / "test.proto").write_bytes(proto)

        self.local = self.root / "assets" / "Geospatial.Grpc.1.0.0.nupkg"
        self.public = self.root / "public.nupkg"
        self.symbols = self.root / "assets" / "Geospatial.Grpc.1.0.0.snupkg"
        NugetPackageTests.write_package(self.local, proto=proto)
        NugetPackageTests.write_package(self.public, signed=True, proto=proto)
        NugetPackageTests.write_package(self.symbols, symbols=True)

        self.bsr = self.root / "assets" / "geospatial-grpc-bsr.zip"
        with zipfile.ZipFile(self.bsr, "w") as archive:
            archive.writestr("LICENSE", b"license\n")
            archive.writestr("README.md", b"readme")
            archive.writestr(
                "geospatial/v1/test.proto",
                b'syntax = "proto3";\npackage geospatial.v1;\n',
            )
        self.consumption = self.root / "consumption.json"
        self.consumption.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "credentialFree": True,
                    "version": "1.0.0",
                    "bsrCommit": "a" * 32,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create(self, *, consumption: Path | None = None) -> dict[str, object]:
        output = self.root / "assets" / "release-receipt.json"
        return create_release_receipt.create_receipt(
            version="1.0.0",
            git_commit="b" * 40,
            bsr_commit="a" * 32,
            bsr_archive=self.bsr,
            nuget_package=self.local,
            public_nuget_package=self.public,
            symbol_package_path=self.symbols,
            public_consumption=consumption or self.consumption,
            assets_dir=self.root / "assets",
            root=self.root,
            output=output,
        )

    def test_receipt_binds_both_public_registries_and_symbol_package(self) -> None:
        receipt = self.create()
        self.assertTrue(receipt["nuget"]["payloadMatch"])
        self.assertEqual("a" * 32, receipt["bsr"]["commit"])
        self.assertEqual("1.0.0", receipt["nuget"]["symbolPackage"]["version"])
        self.assertTrue(receipt["publicConsumption"]["credentialFree"])

    def test_wrong_public_consumption_coordinate_fails_closed(self) -> None:
        wrong = self.root / "wrong-consumption.json"
        wrong.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "credentialFree": True,
                    "version": "1.0.1",
                    "bsrCommit": "a" * 32,
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "does not match release"):
            self.create(consumption=wrong)


class PublicRegistryProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        (self.root / "geospatial" / "v1").mkdir(parents=True)
        (self.root / "LICENSE").write_bytes(b"license\n")
        (self.root / "README.md").write_bytes(b"readme")
        (self.root / "geospatial" / "v1" / "test.proto").write_bytes(b"schema")
        self.local = self.root / "Geospatial.Grpc.1.0.0.nupkg"
        NugetPackageTests.write_package(self.local)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_missing_coordinates_are_reported_without_false_success(self) -> None:
        original_download = check_public_registry.download
        check_public_registry.download = lambda *args, **kwargs: False
        try:
            result = check_public_registry.probe(
                root=self.root,
                version="1.0.0",
                local_nuget=self.local,
                download_dir=self.root / "downloads",
                bsr_ref="v1.0.0",
                attempts=1,
                delay_seconds=0,
                require_existing=False,
            )
            self.assertEqual("missing", result["bsr"]["state"])
            self.assertEqual("missing", result["nuget"]["state"])
        finally:
            check_public_registry.download = original_download

    def test_required_missing_coordinate_fails_closed(self) -> None:
        original_download = check_public_registry.download
        check_public_registry.download = lambda *args, **kwargs: False
        try:
            with self.assertRaisesRegex(
                check_public_registry.RegistryError, "required BSR coordinate"
            ):
                check_public_registry.probe(
                    root=self.root,
                    version="1.0.0",
                    local_nuget=self.local,
                    download_dir=self.root / "downloads",
                    bsr_ref="a" * 32,
                    attempts=1,
                    delay_seconds=0,
                    require_existing=True,
                )
        finally:
            check_public_registry.download = original_download


class ReleaseWorkflowContractTests(unittest.TestCase):
    def test_release_actions_are_pinned_to_annotated_commit_shas(self) -> None:
        workflow = (ROOT / ".github/workflows/publish-dotnet-protocol.yml").read_text(
            encoding="utf-8"
        )
        uses = re.findall(r"^\s*uses:\s+(\S+)(?:\s+#\s+(\S+))?\s*$", workflow, re.MULTILINE)

        self.assertGreater(len(uses), 0)
        for action, version in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")
                self.assertRegex(version or "", r"^v\d+\.\d+\.\d+$")

    def test_publication_is_single_tag_driven_fail_closed_transaction(self) -> None:
        workflow = (ROOT / ".github/workflows/publish-dotnet-protocol.yml").read_text(
            encoding="utf-8"
        )
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn('- "v*"', workflow)
        self.assertNotIn("geospatial-grpc-v*", workflow)
        self.assertIn("workflow_dispatch never publishes", workflow)
        self.assertIn("BUF_TOKEN is required; refusing a partial release", workflow)
        self.assertIn("NUGET_API_KEY is required; refusing a partial release", workflow)
        self.assertIn("Geospatial.Grpc.${VERSION}.snupkg", workflow)
        self.assertIn("check_public_registry.py", workflow)
        self.assertIn("clean_public_consumption.sh", workflow)
        self.assertIn("release-receipt.json", workflow)
        self.assertIn("SHA256SUMS", workflow)
        self.assertNotIn("Publish to Buf Registry", ci)
        self.assertNotIn("BUF_TOKEN is not configured; skipping", ci)


if __name__ == "__main__":
    unittest.main()
