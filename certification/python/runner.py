"""Execute the promoted ``geospatial-grpc`` Python package against a live target.

This is the Python counterpart of ``certification/dotnet/Program.cs`` and
``certification/typescript/runner.mjs``. It runs every scenario in
``certification/scenarios.v1.json`` through the installed generated client
(never a source checkout), compares each canonical response with the fixture,
and writes a lane report consumed by
``scripts/build_protocol_certification_fragment.py``.

The installed package version is reported exactly as installed. The fragment
builder decides whether that version satisfies the governed cell.

usage: runner.py <absolute-channel-target> <fixture-directory> <report-path>
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from urllib.parse import urlsplit

import grpc
from google.protobuf import json_format, message_factory

PACKAGE = "geospatial-grpc"
PACKAGE_SOURCE = "https://pypi.org/pypi/geospatial-grpc/json"
CERTIFICATION = Path(__file__).resolve().parents[1]
SERVER_ASSIGNED_FIELDS = CERTIFICATION / "server-assigned-fields.v1.json"
SCENARIOS = CERTIFICATION / "scenarios.v1.json"
CATALOG = CERTIFICATION / "protocol-certification-catalog.v1.json"
SERVER_ASSIGNED = "<server-assigned>"
CAPTURE = re.compile(r"\{\{capture:([A-Za-z0-9_]+)\}\}")
POLL_INTERVAL_SECONDS = 1.0


class ScenarioFailure(Exception):
    """A recorded, attributable scenario failure."""


def load_server_assigned_fields(
    path: Path = SERVER_ASSIGNED_FIELDS,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (required, optional) server-assigned paths by operation."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "honua.grpc-certification-server-assigned-fields/v1":
        raise ValueError(f"unsupported server-assigned field list: {path}")
    return document["operations"], document.get("optional_operations", {})


def load_scenarios(path: Path = SCENARIOS) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "honua.grpc-certification-scenarios/v1":
        raise ValueError(f"unsupported scenario list: {path}")
    return document["scenarios"]


def load_excluded_operations(path: Path = CATALOG) -> set[str]:
    """Operations the 2026.1 scope ruling excludes from the governed cells (#88)."""
    catalog = json.loads(path.read_text(encoding="utf-8"))
    return {operation["operation"] for operation in catalog.get("excluded_operations", [])}


def _path_tokens(pattern: str) -> list[str]:
    if not pattern.startswith("$."):
        raise ValueError(f"path must start with '$.': {pattern}")
    tokens = []
    for part in pattern[2:].split("."):
        if part.endswith("[*]"):
            tokens.extend([part[:-3], "[*]"])
        else:
            tokens.append(part)
    if not tokens or any(not token for token in tokens):
        raise ValueError(f"malformed path: {pattern}")
    return tokens


def read_path(document: object, pattern: str) -> object:
    """Return the value at a path without wildcards, or None."""
    node = document
    for token in _path_tokens(pattern):
        if token == "[*]" or not isinstance(node, dict) or token not in node:
            return None
        node = node[token]
    return node


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


def _module_for(service: str):
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", service).lower()
    return importlib.import_module(f"geospatial.v1.{snake}_pb2")


class Method:
    """One geospatial.v1 RPC bound to the installed generated message classes."""

    def __init__(self, channel: grpc.Channel, operation: str):
        service, name = operation.split("/")
        descriptor = _module_for(service).DESCRIPTOR.services_by_name[service].methods_by_name[name]
        self.request_type = message_factory.GetMessageClass(descriptor.input_type)
        self.response_type = message_factory.GetMessageClass(descriptor.output_type)
        path = f"/geospatial.v1.{service}/{name}"
        factory = channel.unary_stream if descriptor.server_streaming else channel.unary_unary
        self.streaming = descriptor.server_streaming
        self.call = factory(
            path,
            request_serializer=self.request_type.SerializeToString,
            response_deserializer=self.response_type.FromString,
        )


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
    poll_timeout_override = os.environ.get("HONUA_CERTIFICATION_POLL_TIMEOUT_SECONDS")
    call_metadata = (("x-api-key", api_key),)
    authority = f"{target.hostname}:{target.port}"
    channel = (
        grpc.secure_channel(authority, grpc.ssl_channel_credentials())
        if target.scheme == "https"
        else grpc.insecure_channel(authority)
    )
    outcomes: dict[str, dict] = {}
    captures: dict[str, str] = {}
    started_at = datetime.now(timezone.utc)
    server_assigned, optional_server_assigned = load_server_assigned_fields()
    methods: dict[str, Method] = {}

    def method(operation: str) -> Method:
        if operation not in methods:
            methods[operation] = Method(channel, operation)
        return methods[operation]

    def read_fixture(name: str) -> str:
        text = (fixture_directory / name).read_text(encoding="utf-8")

        def substitute(match: re.Match) -> str:
            key = match.group(1)
            if key not in captures:
                raise ScenarioFailure(f"{name} needs capture '{key}', which an earlier scenario did not provide")
            return captures[key]

        return CAPTURE.sub(substitute, text)

    def parse(name: str, message_type):
        return json_format.Parse(read_fixture(name), message_type())

    def masked(operation: str, document: object) -> object:
        return mask_server_assigned(
            document, server_assigned.get(operation, []), optional_server_assigned.get(operation, []))

    def unary(operation: str, request_fixture: str):
        rpc = method(operation)
        return rpc.call(parse(request_fixture, rpc.request_type), metadata=call_metadata, timeout=30)

    def compare_unary(operation: str, response_fixture: str, response) -> str | None:
        expected = parse(response_fixture, method(operation).response_type)
        return first_divergence(masked(operation, _canonical(expected)), masked(operation, _canonical(response)))

    def capture(spec: dict | None, document: object) -> None:
        for key, pattern in (spec or {}).items():
            value = read_path(document, pattern)
            if not isinstance(value, str) or not value:
                raise ScenarioFailure(f"response has no value at {pattern} to capture as '{key}'")
            captures[key] = value

    def run(scenario: dict) -> None:
        operation = scenario["operation"]
        setup = scenario.get("setup")
        if setup is not None:
            capture(setup.get("capture"), _canonical(unary(setup["operation"], setup["request"])))
        negative = scenario.get("negative")
        if negative is not None:
            expected_status = json.loads(read_fixture(negative["status"]))
            try:
                unary(operation, negative["request"])
            except grpc.RpcError as rejection:
                if rejection.code().value[0] != expected_status["code"]:
                    raise ScenarioFailure(
                        f"Negative case {negative['request']} expected status {expected_status['name']}, "
                        f"got {rejection.code().name}: {rejection.details()}") from None
            else:
                raise ScenarioFailure(
                    f"Negative case {negative['request']} succeeded; expected the whole batch to fail "
                    f"with status {expected_status['name']}")
            verify = negative.get("verify")
            if verify is not None:
                divergence = compare_unary(
                    verify["operation"], verify["response"], unary(verify["operation"], verify["request"]))
                if divergence is not None:
                    raise ScenarioFailure(
                        f"Negative case {negative['request']} was rejected, but reading its targets back "
                        f"does not match the unchanged state at {divergence}")
        if scenario["kind"] == "server_stream":
            rpc = method(operation)
            messages = list(rpc.call(
                parse(scenario["request"], rpc.request_type), metadata=call_metadata, timeout=60))
            actual = [masked(operation, _canonical(message)) for message in messages]
            expected = []
            index = 1
            while (fixture_directory / f"{scenario['responses']}.{index}.json").is_file():
                expected.append(masked(operation, _canonical(
                    parse(f"{scenario['responses']}.{index}.json", rpc.response_type))))
                index += 1
            if not expected:
                raise ScenarioFailure(f"no {scenario['responses']}.N.json fixtures")
            if messages:
                capture(scenario.get("capture"), _canonical(messages[0]))
            divergence = first_divergence(expected, actual)
        else:
            poll = scenario.get("poll_until")
            response = unary(operation, scenario["request"])
            if poll is not None:
                timeout = float(poll_timeout_override or poll["timeout_seconds"])
                deadline = time.monotonic() + timeout
                while read_path(_canonical(response), poll["path"]) not in poll["values"] \
                        and time.monotonic() < deadline:
                    time.sleep(POLL_INTERVAL_SECONDS)
                    response = unary(operation, scenario["request"])
            capture(scenario.get("capture"), _canonical(response))
            divergence = compare_unary(operation, scenario["response"], response)
        if divergence is not None:
            raise ScenarioFailure(f"Canonical response mismatch at {divergence}")

    with channel:
        for scenario in load_scenarios():
            operation = scenario["operation"]
            try:
                run(scenario)
                outcomes[operation] = {"result": "pass"}
            except ScenarioFailure as failure:
                outcomes[operation] = {"result": "fail", "reason": str(failure)}
            except Exception as exception:  # noqa: BLE001 - every failure is a recorded outcome
                detail = exception.details() if isinstance(exception, grpc.RpcError) else str(exception)
                code = f"{exception.code().name}: " if isinstance(exception, grpc.RpcError) else ""
                outcomes[operation] = {
                    "result": "fail",
                    "reason": (
                        "Canonical published client executed and failed: "
                        f"{type(exception).__name__}: {code}{detail}"
                    ),
                }

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
    # Excluded operations are still executed and reported, but only a governed
    # failure fails the lane (the fragment reports excluded results separately).
    excluded = load_excluded_operations()
    governed_failures = sum(
        1 for name, outcome in outcomes.items() if outcome["result"] == "fail" and name not in excluded
    )
    return 0 if governed_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
