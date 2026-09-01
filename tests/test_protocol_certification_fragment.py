import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_protocol_certification_fragment.py"
SPEC = importlib.util.spec_from_file_location("fragment", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class FragmentTests(unittest.TestCase):
    def build(self, reports=()):
        args = argparse.Namespace(
            report=list(reports), channel_target="http://localhost:8081",
            server_image="ghcr.io/honua-io/honua-server@sha256:" + "c" * 64,
            server_source_sha="b" * 40, image_source_revision="b" * 40,
            producer_source_sha="a" * 40, candidate_cut="2026-08-26T00:00:00Z",
            started_at="2026-08-26T00:00:00Z", completed_at="2026-08-26T00:01:00Z",
        )
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
        self.assertEqual("incomplete", fragment["client_rollup"]["client_states"]["grpc-dotnet"])
        self.assertEqual("unpublished", fragment["client_rollup"]["client_states"]["grpc-python"])
        self.assertEqual("unpublished", fragment["client_rollup"]["client_states"]["grpc-typescript"])
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
                "package_version": "1.0.0",
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
                "package_version": "1.0.0",
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

    def test_complete_facets_emit_a_v2_receipt_bound_to_the_federation_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "dotnet.json"
            report.write_text(json.dumps({
                "runner_lane": "grpc-dotnet",
                "package": "Geospatial.Grpc",
                "package_version": "1.0.0",
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
        self.assertEqual("2026-08-29-complete.11", receipt["identity"]["requirements_revision"])
        self.assertEqual(
            {"positive", "negative", "media-schema"},
            set(observation["exercised_capabilities"]),
        )

    def test_rejects_partial_reported_facets(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "dotnet.json"
            report.write_text(json.dumps({
                "runner_lane": "grpc-dotnet",
                "package": "Geospatial.Grpc",
                "package_version": "1.0.0",
                "package_source": "https://api.nuget.org/v3/index.json",
                "operations": {"FeatureService/QueryFeatures": {
                    "result": "pass", "facet_results": {"positive": "pass"},
                }},
            }))
            with self.assertRaisesRegex(ValueError, "must cover every governed facet"):
                self.build([report])

    def test_rejects_non_public_or_wrong_package_identity(self):
        with tempfile.TemporaryDirectory() as directory:
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


if __name__ == "__main__":
    unittest.main()
