import argparse
import base64
import hashlib
import importlib.util
import json
import tempfile
import unittest
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_protocol_certification_fragment.py"
SPEC = importlib.util.spec_from_file_location("fragment", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


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

        self.assertEqual([{
            "runner_lane": "grpc-dotnet", "operation": "FeatureService/QueryFeatures",
            "reason": "Canonical response mismatch at $.features[0].id",
        }], fragment["execution_failures"])
        self.assertIn("$.features[0].id", MODULE.certification_errors(fragment, "pr")[0])

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
            "runner_lane": "grpc-dotnet", "operations": {"FeatureService/QueryFeatures": {"result": "fail"}},
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
                "runner_lane": "grpc-dotnet", "package": "Geospatial.Grpc", "package_version": "1.0.0",
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
