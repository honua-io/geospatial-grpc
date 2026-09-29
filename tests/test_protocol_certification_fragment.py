import argparse
import base64
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_protocol_certification_fragment.py"
SPEC = importlib.util.spec_from_file_location("fragment", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

GOVERNED_CLIENT_VERSION = "source@73fc882b1ae00d0a4a348aeadfba9f48b1a0317c"
RELEASE_ROOT = Path(os.environ.get("HONUA_RELEASE_ROOT", "/home/mike/honua-io/honua-release"))
EVIDENCE_ROOT = Path(os.environ.get("HONUA_EVIDENCE_ROOT", "/home/mike/honua-io/honua-evidence"))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@contextmanager
def patched_catalog(mutate):
    original = MODULE.CATALOG
    document = json.loads(original.read_text())
    mutate(document)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "catalog.json"
        path.write_text(json.dumps(document))
        MODULE.CATALOG = path
        try:
            yield document
        finally:
            MODULE.CATALOG = original


class FragmentTests(unittest.TestCase):
    def build(self, reports=(), **overrides):
        args = argparse.Namespace(
            report=list(reports), channel_target="http://localhost:8081",
            server_image="ghcr.io/honua-io/honua-server@sha256:" + "c" * 64,
            server_source_sha="b" * 40, image_source_revision="b" * 40,
            producer_source_sha="a" * 40, candidate_cut="2026-08-26T00:00:00Z",
            started_at="2026-08-26T00:00:00Z", completed_at="2026-08-26T00:01:00Z",
        )
        vars(args).update(overrides)
        return MODULE.build_fragment(args)

    def test_materializes_exact_release_denominator_and_truthful_identity(self):
        fragment = self.build()
        self.assertEqual(240, len(fragment["observations"]))
        for lane in MODULE.CLIENT_IDS:
            self.assertEqual(80, sum(o["runner_lane"] == lane for o in fragment["observations"]))
        for observation in fragment["observations"]:
            self.assertEqual("skip", observation["result"])
            self.assertEqual(observation["canonical_client"], observation["client_id"])
            self.assertEqual(observation["client_id"], observation["performed_by"])
            self.assertEqual([], observation["exercised_capabilities"])
            parsed = urlsplit(observation["request_url"])
            self.assertEqual("http", parsed.scheme)
            self.assertEqual("localhost:8081", parsed.netloc)
            self.assertTrue(parsed.path.startswith("/geospatial.v1."))
        self.assertEqual("red", fragment["client_rollup"]["state"])
        self.assertEqual(
            {"grpc-dotnet": "unpublished", "grpc-python": "unpublished", "grpc-typescript": "unpublished"},
            fragment["client_rollup"]["client_states"],
        )
        catalog = json.loads(MODULE.CATALOG.read_text())
        for observation in fragment["observations"]:
            self.assertEqual(GOVERNED_CLIENT_VERSION, observation["client_version"])
            self.assertEqual(catalog["contract_revision"], observation["contract_revision"])
            self.assertEqual(catalog["fixture_revision"], observation["fixture_revision"])
        self.assertFalse(fragment["client_rollup"]["all_claimed_clients_executed"])
        self.assertFalse(fragment["client_rollup"]["all_claimed_cells_passed"])
        self.assertIsNone(fragment["client_rollup"]["claim_narrowing_decision"])
        python = next(o for o in fragment["observations"] if o["runner_lane"] == "grpc-python")
        self.assertEqual("unpublished", python["publication_state"])
        self.assertEqual("skip", python["result"])

    def test_executed_positive_result_skips_observation_until_every_facet_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "dotnet.json"
            report.write_text(json.dumps({
                "runner_lane": "grpc-dotnet",
                "package": "Geospatial.Grpc",
                "package_version": GOVERNED_CLIENT_VERSION,
                "package_source": "https://api.nuget.org/v3/index.json",
                "operations": {"FeatureService/QueryFeatures": {"result": "pass"}},
            }))
            fragment = self.build([report])
        observation = next(o for o in fragment["observations"] if o["runner_lane"] == "grpc-dotnet" and o["operation"] == "FeatureService/QueryFeatures")
        receipt = observation["evidence_receipt"]
        self.assertEqual("skip", observation["result"])
        self.assertIn("negative", observation["skip_reason"])
        self.assertIn("positive execution pass", observation["skip_reason"])
        self.assertEqual([], observation["exercised_capabilities"])
        self.assertIsNone(receipt)
        self.assertIsNone(observation["evidence_uri"])
        self.assertIsNone(observation["evidence_digest"])
        self.assertIsNone(observation["facet_results"])
        self.assertFalse(any(o["result"] == "pass" for o in fragment["observations"]))

    def test_failed_response_comparison_remains_truthful_skip_until_every_facet_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "dotnet.json"
            report.write_text(json.dumps({
                "runner_lane": "grpc-dotnet",
                "package": "Geospatial.Grpc",
                "package_version": GOVERNED_CLIENT_VERSION,
                "package_source": "https://api.nuget.org/v3/index.json",
                "operations": {"FeatureService/QueryFeatures": {
                    "result": "fail", "reason": "Canonical response mismatch at $.features[0].id",
                }},
            }))
            fragment = self.build([report])
        observation = next(o for o in fragment["observations"] if o["runner_lane"] == "grpc-dotnet" and o["operation"] == "FeatureService/QueryFeatures")
        self.assertEqual("skip", observation["result"])
        self.assertIn("positive execution fail", observation["skip_reason"])
        self.assertIn("$.features[0].id", observation["skip_reason"])
        self.assertIsNone(observation["evidence_uri"])
        self.assertIsNone(observation["evidence_digest"])
        self.assertIsNone(observation["evidence_receipt"])
        self.assertIsNone(observation["facet_results"])
        self.assertEqual([], observation["exercised_capabilities"])

        self.assertEqual([{
            "runner_lane": "grpc-dotnet", "operation": "FeatureService/QueryFeatures",
            "reason": "Canonical response mismatch at $.features[0].id",
        }], fragment["execution_failures"])
        self.assertIn("$.features[0].id", MODULE.certification_errors(fragment, "pr")[0])

    def test_complete_facets_emit_a_v2_receipt_bound_to_the_federation_revision(self):
        def publish_dotnet(document):
            for client in document["clients"]:
                if client["client_lane"] == "grpc-dotnet":
                    client["publication_state"] = "published"
        with patched_catalog(publish_dotnet), tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "dotnet.json"
            report.write_text(json.dumps({
                "runner_lane": "grpc-dotnet",
                "package": "Geospatial.Grpc",
                "package_version": GOVERNED_CLIENT_VERSION,
                "package_source": "https://api.nuget.org/v3/index.json",
                "operations": {"FeatureService/QueryFeatures": {
                    "result": "pass",
                    "facet_results": {
                        "positive": "pass", "negative": "pass", "media-schema": "pass",
                    },
                }},
            }))
            fragment = self.build([report])
        observation = next(o for o in fragment["observations"] if o["runner_lane"] == "grpc-dotnet" and o["operation"] == "FeatureService/QueryFeatures")
        self.assertEqual("pass", observation["result"])
        self.assertIsNone(observation["skip_reason"])
        receipt = observation["evidence_receipt"]
        self.assertEqual("honua.certification-evidence-receipt/v2", receipt["schema"])
        self.assertEqual("supported", receipt["identity"]["maturity"])
        self.assertEqual("nightly", receipt["identity"]["required_tier"])
        self.assertEqual(
            json.loads(MODULE.CATALOG.read_text())["requirements_revision"],
            receipt["identity"]["requirements_revision"],
        )
        self.assertEqual(
            {"positive", "negative", "media-schema"},
            set(observation["exercised_capabilities"]),
        )
        # Compute the expected receipt digest independently of the producer helper.
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        self.assertEqual(digest, observation["evidence_digest"])
        payload = json.loads(base64.b64decode(receipt["payload_base64"], validate=True))
        report = json.loads(base64.b64decode(payload[0]["content_base64"], validate=True))
        self.assertEqual("pass", report["operations"]["FeatureService/QueryFeatures"]["result"])

    def test_release_rejects_missing_cells_but_pr_can_emit_bounded_nonpasses(self):
        fragment = self.build()
        self.assertEqual([], MODULE.certification_errors(fragment, "pr"))
        for tier in ("nightly", "release"):
            self.assertEqual([f"{tier} certification has 240 non-passing required cells"],
                             MODULE.certification_errors(fragment, tier))

    def test_rejects_floating_image_and_source_mismatch(self):
        with self.assertRaisesRegex(ValueError, "digest-addressed"):
            self.build(server_image="ghcr.io/honua-io/honua-server:latest")
        with self.assertRaisesRegex(ValueError, "equal server source SHA"):
            self.build(image_source_revision="d" * 40)

    def test_rejects_invalid_stale_and_reversed_execution_times(self):
        for changes, reason in (
            ({"candidate_cut": "invalid"}, "timezone-aware"),
            ({"started_at": "2026-08-26T00:00:00"}, "timezone-aware"),
            ({"started_at": "2026-08-25T00:00:00Z"}, "predates candidate cut"),
            ({"completed_at": "2026-08-25T00:00:00Z"}, "precedes started_at"),
            ({"completed_at": "2099-01-01T00:00:00Z"}, "in the future"),
            ({"tier": "release"}, "older than 24 hours"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, reason):
                self.build(**changes)

    def test_unknown_operation_cannot_hide_executed_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps({"runner_lane": "grpc-dotnet", "operations": {
                "FeatureService/Typo": {"result": "fail"},
            }}))
            with self.assertRaisesRegex(ValueError, "unknown operations"):
                self.build([path])

    def test_release_rejects_relabeling_old_or_wrong_target_reports(self):
        now = datetime.now(timezone.utc)
        cut, start, end = [(now - timedelta(minutes=i)).isoformat() for i in (3, 2, 1)]
        report = {
            "runner_lane": "grpc-dotnet",
            "package_version": GOVERNED_CLIENT_VERSION,
            "operations": {"FeatureService/QueryFeatures": {"result": "fail"}},
            "execution_identity": {
                "channel_target": "http://localhost:8081",
                "server_image": "ghcr.io/honua-io/honua-server@sha256:" + "c" * 64,
                "server_source_sha": "b" * 40,
                "fixture_revision": json.loads(MODULE.CATALOG.read_text())["fixture_revision"],
            },
            "started_at": (now - timedelta(days=2)).isoformat(),
            "completed_at": (now - timedelta(days=2)).isoformat(),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            def build_report():
                path.write_text(json.dumps(report))
                return self.build([path], tier="release", candidate_cut=cut, started_at=start, completed_at=end)
            with self.assertRaisesRegex(ValueError, "predates candidate cut"):
                build_report()
            report.update(started_at=cut, completed_at=end)
            with self.assertRaisesRegex(ValueError, "outside this run"):
                build_report()
            report.update(started_at=start)
            report["execution_identity"]["channel_target"] = "https://other.example.test"
            with self.assertRaisesRegex(ValueError, "execution identity mismatch"):
                build_report()

    def test_cli_writes_evidence_and_returns_failure_for_executed_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            output = Path(directory) / "fragment.json"
            path.write_text(json.dumps({
                "runner_lane": "grpc-dotnet", "package": "Geospatial.Grpc", "package_version": GOVERNED_CLIENT_VERSION,
                "package_source": "https://api.nuget.org/v3/index.json",
                "operations": {"FeatureService/QueryFeatures": {
                    "result": "fail", "reason": "Canonical response mismatch at $.features[0].geometry.point.x",
                }},
            }))
            command = [sys.executable, str(SCRIPT), "--report", str(path), "--output", str(output),
                       "--channel-target", "http://localhost:8081",
                       "--server-image", "ghcr.io/honua-io/honua-server@sha256:" + "c" * 64,
                       "--server-source-sha", "b" * 40, "--image-source-revision", "b" * 40,
                       "--producer-source-sha", "a" * 40,
                       "--candidate-cut", "2026-08-26T00:00:00Z", "--started-at", "2026-08-26T00:00:00Z"]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("grpc-dotnet/FeatureService/QueryFeatures", result.stderr)
            self.assertIn("geometry.point.x", result.stderr)
            fragment = json.loads(output.read_text())
            self.assertEqual(240, len(fragment["observations"]))
            self.assertEqual(1, len(fragment["execution_failures"]))

    def test_recorded_narrowing_url_does_not_waive_failed_required_cells(self):
        original = MODULE.CATALOG
        with tempfile.TemporaryDirectory() as directory:
            catalog = json.loads(original.read_text())
            catalog["claim_narrowing_decision"] = "https://github.com/honua-io/geospatial-grpc/issues/88#issuecomment-1"
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog))
            MODULE.CATALOG = path
            try:
                fragment = self.build()
                self.assertEqual("red", fragment["client_rollup"]["state"])
                self.assertTrue(MODULE.certification_errors(fragment, "release"))
            finally:
                MODULE.CATALOG = original

    def test_rejects_partial_reported_facets(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "dotnet.json"
            report.write_text(json.dumps({
                "runner_lane": "grpc-dotnet",
                "package": "Geospatial.Grpc",
                "package_version": GOVERNED_CLIENT_VERSION,
                "package_source": "https://api.nuget.org/v3/index.json",
                "operations": {"FeatureService/QueryFeatures": {
                    "result": "pass", "facet_results": {"positive": "pass"},
                }},
            }))
            with self.assertRaisesRegex(ValueError, "must cover every governed facet"):
                self.build([report])

    def test_rejects_non_public_or_wrong_package_identity(self):
        def declare_nuget(document):
            for client in document["clients"]:
                if client["client_lane"] == "grpc-dotnet":
                    client["publication_state"] = "published"
                    client["client_version"] = "1.0.0"
                    client["package"] = "Geospatial.Grpc"
                    client["package_source"] = "https://api.nuget.org/v3/index.json"
        with patched_catalog(declare_nuget), tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "dotnet.json"
            report.write_text(json.dumps({
                "runner_lane": "grpc-dotnet",
                "package": "Geospatial.Grpc",
                "package_version": "1.0.0",
                "package_source": "https://nuget.pkg.github.com/honua-io/index.json",
                "operations": {"FeatureService/QueryFeatures": {"result": "pass"}},
            }))
            with self.assertRaisesRegex(ValueError, "published package identity mismatch"):
                self.build([report])

    def test_promoted_package_bytes_do_not_satisfy_the_governed_cell(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "dotnet.json"
            report.write_text(json.dumps({
                "runner_lane": "grpc-dotnet",
                "package": "Geospatial.Grpc",
                "package_version": "1.0.0",
                "package_source": "https://api.nuget.org/v3/index.json",
                "operations": {"FeatureService/QueryFeatures": {
                    "result": "fail",
                    "reason": "Canonical response mismatch at $.features[0].id",
                }},
            }))
            fragment = self.build([report])
        observation = next(
            item for item in fragment["observations"]
            if item["runner_lane"] == "grpc-dotnet" and item["operation"] == "FeatureService/QueryFeatures"
        )
        self.assertEqual("skip", observation["result"])
        self.assertEqual(GOVERNED_CLIENT_VERSION, observation["client_version"])
        self.assertIsNone(observation["evidence_receipt"])
        self.assertIn("1.0.0", observation["skip_reason"])
        self.assertIn(GOVERNED_CLIENT_VERSION, observation["skip_reason"])
        self.assertIn("$.features[0].id", observation["skip_reason"])
        self.assertEqual([{
            "runner_lane": "grpc-dotnet",
            "operation": "FeatureService/QueryFeatures",
            "reason": "Canonical response mismatch at $.features[0].id",
        }], fragment["execution_failures"])
        untouched = next(
            item for item in fragment["observations"]
            if item["runner_lane"] == "grpc-dotnet" and item["operation"] == "FeatureService/ApplyEdits"
        )
        self.assertIn("not executed against the governed client", untouched["skip_reason"])

    def test_rejects_placeholder_or_floating_identity(self):
        with self.assertRaisesRegex(ValueError, "absolute HTTP"):
            args = argparse.Namespace(**{**vars(argparse.Namespace(
                report=[], channel_target="grpc-server:8081", server_image="x@sha256:" + "c"*64,
                server_source_sha="b"*40, image_source_revision="b"*40, producer_source_sha="a"*40,
                candidate_cut="x", started_at="x", completed_at="x"))})
            MODULE.build_fragment(args)

    def test_rejects_unrecorded_claim_narrowing(self):
        original = MODULE.CATALOG
        with tempfile.TemporaryDirectory() as directory:
            catalog = json.loads(original.read_text())
            catalog["claim_narrowing_decision"] = "https://example.invalid/decision"
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog))
            MODULE.CATALOG = path
            try:
                with self.assertRaisesRegex(ValueError, "recorded issue #88"):
                    self.build()
            finally:
                MODULE.CATALOG = original

    def test_python_and_typescript_executions_are_attributed_by_lane(self):
        with tempfile.TemporaryDirectory() as directory:
            reports = []
            for lane, package, source in (
                ("grpc-python", "geospatial-grpc", "https://pypi.org/pypi/geospatial-grpc/json"),
                ("grpc-typescript", "@honua/geospatial-grpc",
                 "https://registry.npmjs.org/@honua/geospatial-grpc"),
            ):
                report = Path(directory) / f"{lane}.json"
                report.write_text(json.dumps({
                    "runner_lane": lane,
                    "package": package,
                    "package_version": "1.0.0",
                    "package_source": source,
                    "operations": {
                        "FeatureService/QueryFeatures": {"result": "pass"},
                        "FormService/GetFormDefinition": {
                            "result": "fail",
                            "reason": f"{lane}: StatusCode.UNIMPLEMENTED",
                        },
                    },
                }))
                reports.append(report)
            fragment = self.build(reports)
        self.assertEqual([
            {"runner_lane": "grpc-python", "operation": "FormService/GetFormDefinition",
             "reason": "grpc-python: StatusCode.UNIMPLEMENTED"},
            {"runner_lane": "grpc-typescript", "operation": "FormService/GetFormDefinition",
             "reason": "grpc-typescript: StatusCode.UNIMPLEMENTED"},
        ], fragment["execution_failures"])
        for lane in ("grpc-python", "grpc-typescript"):
            cells = [o for o in fragment["observations"] if o["runner_lane"] == lane]
            self.assertEqual(80, len(cells))
            # Promoted 1.0.0 bytes executed, but they are not the governed pin:
            # every governed cell stays an evidence-free skip that names why.
            self.assertEqual({"skip"}, {o["result"] for o in cells})
            self.assertTrue(all(o["evidence_receipt"] is None for o in cells))
            query = next(o for o in cells if o["operation"] == "FeatureService/QueryFeatures")
            self.assertIn("positive execution pass", query["skip_reason"])
            self.assertIn(GOVERNED_CLIENT_VERSION, query["skip_reason"])
        self.assertEqual("red", fragment["client_rollup"]["state"])

    def test_skip_fragment_is_accepted_by_evidence_and_enforced_by_release_gate(self):
        requirements_path = RELEASE_ROOT / "certification/protocol-certification-requirements.v1.json"
        aggregate_path = EVIDENCE_ROOT / "scripts/aggregate-certification.py"
        gate_path = RELEASE_ROOT / "tools/check_protocol_certification.py"
        if not (requirements_path.is_file() and aggregate_path.is_file() and gate_path.is_file()):
            self.skipTest("honua-release and honua-evidence checkouts are required")
        requirements = json.loads(requirements_path.read_text())
        rows = [
            row for row in requirements["requirements"]
            if row["surface"] == "grpc" and str(row["canonical_client"]).startswith("Generated gRPC")
        ]
        self.assertEqual(240, len(rows))
        catalog = json.loads(MODULE.CATALOG.read_text())
        for row in rows:
            client = next(item for item in catalog["clients"] if item["client_lane"] == row["client_lane"])
            self.assertEqual(client["client_version"], row["client_version"])
            self.assertEqual(client["canonical_client"], row["canonical_client"])
            self.assertEqual(catalog["contract_revision"], row["contract_revision"])
            self.assertEqual(catalog["fixture_revision"], row["fixture_revision"])
        source_revisions = requirements["source_revisions"]
        server_sha = source_revisions["server"]["commit"]
        producer_sha = source_revisions["geospatial-grpc"]["commit"]
        image = "sha256:" + "c" * 64
        cut = "2026-08-26T00:00:00Z"
        fragment = self.build(
            server_source_sha=server_sha,
            image_source_revision=server_sha,
            producer_source_sha=producer_sha,
            server_image="ghcr.io/honua-io/honua-server@" + image,
            candidate_cut=cut,
            started_at=cut,
            completed_at="2026-08-26T00:01:00Z",
        )
        fetch = load_module(
            "honua_fetch_certification_producers",
            EVIDENCE_ROOT / "scripts/fetch-certification-producers.py",
        )
        fetch.validate_fragment_producer(fragment, "geospatial-grpc", producer_sha, "honua-io/geospatial-grpc")
        aggregate = load_module("honua_aggregate_certification", aggregate_path)
        with tempfile.TemporaryDirectory() as directory:
            fragment_path = Path(directory) / "protocol-certification-fragment.json"
            fragment_path.write_text(json.dumps(fragment))
            loaded = aggregate.load_fragments(Path(directory))
        self.assertEqual(1, len(loaded))
        candidate = {
            "source_sha": server_sha,
            "image_digest": image,
            "cut_at": cut,
        }
        ledger = aggregate.build_ledger(
            requirements["revision"],
            "b" * 40,
            True,
            rows,
            loaded,
            candidate,
            now=datetime(2026, 9, 26, tzinfo=timezone.utc),
        )
        self.assertEqual(240, len(ledger["cells"]))
        for cell in ledger["cells"]:
            self.assertEqual("skip", cell["result"])
            self.assertNotEqual("no producer evidence for required certification cell", cell["skip_reason"])
            self.assertEqual(producer_sha, cell["producer_source_sha"])
            self.assertIsNone(cell["evidence_receipt"])
        gate = load_module("honua_check_protocol_certification", gate_path)
        filtered = dict(requirements)
        filtered["requirements"] = rows
        report = gate.evaluate(
            ledger,
            "release",
            expected_source_sha=server_sha,
            expected_image_digest=image,
            expected_cut_at=cut,
            expected_component_source_shas={
                name: source_revisions[name]["commit"] for name in gate.FROZEN_RELEASE_SOURCES
            },
            expected_client_versions={
                "sdk-js": "0.0.0",
                "sdk-python": "0.0.0",
                "sdk-dotnet": "0.0.0",
            },
            now=datetime(2026, 9, 26, tzinfo=timezone.utc),
            requirements=filtered,
        )
        self.assertEqual("fail", report["overall_status"])
        self.assertEqual(240, report["required_cells"])
        self.assertTrue(any("expected 'pass'" in finding["why"] for finding in report["findings"]))
        self.assertFalse(any("do not resolve" in finding["why"] for finding in report["findings"]))


if __name__ == "__main__":
    unittest.main()
