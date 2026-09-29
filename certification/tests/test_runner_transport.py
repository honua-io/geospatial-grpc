"""Exercise installed .NET, Python and TypeScript client bytes against an
independent loopback gRPC oracle.

This is a producer regression, not Honua Server release certification. The
oracle writes protobuf wire fields directly; it never uses generated bindings
or records the runner's output to construct an expected response.
"""
import json
import os
from pathlib import Path
import struct
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

import grpc

ROOT = Path(__file__).resolve().parents[2]
DOTNET_RUNNER = ROOT / "certification/dotnet/bin/Release/net10.0/GrpcCertificationRunner.dll"
PYTHON_RUNNER = ROOT / "certification/python/runner.py"
TYPESCRIPT_RUNNER = ROOT / "certification/typescript/runner.mjs"
TYPESCRIPT_MODULES = ROOT / "certification/typescript/node_modules/@honua/geospatial-grpc"
SCENARIOS = json.loads((ROOT / "certification/scenarios.v1.json").read_text(encoding="utf-8"))["scenarios"]
CALLS = {scenario["operation"]: scenario for scenario in SCENARIOS}
# Requests that carry a captured id, as the real fixtures do.
BOUND_REQUESTS = {
    "ProcessService/GetJob": {"jobId": "{{capture:submitted_job}}"},
    "ProcessService/GetJobResult": {"jobId": "{{capture:submitted_job}}"},
    "ProcessService/CancelJob": {"jobId": "{{capture:job_to_cancel}}"},
    "SpecService/CancelApply": {"jobId": "{{capture:applied_spec}}"},
}
# Runners execute each scenario's negative case before its positive call, so
# the oracle rejects the first call of those operations (ApplyEdits keeps its
# explicit marker, because its read-back uses QueryFeatures).
FIRST_CALL_NEGATIVE = {
    name for name, scenario in CALLS.items()
    if "negative" in scenario and name != "FeatureService/ApplyEdits"
}
STREAMING = {name for name, scenario in CALLS.items() if scenario["kind"] == "server_stream"}
# Server-assigned ids the oracle returns so captures resolve (field 1 of
# SubmitJobResponse; field 10 of ApplySpecEvent).
CAPTURED_IDS = {
    "ProcessService/SubmitJob": b"\x0a\x0aoracle-job",
    "SpecService/ApplySpec": b"\x52\x0coracle-apply",
}


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result) + bytes([value])


def message(field, payload):
    return varint((field << 3) | 2) + varint(len(payload)) + payload


def query_response(*, x=-157.5, y=21.25, z=0.0, m=12.5, wkid=4326, null_value=True, identifier=42,
                   attribute_extra=b""):
    # QueryFeaturesResponse.features=5 -> Feature.geometry=3 -> Geometry.point=1.
    # Point x/y/z/m are fixed64 fields 1/2/3/4; optional zero Z must stay present.
    point = b"".join(varint((field << 3) | 1) + struct.pack("<d", value)
                     for field, value in ((1, x), (2, y), (3, z), (4, m)) if value is not None)
    feature = b"\x08" + varint(identifier) + message(3, message(1, point))
    # AttributeValue.null_value is oneof field 9, explicitly encoded even at 0.
    attribute = (b"\x48\x00" if null_value else b"\x21" + struct.pack("<d", 0.0)) + attribute_extra
    feature += message(2, message(1, b"height") + message(2, attribute))
    return b"\x10\x01" + message(3, b"\x08" + varint(wkid)) + message(5, feature)


def edit_result(object_id, success=True):
    # EditResult.object_id=1 (int64 varint, omitted at 0), success=2 (bool).
    payload = (b"\x08" + varint(object_id) if object_id else b"") + (b"\x10\x01" if success else b"")
    return payload


def apply_edits_response(*, add_id=555, update_id=42):
    # ApplyEditsResponse.add_results=1, update_results=2.
    return message(1, edit_result(add_id)) + message(2, edit_result(update_id))


# The fixture's expected add id deliberately differs from the oracle's 555:
# addResults[*].objectId is server-assigned (certification/server-assigned-fields.v1.json).
EXPECTED_APPLY_EDITS = {
    "addResults": [{"objectId": "101", "success": True}],
    "updateResults": [{"objectId": "42", "success": True}],
}
NEGATIVE_MARKER = "missing-target"
VERIFY_MARKER = "rejected-batch-read-back"


