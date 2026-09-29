"""Exercise installed .NET bytes against an independent loopback gRPC oracle.

This is a producer regression, not Honua Server release certification. The
oracle writes protobuf wire fields directly; it never uses generated bindings
or records the runner's output to construct an expected response.
"""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

import grpc

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "certification/dotnet/bin/Release/net10.0/GrpcCertificationRunner.dll"
CALLS = {
    "FeatureService/QueryFeatures": "feature_query",
    "FeatureService/ApplyEdits": "feature_apply_edits",
    "FormService/GetFormDefinition": "form_get_definition",
    "FormService/SubmitFormData": "form_submit",
    "ProcessService/ExecutePlan": "process_execute_plan",
    "WorkspaceService/CreateWorkspace": "workspace_create",
}


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result) + bytes([value])


def message(field, payload):
    return varint((field << 3) | 2) + varint(len(payload)) + payload


def query_response(*, x=-157.5, y=21.25, z=0.0, m=12.5, wkid=4326, null_value=True, identifier=42):
    # QueryFeaturesResponse.features=5 -> Feature.geometry=3 -> Geometry.point=1.
    # Point x/y/z/m are fixed64 fields 1/2/3/4; optional zero Z must stay present.
    point = b"".join(varint((field << 3) | 1) + struct.pack("<d", value)
                     for field, value in ((1, x), (2, y), (3, z), (4, m)) if value is not None)
    feature = b"\x08" + varint(identifier) + message(3, message(1, point))
    # AttributeValue.null_value is oneof field 9, explicitly encoded even at 0.
    attribute = b"\x48\x00" if null_value else b"\x21" + struct.pack("<d", 0.0)
    feature += message(2, message(1, b"height") + message(2, attribute))
    return b"\x10\x01" + message(3, b"\x08" + varint(wkid)) + message(5, feature)


EXPECTED_QUERY = {
    "geometryType": "GEOMETRY_TYPE_POINT",
    "spatialReference": {"wkid": 4326},
    "features": [{"id": "42", "attributes": {"height": {"nullValue": "NULL_VALUE"}},
                  "geometry": {"point": {"x": -157.5, "y": 21.25, "z": 0, "m": 12.5}}}],
}


class RunnerTransportTests(unittest.TestCase):
    def execute(self, response=None, abort=False):
        self.assertTrue(RUNNER.is_file(), "Build certification/dotnet in Release before running this suite")
        requests = {}
        server = grpc.server(ThreadPoolExecutor(max_workers=2))

        def handler(operation):
            def invoke(request, context):
                requests[operation] = request
                if operation == "FeatureService/QueryFeatures":
                    if abort:
                        context.abort(grpc.StatusCode.UNAVAILABLE, "injected unavailable")
                    return query_response() if response is None else response
                return b""
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
                for operation, name in CALLS.items():
                    request = {"serviceId": "oracle"} if name == "feature_query" else {}
                    expected = EXPECTED_QUERY if name == "feature_query" else {}
                    (fixtures / f"{name}_request.json").write_text(json.dumps(request))
                    (fixtures / f"{name}_response.json").write_text(json.dumps(expected))
                report_path = fixtures / "report.json"
                completed = subprocess.run(
                    ["dotnet", str(RUNNER), f"http://127.0.0.1:{port}", str(fixtures), str(report_path)],
                    env={**os.environ, "HONUA_PROTOCOL_API_KEY": "oracle-test-key"},
                    text=True, capture_output=True, timeout=30, check=False,
                )
                self.assertTrue(report_path.is_file(), completed.stderr)
                report = json.loads(report_path.read_text())
        finally:
            server.stop(0).wait()
        self.assertEqual(set(CALLS), set(requests))
        self.assertEqual(b"\x0a\x06oracle", requests["FeatureService/QueryFeatures"])
        self.assertEqual(set(CALLS), set(report["operations"]))
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
                self.assertEqual(5, sum(item["result"] == "pass" for item in report["operations"].values()))

    def test_rpc_exception_fails_without_losing_other_results(self):
        completed, report = self.execute(abort=True)
        self.assertEqual(1, completed.returncode, report)
        self.assertIn("injected unavailable", report["operations"]["FeatureService/QueryFeatures"]["reason"])
        self.assertEqual(5, sum(item["result"] == "pass" for item in report["operations"].values()))


if __name__ == "__main__":
    unittest.main()
