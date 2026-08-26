import argparse
import hashlib
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

    def test_executed_result_has_digest_bound_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "dotnet.json"
            report.write_text(json.dumps({
                "runner_lane": "grpc-dotnet",
                "operations": {"FeatureService/QueryFeatures": {"result": "pass"}},
            }))
            fragment = self.build([report])
        observation = next(o for o in fragment["observations"] if o["runner_lane"] == "grpc-dotnet" and o["operation"] == "FeatureService/QueryFeatures")
        receipt = observation["evidence_receipt"]
        expected = "sha256:" + hashlib.sha256(MODULE.canonical_bytes(receipt)).hexdigest()
        self.assertEqual("pass", observation["result"])
        self.assertEqual(observation["scenario_facets"], observation["exercised_capabilities"])
        self.assertEqual(expected, observation["evidence_digest"])
        self.assertTrue(all(v["evidence_digest"] == expected for v in observation["facet_results"].values()))

    def test_rejects_placeholder_or_floating_identity(self):
        with self.assertRaisesRegex(ValueError, "absolute HTTP"):
            args = argparse.Namespace(**{**vars(argparse.Namespace(
                report=[], channel_target="grpc-server:8081", server_image="x@sha256:" + "c"*64,
                server_source_sha="b"*40, image_source_revision="b"*40, producer_source_sha="a"*40,
                candidate_cut="x", started_at="x", completed_at="x"))})
            MODULE.build_fragment(args)


if __name__ == "__main__":
    unittest.main()