EXPECTED_QUERY = {
    "geometryType": "GEOMETRY_TYPE_POINT",
    "spatialReference": {"wkid": 4326},
    "features": [{"id": "42", "attributes": {"height": {"nullValue": "NULL_VALUE"}},
                  "geometry": {"point": {"x": -157.5, "y": 21.25, "z": 0, "m": 12.5}}}],
}


class RunnerTransportContract:
    """Shared oracle contract; each subclass binds one installed-client runner."""

    lane = ""

    def command(self, target, fixtures, report_path):
        raise NotImplementedError

    def execute(self, response=None, abort=False, edits_response=None,
                negative_status=grpc.StatusCode.NOT_FOUND, verify_response=None, unimplemented=(), captured=None, cancel_races=0,
                negative_first_call=True):
        requests = {}
        captured_ids = CAPTURED_IDS if captured is None else captured
        races = {"left": cancel_races}
        seen = set()
        server = grpc.server(ThreadPoolExecutor(max_workers=2))

        def handler(operation):
            def reject_negative(context):
                if negative_first_call and operation in FIRST_CALL_NEGATIVE and operation not in seen:
                    seen.add(operation)
                    context.abort(grpc.StatusCode.NOT_FOUND, "oracle negative case")
                seen.add(operation)

            def invoke_stream(request, context):
                reject_negative(context)
                requests[operation] = request
                if operation in unimplemented:
                    context.abort(grpc.StatusCode.UNIMPLEMENTED, "Service is unimplemented.")
                yield captured_ids.get(operation, b"")

            def invoke(request, context):
                if VERIFY_MARKER.encode() not in request:
                    reject_negative(context)
                if VERIFY_MARKER.encode() not in request:
                    requests[operation] = request
                if operation in unimplemented:
                    context.abort(grpc.StatusCode.UNIMPLEMENTED, "Service is unimplemented.")
                if operation == "ProcessService/CancelJob" and races["left"] > 0:
                    races["left"] -= 1
                    context.abort(grpc.StatusCode.FAILED_PRECONDITION, "job reached terminal state before cancellation")
                if operation == "FeatureService/QueryFeatures" and VERIFY_MARKER.encode() in request:
                    requests["FeatureService/QueryFeatures#read-back"] = request
                    return query_response() if verify_response is None else verify_response
                if operation == "FeatureService/QueryFeatures":
                    if abort:
                        context.abort(grpc.StatusCode.UNAVAILABLE, "injected unavailable")
                    return query_response() if response is None else response
                if operation == "FeatureService/ApplyEdits":
                    if NEGATIVE_MARKER.encode() in request:
                        requests["FeatureService/ApplyEdits#negative"] = request
                        if negative_status is not None:
                            context.abort(negative_status, "feature 8 was not found")
                        return b""
                    return apply_edits_response() if edits_response is None else edits_response
                return captured_ids.get(operation, b"")
            if operation in STREAMING:
                return grpc.unary_stream_rpc_method_handler(invoke_stream)
            return grpc.unary_unary_rpc_method_handler(invoke)

        for operation in CALLS:
            service, method = operation.split("/")
            server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
                "geospatial.v1." + service, {method: handler(operation)}),))
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                fixtures = Path(directory)
                for operation, scenario in CALLS.items():
                    request = {"serviceId": "oracle"} if operation == "FeatureService/QueryFeatures" \
                        else BOUND_REQUESTS.get(operation, {})
                    expected = {"FeatureService/QueryFeatures": EXPECTED_QUERY,
                                "FeatureService/ApplyEdits": EXPECTED_APPLY_EDITS,
                                "ProcessService/SubmitJob": {"jobId": "fixture-job"},
                                "SpecService/ApplySpec": {"jobId": "fixture-apply"}}.get(operation, {})
                    (fixtures / scenario["request"]).write_text(json.dumps(request))
                    if operation in STREAMING:
                        (fixtures / f"{scenario['responses']}.1.json").write_text(json.dumps(expected))
                    else:
                        (fixtures / scenario["response"]).write_text(json.dumps(expected))
                    if "setup" in scenario:
                        (fixtures / scenario["setup"]["request"]).write_text(json.dumps({}))
                    if operation in FIRST_CALL_NEGATIVE:
                        (fixtures / scenario["negative"]["request"]).write_text(json.dumps({}))
                        (fixtures / scenario["negative"]["status"]).write_text(
                            json.dumps({"code": 5, "name": "NOT_FOUND"}))
                (fixtures / "feature_apply_edits_missing_target_request.json").write_text(
                    json.dumps({"serviceId": NEGATIVE_MARKER, "deletes": ["7", "8"]}))
                (fixtures / "feature_apply_edits_missing_target_status.json").write_text(
                    json.dumps({"code": 5, "name": "NOT_FOUND"}))
                (fixtures / "feature_apply_edits_missing_target_verify_request.json").write_text(
                    json.dumps({"serviceId": VERIFY_MARKER}))
                (fixtures / "feature_apply_edits_missing_target_verify_response.json").write_text(
                    json.dumps(EXPECTED_QUERY))
                report_path = fixtures / "report.json"
                completed = subprocess.run(
                    self.command(f"http://127.0.0.1:{port}", fixtures, report_path),
                    env={**os.environ, "HONUA_PROTOCOL_API_KEY": "oracle-test-key",
                         "HONUA_CERTIFICATION_POLL_TIMEOUT_SECONDS": "0"},
                    text=True, capture_output=True, timeout=120, check=False,
                )
                self.assertTrue(report_path.is_file(), completed.stderr)
                report = json.loads(report_path.read_text())
        finally:
            server.stop(0).wait()
        expected_requests = set(CALLS) | {"FeatureService/ApplyEdits#negative"}
        if negative_status == grpc.StatusCode.NOT_FOUND:
            expected_requests.add("FeatureService/QueryFeatures#read-back")
        if captured is None:
            self.assertEqual(expected_requests, set(requests))
        self.assertEqual(b"\x0a\x06oracle", requests["FeatureService/QueryFeatures"])
        if captured is None:
            # Captured ids are bound into the dependent requests.
            self.assertEqual(b"\x0a\x0aoracle-job", requests["ProcessService/CancelJob"])
            self.assertEqual(b"\x0a\x0aoracle-job", requests["ProcessService/GetJob"])
            self.assertEqual(b"\x0a\x0coracle-apply", requests["SpecService/CancelApply"])
        self.assertEqual(set(CALLS), set(report["operations"]))
        self.assertEqual(self.lane, report["runner_lane"])
        self.assertIsInstance(report["package_version"], str)
        return completed, report

    def test_matching_wire_values_pass_and_preserve_optional_zero_and_null(self):
        completed, report = self.execute()
        self.assertEqual(0, completed.returncode, report)
        self.assertEqual({"pass"}, {item["result"] for item in report["operations"].values()})

    def test_corrupted_values_fail_after_all_operations_and_report_are_retained(self):
        for change, divergence in (
            ({"x": 21.25, "y": -157.5}, "geometry.point.x"),
            ({"z": None}, "geometry.point.z"),
            ({"m": 13}, "geometry.point.m"),
            ({"wkid": 3857}, "spatialReference.wkid"),
            ({"null_value": False}, "attributes.height"),
            ({"identifier": 43}, "features[0].id"),
        ):
            with self.subTest(change=change):
                completed, report = self.execute(query_response(**change))
                self.assertEqual(1, completed.returncode, report)
                outcome = report["operations"]["FeatureService/QueryFeatures"]
                self.assertEqual("fail", outcome["result"])
                self.assertIn(divergence, outcome["reason"])
                self.assertEqual(len(CALLS) - 1, sum(item["result"] == "pass" for item in report["operations"].values()))

    def test_server_assigned_add_id_is_not_compared(self):
        # The oracle assigns 555; the fixture says 101. The path is listed as
        # server-assigned, so only its presence is required.
        completed, report = self.execute(edits_response=apply_edits_response(add_id=987654))
        self.assertEqual(0, completed.returncode, report)
        self.assertEqual("pass", report["operations"]["FeatureService/ApplyEdits"]["result"])

    def test_server_assigned_value_must_still_be_present(self):
        completed, report = self.execute(edits_response=apply_edits_response(add_id=0))
        self.assertEqual(1, completed.returncode, report)
        outcome = report["operations"]["FeatureService/ApplyEdits"]
        self.assertEqual("fail", outcome["result"])
        self.assertIn("addResults[0]", outcome["reason"])

    def test_client_supplied_edit_id_is_still_compared(self):
        completed, report = self.execute(edits_response=apply_edits_response(update_id=43))
        self.assertEqual(1, completed.returncode, report)
        outcome = report["operations"]["FeatureService/ApplyEdits"]
        self.assertEqual("fail", outcome["result"])
        self.assertIn("updateResults[0].objectId", outcome["reason"])

    def test_negative_batch_that_succeeds_fails_the_operation(self):
        completed, report = self.execute(negative_status=None)
        self.assertEqual(1, completed.returncode, report)
        outcome = report["operations"]["FeatureService/ApplyEdits"]
        self.assertEqual("fail", outcome["result"])
        self.assertIn("succeeded", outcome["reason"])
        self.assertEqual(len(CALLS) - 1, sum(item["result"] == "pass" for item in report["operations"].values()))

    def test_negative_batch_with_the_wrong_status_fails_the_operation(self):
        completed, report = self.execute(negative_status=grpc.StatusCode.INVALID_ARGUMENT)
        self.assertEqual(1, completed.returncode, report)
        outcome = report["operations"]["FeatureService/ApplyEdits"]
        self.assertEqual("fail", outcome["result"])
        self.assertIn("NOT_FOUND", outcome["reason"])

    def test_rejected_batch_that_changed_state_fails_the_operation(self):
        # The server returned NOT_FOUND but its read-back shows a changed feature.
        completed, report = self.execute(verify_response=query_response(identifier=43))
        self.assertEqual(1, completed.returncode, report)
        outcome = report["operations"]["FeatureService/ApplyEdits"]
        self.assertEqual("fail", outcome["result"])
        self.assertIn("does not match the unchanged state", outcome["reason"])
        self.assertIn("features[0].id", outcome["reason"])
        self.assertEqual(len(CALLS) - 1, sum(item["result"] == "pass" for item in report["operations"].values()))

    def test_excluded_operation_failure_is_reported_but_does_not_fail_the_lane(self):
        # FormService and ExecutePlan are excluded by the 2026.1 scope ruling (#88).
        completed, report = self.execute(
            unimplemented=("FormService/GetFormDefinition", "ProcessService/ExecutePlan"))
        self.assertEqual(0, completed.returncode, report)
        for operation in ("FormService/GetFormDefinition", "ProcessService/ExecutePlan"):
            self.assertEqual("fail", report["operations"][operation]["result"])
            self.assertIn("unimplemented", report["operations"][operation]["reason"].lower())

    def test_missing_captured_id_fails_the_dependent_scenarios(self):
        # SubmitJob returns no job id, so GetJob, GetJobResult and CancelJob cannot bind.
        completed, report = self.execute(captured={"SpecService/ApplySpec": CAPTURED_IDS["SpecService/ApplySpec"]})
        self.assertEqual(1, completed.returncode, report)
        self.assertEqual("fail", report["operations"]["ProcessService/SubmitJob"]["result"])
        for operation in ("ProcessService/GetJob", "ProcessService/GetJobResult"):
            self.assertIn("needs capture 'submitted_job'", report["operations"][operation]["reason"])
        self.assertIn("to capture as 'job_to_cancel'", report["operations"]["ProcessService/CancelJob"]["reason"])
        self.assertEqual("pass", report["operations"]["SpecService/CancelApply"]["result"])

    def test_cancel_setup_race_is_retried_with_a_fresh_job(self):
        completed, report = self.execute(cancel_races=2)
        self.assertEqual(0, completed.returncode, report)
        self.assertEqual("pass", report["operations"]["ProcessService/CancelJob"]["result"])

    def test_cancel_setup_race_that_persists_fails(self):
        completed, report = self.execute(cancel_races=3)
        self.assertEqual(1, completed.returncode, report)
        self.assertEqual("fail", report["operations"]["ProcessService/CancelJob"]["result"])
        self.assertIn("terminal state before cancellation", report["operations"]["ProcessService/CancelJob"]["reason"])

    def test_governed_scenarios_report_all_three_facets(self):
        completed, report = self.execute()
        self.assertEqual(0, completed.returncode, report)
        for operation, scenario in CALLS.items():
            if "negative" in scenario:
                self.assertEqual({"positive": "pass", "negative": "pass", "media-schema": "pass"},
                                 report["operations"][operation]["facet_results"], operation)

    def test_negative_case_that_succeeds_fails_only_the_negative_facet(self):
        completed, report = self.execute(negative_first_call=False)
        self.assertEqual(1, completed.returncode, report)
        outcome = report["operations"]["ProcessService/ValidatePlan"]
        self.assertEqual("fail", outcome["result"])
        self.assertEqual({"positive": "pass", "negative": "fail", "media-schema": "pass"}, outcome["facet_results"])
        self.assertIn("succeeded", outcome["reason"])

    def test_field_unknown_to_the_installed_schema_fails_media_schema(self):
        # Field 99 (varint) is not in QueryFeaturesResponse.
        completed, report = self.execute(query_response() + b"\xf8\x06\x01")
        self.assertEqual(1, completed.returncode, report)
        outcome = report["operations"]["FeatureService/QueryFeatures"]
        self.assertEqual({"positive": "pass", "negative": "pass", "media-schema": "fail"}, outcome["facet_results"])
        self.assertIn("unknown to the installed schema", outcome["reason"])

    def test_value_mismatch_fails_only_the_positive_facet(self):
        completed, report = self.execute(query_response(x=21.25, y=-157.5))
        self.assertEqual(1, completed.returncode, report)
        outcome = report["operations"]["FeatureService/QueryFeatures"]
        self.assertEqual({"positive": "fail", "negative": "pass", "media-schema": "pass"}, outcome["facet_results"])

    def test_unknown_field_inside_a_map_value_fails_media_schema(self):
        # Field 99 inside the AttributeValue held by Feature.attributes["height"].
        completed, report = self.execute(query_response(attribute_extra=b"\xf8\x06\x01"))
        self.assertEqual(1, completed.returncode, report)
        outcome = report["operations"]["FeatureService/QueryFeatures"]
        self.assertEqual("fail", outcome["facet_results"]["media-schema"])
        self.assertIn("attributes", outcome["reason"])

    def test_rpc_exception_fails_without_losing_other_results(self):
        completed, report = self.execute(abort=True)
        self.assertEqual(1, completed.returncode, report)
        self.assertIn("injected unavailable", report["operations"]["FeatureService/QueryFeatures"]["reason"])
        self.assertEqual(len(CALLS) - 1, sum(item["result"] == "pass" for item in report["operations"].values()))


