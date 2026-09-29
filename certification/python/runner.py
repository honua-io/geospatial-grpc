"""Execute the promoted ``geospatial-grpc`` Python package against a live target.

This is the Python counterpart of ``certification/dotnet/Program.cs``. It runs the
same six conformance fixtures through the installed generated client (never a
source checkout), compares each canonical response with the fixture, and writes
a lane report consumed by ``scripts/build_protocol_certification_fragment.py``.

The installed package version is reported exactly as installed. The fragment
builder decides whether that version satisfies the governed cell; a promoted
package that is not the governed ``client_version`` stays an attributable
execution result and never a governed pass.

usage: runner.py <absolute-channel-target> <fixture-directory> <report-path>
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from urllib.parse import urlsplit

import grpc
from google.protobuf import json_format

from geospatial.v1 import (
    feature_service_pb2,
    feature_service_pb2_grpc,
    form_service_pb2,
    form_service_pb2_grpc,
    process_service_pb2,
    process_service_pb2_grpc,
    workspace_service_pb2,
    workspace_service_pb2_grpc,
)

PACKAGE = "geospatial-grpc"
PACKAGE_SOURCE = "https://pypi.org/pypi/geospatial-grpc/json"
SERVER_ASSIGNED_FIELDS = Path(__file__).resolve().parents[1] / "server-assigned-fields.v1.json"
SERVER_ASSIGNED = "<server-assigned>"


def load_server_assigned_fields(
    path: Path = SERVER_ASSIGNED_FIELDS,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (required, optional) server-assigned paths by operation."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "honua.grpc-certification-server-assigned-fields/v1":
        raise ValueError(f"unsupported server-assigned field list: {path}")
    return document["operations"], document.get("optional_operations", {})


def _path_tokens(pattern: str) -> list[str]:
    if not pattern.startswith("$."):
        raise ValueError(f"server-assigned path must start with '$.': {pattern}")
    tokens = []
    for part in pattern[2:].split("."):
        if part.endswith("[*]"):
            tokens.extend([part[:-3], "[*]"])
        else:
            tokens.append(part)
    if not tokens or any(not token for token in tokens):
        raise ValueError(f"malformed server-assigned path: {pattern}")
    return tokens


def mask_server_assigned(document: object, patterns: list[str], optional: list[str] = ()) -> object:
    """Replace each present server-assigned value with a placeholder.

    Absent values are left absent, so the comparison still requires a required
    path on both sides. Optional paths (values that may validly be the proto3
    default, which the JSON mapping omits) are removed instead. Nothing outside
    the listed paths is touched.
    """
    def visit(node: object, tokens: list[str], remove: bool) -> None:
        head, rest = tokens[0], tokens[1:]
        if head == "[*]":
            if isinstance(node, list):
                if rest:
                    for item in node:
                        visit(item, rest, remove)
                elif not remove:
                    node[:] = [SERVER_ASSIGNED] * len(node)
            return
        if not isinstance(node, dict) or head not in node:
            return
        if rest:
            visit(node[head], rest, remove)
        elif remove:
            del node[head]
        else:
            node[head] = SERVER_ASSIGNED

    for pattern in patterns:
        visit(document, _path_tokens(pattern), False)
    for pattern in optional:
        visit(document, _path_tokens(pattern), True)
    return document


def _kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError(f"unsupported JSON value {type(value).__name__}")


def first_divergence(expected: object, actual: object, path: str = "$") -> str | None:
    """Return the first JSON path where the canonical documents differ."""
    if _kind(expected) != _kind(actual):
        return path
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        for name in sorted(set(expected) | set(actual)):
            child = f"{path}.{name}"
            if name not in expected or name not in actual:
                return child
            divergence = first_divergence(expected[name], actual[name], child)
            if divergence is not None:
                return divergence
        return None
    if isinstance(expected, list):
        assert isinstance(actual, list)
        shared = min(len(expected), len(actual))
        for index in range(shared):
            divergence = first_divergence(expected[index], actual[index], f"{path}[{index}]")
            if divergence is not None:
                return divergence
        return None if len(expected) == len(actual) else f"{path}[{shared}]"
    return None if expected == actual else path


def _canonical(message) -> object:
    # Round-trip through the proto3 JSON mapping so both sides use identical
    # canonical spellings (enum names, int64-as-string, omitted defaults).
    return json.loads(json_format.MessageToJson(message))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: runner.py <absolute-channel-target> <fixture-directory> <report-path>", file=sys.stderr)
        return 2
    target = urlsplit(argv[0])
    if target.scheme not in {"http", "https"} or not target.hostname or target.port is None:
        print("channel target must be an absolute http(s)://host:port URL", file=sys.stderr)
        return 2
    fixture_directory = Path(argv[1]).resolve()
    report_path = Path(argv[2]).resolve()
    api_key = os.environ.get("HONUA_PROTOCOL_API_KEY")
    if not api_key:
        raise SystemExit("HONUA_PROTOCOL_API_KEY is required")
    call_metadata = (("x-api-key", api_key),)
    authority = f"{target.hostname}:{target.port}"
    channel = (
        grpc.secure_channel(authority, grpc.ssl_channel_credentials())
        if target.scheme == "https"
        else grpc.insecure_channel(authority)
    )
    outcomes: dict[str, dict] = {}
    failures = 0
    started_at = datetime.now(timezone.utc)
    server_assigned, optional_server_assigned = load_server_assigned_fields()

    def compare(operation, request_fixture, response_fixture, request_type, response_type, invoke):
        """Call once and return the first divergence from the fixture, or None."""
        request = json_format.Parse(
            (fixture_directory / request_fixture).read_text(encoding="utf-8"), request_type()
        )
        response = invoke(request, metadata=call_metadata, timeout=30)
        expected = json_format.Parse(
            (fixture_directory / response_fixture).read_text(encoding="utf-8"), response_type()
        )
        patterns = server_assigned.get(operation, [])
        optional = optional_server_assigned.get(operation, [])
        return first_divergence(
            mask_server_assigned(_canonical(expected), patterns, optional),
            mask_server_assigned(_canonical(response), patterns, optional),
        )

    def execute(operation, request_fixture, response_fixture, request_type, response_type, invoke,
                negative=None):
        nonlocal failures
        try:
            if negative is not None:
                negative_request_fixture, negative_status_fixture, verify = negative
                negative_request = json_format.Parse(
                    (fixture_directory / negative_request_fixture).read_text(encoding="utf-8"), request_type()
                )
                expected_status = json.loads(
                    (fixture_directory / negative_status_fixture).read_text(encoding="utf-8")
                )
                try:
                    invoke(negative_request, metadata=call_metadata, timeout=30)
                except grpc.RpcError as rejection:
                    if rejection.code().value[0] != expected_status["code"]:
                        failures += 1
                        outcomes[operation] = {
                            "result": "fail",
                            "reason": (
                                f"Negative case {negative_request_fixture} expected status "
                                f"{expected_status['name']}, got {rejection.code().name}: {rejection.details()}"
                            ),
                        }
                        return
                else:
                    failures += 1
                    outcomes[operation] = {
                        "result": "fail",
                        "reason": (
                            f"Negative case {negative_request_fixture} succeeded; expected the whole "
                            f"batch to fail with status {expected_status['name']}"
                        ),
                    }
                    return
                # The rejected batch must have applied nothing: read its targets back.
                verify_divergence = verify()
                if verify_divergence is not None:
                    failures += 1
                    outcomes[operation] = {
                        "result": "fail",
                        "reason": (
                            f"Negative case {negative_request_fixture} was rejected, but reading its targets back "
                            f"does not match the unchanged state at {verify_divergence}"
                        ),
                    }
                    return
            divergence = compare(operation, request_fixture, response_fixture, request_type, response_type, invoke)
            if divergence is not None:
                failures += 1
                outcomes[operation] = {
                    "result": "fail",
                    "reason": f"Canonical response mismatch at {divergence}",
                }
                return
            outcomes[operation] = {"result": "pass"}
        except Exception as exception:  # noqa: BLE001 - every failure is a recorded outcome
            failures += 1
            detail = exception.details() if isinstance(exception, grpc.RpcError) else str(exception)
            code = f"{exception.code().name}: " if isinstance(exception, grpc.RpcError) else ""
            outcomes[operation] = {
                "result": "fail",
                "reason": (
                    "Canonical published client executed and failed: "
                    f"{type(exception).__name__}: {code}{detail}"
                ),
            }

    with channel:
        feature = feature_service_pb2_grpc.FeatureServiceStub(channel)
        form = form_service_pb2_grpc.FormServiceStub(channel)
        process = process_service_pb2_grpc.ProcessServiceStub(channel)
        workspace = workspace_service_pb2_grpc.WorkspaceServiceStub(channel)
        execute("FeatureService/QueryFeatures", "feature_query_request.json", "feature_query_response.json",
                feature_service_pb2.QueryFeaturesRequest, feature_service_pb2.QueryFeaturesResponse,
                feature.QueryFeatures)
        execute("FeatureService/ApplyEdits", "feature_apply_edits_request.json", "feature_apply_edits_response.json",
                feature_service_pb2.ApplyEditsRequest, feature_service_pb2.ApplyEditsResponse,
                feature.ApplyEdits,
                negative=("feature_apply_edits_missing_target_request.json",
                          "feature_apply_edits_missing_target_status.json",
                          lambda: compare("FeatureService/QueryFeatures",
                                          "feature_apply_edits_missing_target_verify_request.json",
                                          "feature_apply_edits_missing_target_verify_response.json",
                                          feature_service_pb2.QueryFeaturesRequest,
                                          feature_service_pb2.QueryFeaturesResponse,
                                          feature.QueryFeatures)))
        execute("FormService/GetFormDefinition", "form_get_definition_request.json",
                "form_get_definition_response.json",
                form_service_pb2.GetFormDefinitionRequest, form_service_pb2.GetFormDefinitionResponse,
                form.GetFormDefinition)
        execute("FormService/SubmitFormData", "form_submit_request.json", "form_submit_response.json",
                form_service_pb2.SubmitFormDataRequest, form_service_pb2.SubmitFormDataResponse,
                form.SubmitFormData)
        execute("ProcessService/ExecutePlan", "process_execute_plan_request.json",
                "process_execute_plan_response.json",
                process_service_pb2.ExecutePlanRequest, process_service_pb2.ExecutePlanResponse,
                process.ExecutePlan)
        execute("WorkspaceService/CreateWorkspace", "workspace_create_request.json", "workspace_create_response.json",
                workspace_service_pb2.CreateWorkspaceRequest, workspace_service_pb2.CreateWorkspaceResponse,
                workspace.CreateWorkspace)

    report = {
        "runner_lane": "grpc-python",
        "package": PACKAGE,
        "package_version": metadata.version(PACKAGE),
        "package_source": PACKAGE_SOURCE,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "execution_identity": {
            "channel_target": f"{target.scheme}://{authority}",
            "server_image": os.environ.get("SERVER_IMAGE"),
            "server_source_sha": os.environ.get("SERVER_SOURCE_SHA"),
            "fixture_revision": os.environ.get("FIXTURE_REVISION"),
        },
        "operations": outcomes,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