class DotnetRunnerTransportTests(RunnerTransportContract, unittest.TestCase):
    lane = "grpc-dotnet"

    def command(self, target, fixtures, report_path):
        self.assertTrue(DOTNET_RUNNER.is_file(), "Build certification/dotnet in Release before running this suite")
        return ["dotnet", str(DOTNET_RUNNER), target, str(fixtures), str(report_path)]


class PythonRunnerTransportTests(RunnerTransportContract, unittest.TestCase):
    lane = "grpc-python"

    def command(self, target, fixtures, report_path):
        try:
            import geospatial.v1.feature_service_pb2  # noqa: F401
        except ImportError:
            self.fail("Install the promoted geospatial-grpc package before running this suite")
        return [sys.executable, str(PYTHON_RUNNER), target, str(fixtures), str(report_path)]


class TypeScriptRunnerTransportTests(RunnerTransportContract, unittest.TestCase):
    lane = "grpc-typescript"

    def command(self, target, fixtures, report_path):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js 22+ is required for the TypeScript runner")
        self.assertTrue(TYPESCRIPT_MODULES.is_dir(), "Run npm ci in certification/typescript before this suite")
        return [node, str(TYPESCRIPT_RUNNER), target, str(fixtures), str(report_path)]


if __name__ == "__main__":
    unittest.main()
