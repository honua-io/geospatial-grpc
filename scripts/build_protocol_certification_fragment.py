#!/usr/bin/env python3
"""Build governed multi-client gRPC certification evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

CATALOG = Path(__file__).resolve().parents[1] / "certification/protocol-certification-catalog.v1.json"
PRODUCER = "geospatial-grpc"
OWNER = "https://github.com/honua-io/geospatial-grpc/issues/88"
CLIENT_IDS = {
    "grpc-dotnet": "Generated gRPC .NET client",
    "grpc-python": "Generated gRPC Python client",
    "grpc-typescript": "Generated gRPC TypeScript client",
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def timestamp(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is not None:
            return parsed
    except (ValueError, AttributeError):
        pass
    raise ValueError(f"{name} must be a timezone-aware ISO-8601 timestamp")


def validate_times(started_at: str, completed_at: str, cut_at: str, tier: str) -> None:
    started = timestamp(started_at, "started_at")
    completed = timestamp(completed_at, "completed_at")
    cut = timestamp(cut_at, "candidate_cut")
    now = datetime.now(timezone.utc)
    if started < cut:
        raise ValueError("stale evidence: execution predates candidate cut")
    if completed < started:
        raise ValueError("completed_at precedes started_at")
    if completed > now + timedelta(minutes=5):
        raise ValueError("completed_at is in the future")
    if tier in {"nightly", "release"} and now - completed > timedelta(hours=24):
        raise ValueError("stale evidence: execution is older than 24 hours")


def certification_errors(fragment: dict, tier: str) -> list[str]:
    errors = [
        f"{failure['runner_lane']}/{failure['operation']}: {failure['reason']}"
        for failure in fragment["execution_failures"]
    ]
    if tier in {"nightly", "release"} and fragment["client_rollup"]["state"] != "pass":
        missing = sum(item["result"] != "pass" for item in fragment["observations"])
        errors.append(f"{tier} certification has {missing} non-passing required cells")
    return errors


def validate_identity(args: argparse.Namespace) -> tuple[str, str]:
    parsed = urlsplit(args.channel_target)
    if (parsed.scheme not in {"http", "https"} or not parsed.netloc
            or parsed.path not in {"", "/"} or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("channel target must be an absolute HTTP(S) origin")
    if not re.fullmatch(r"[0-9a-f]{40}", args.server_source_sha):
        raise ValueError("server source SHA must be a full lowercase commit")
    if not re.fullmatch(r"[0-9a-f]{40}", args.producer_source_sha):
        raise ValueError("producer source SHA must be a full lowercase commit")
    match = re.search(r"@(?P<digest>sha256:[0-9a-f]{64})$", args.server_image)
    if not match:
        raise ValueError("server image must be digest-addressed")
    if args.image_source_revision != args.server_source_sha:
        raise ValueError("verified image source revision must equal server source SHA")
    return parsed.geturl().rstrip("/"), match.group("digest")


def build_fragment(args: argparse.Namespace) -> dict:
    target, image_digest = validate_identity(args)
    catalog = json.loads(CATALOG.read_text())
    tier = getattr(args, "tier", "pr")
    now = args.completed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    validate_times(args.started_at, now, args.candidate_cut, tier)
    reports = {}
    payloads = []
    for report_path in args.report:
        raw = report_path.read_bytes()
        report = json.loads(raw)
        lane = report["runner_lane"]
        if lane not in CLIENT_IDS or lane in reports:
            raise ValueError(f"invalid or duplicate runner lane: {lane}")
        unknown = set(report.get("operations", {})) - {op["operation"] for op in catalog["operations"]}
        if unknown:
            raise ValueError(f"unknown operations for {lane}: {sorted(unknown)}")
        if report.get("operations") and tier in {"nightly", "release"}:
            expected_identity = {
                "channel_target": target,
                "server_image": args.server_image,
                "server_source_sha": args.server_source_sha,
                "fixture_revision": catalog["fixture_revision"],
            }
            if report.get("execution_identity") != expected_identity:
                raise ValueError(f"execution identity mismatch for {lane}")
            validate_times(report.get("started_at"), report.get("completed_at"), args.candidate_cut, tier)
            if (timestamp(report["started_at"], "report started_at") < timestamp(args.started_at, "started_at")
                    or timestamp(report["completed_at"], "report completed_at") > timestamp(now, "completed_at")):
                raise ValueError(f"execution report for {lane} is outside this run")
        reports[lane] = report
        payloads.append({"name": report_path.name, "content_base64": base64.b64encode(raw).decode()})

    payload_base64 = base64.b64encode(canonical_bytes(payloads)).decode()
    observations = []
    lane_states = {}
    execution_failures = []
    for client in catalog["clients"]:
        lane = client["client_lane"]
        publication_state = client.get("publication_state")
        if publication_state not in {"published", "unpublished"}:
            raise ValueError(f"invalid publication state for {lane}: {publication_state}")
        report = reports.get(lane, {})
        outcomes = report.get("operations", {})
        lane_states[lane] = "unpublished" if publication_state == "unpublished" else "incomplete"
        if outcomes and "package" in client:
            expected_package_identity = {
                "package": client["package"],
                "package_version": client["client_version"],
                "package_source": client["package_source"],
            }
            actual_package_identity = {
                field: report.get(field) for field in expected_package_identity
            }
            if actual_package_identity != expected_package_identity:
                raise ValueError(
                    f"published package identity mismatch for {lane}: "
                    f"expected {expected_package_identity}, got {actual_package_identity}"
                )
        for operation in catalog["operations"]:
            outcome = outcomes.get(operation["operation"])
            result = outcome.get("result") if outcome else "skip"
            if result not in {"pass", "fail", "skip"}:
                raise ValueError(f"unsupported result for {lane}/{operation['operation']}: {result}")
            if result == "pass" and publication_state != "published":
                raise ValueError(f"unpublished client cannot claim a pass: {lane}")
            if result == "fail":
                execution_failures.append({
                    "runner_lane": lane, "operation": operation["operation"],
                    "reason": outcome.get("reason") or "executed client failed",
                })
            unexecuted_reason = None if result != "skip" else (
                (outcome or {}).get("reason")
                or report.get("unexecuted_reason")
                or f"No canonical published-client execution result; owner: {OWNER}"
            )
            facets = operation["scenario_facets"]
            facet_results = None
            observation_result = "skip"
            skip_reason = unexecuted_reason
            exercised_capabilities = []
            if outcome and result != "skip":
                reported_facets = outcome.get("facet_results")
                if reported_facets is not None:
                    if set(reported_facets) != set(facets) or any(
                        value not in {"pass", "fail"} for value in reported_facets.values()
                    ):
                        raise ValueError(
                            f"facet results for {lane}/{operation['operation']} must cover every "
                            "governed facet with pass or fail"
                        )
                    facet_results = {
                        facet: {"result": facet_result}
                        for facet, facet_result in reported_facets.items()
                    }
                    observation_result = (
                        "pass" if all(value == "pass" for value in reported_facets.values()) else "fail"
                    )
                    if result != observation_result:
                        raise ValueError(
                            f"result for {lane}/{operation['operation']} disagrees with facet results"
                        )
                    skip_reason = None
                    exercised_capabilities = [
                        facet for facet, value in reported_facets.items() if value == "pass"
                    ]
                else:
                    detail = outcome.get("reason")
                    positive_detail = f"; positive execution {result}"
                    if detail:
                        positive_detail += f": {detail}"
                    skip_reason = (
                        "missing required facet: negative — negative-scenario fixture not yet executed"
                        + positive_detail
                    )
            receipt_facets = None if facet_results is None else {
                facet: value["result"] for facet, value in facet_results.items()
            }
            receipt = None
            digest = None
            if facet_results is not None:
                receipt = {
                    "schema": "honua.certification-evidence-receipt/v2",
                    "identity": {
                        "capability_key": operation["capability_key"],
                        "surface": operation["surface"],
                        "operation": operation["operation"],
                        "canonical_client": client["canonical_client"],
                        "client_version": client["client_version"],
                        "deployment_target": client["deployment_target"],
                        "maturity": catalog["maturity"],
                        "required_tier": catalog["required_tier"],
                        "requirements_revision": catalog["requirements_revision"],
                        "source_sha": args.server_source_sha,
                        "producer_source_sha": args.producer_source_sha,
                        "image_digest": image_digest,
                        "fixture_revision": catalog["fixture_revision"],
                        "contract_revision": catalog["contract_revision"],
                        "auth_policy_revision": operation["auth_policy_revision"],
                        "started_at": args.started_at,
                        "completed_at": now,
                    },
                    "result": observation_result,
                    "facets": receipt_facets,
                    "payload_base64": payload_base64,
                }
                digest = "sha256:" + hashlib.sha256(canonical_bytes(receipt)).hexdigest()
            method_path = f"/geospatial.v1.{operation['operation']}"
            observation = {
                "capability_key": operation["capability_key"],
                "surface": operation["surface"],
                "operation": operation["operation"],
                "scenario_facets": facets,
                "canonical_client": client["canonical_client"],
                "client_id": client["canonical_client"],
                "runner_lane": lane,
                "protocol_version": "geospatial.v1",
                "protocol_profile": catalog["fixture_revision"],
                "performed_by": client["canonical_client"],
                "request_url": target + method_path,
                "exercised_capabilities": exercised_capabilities,
                "client_version": client["client_version"],
                "publication_state": publication_state,
                "deployment_target": client["deployment_target"],
                "result": observation_result,
                "skip_reason": skip_reason,
                "source_sha": args.server_source_sha,
                "producer_source_sha": args.producer_source_sha,
                "image_digest": image_digest,
                "fixture_revision": catalog["fixture_revision"],
                "contract_revision": catalog["contract_revision"],
                "auth_policy_revision": operation["auth_policy_revision"],
                "evidence_uri": None if digest is None else f"https://evidence.honua.io/data/sha256/{digest[7:]}",
                "evidence_digest": digest,
                "evidence_receipt": receipt,
                "facet_results": None if digest is None else {
                    facet: {**value, "evidence_digest": digest}
                    for facet, value in facet_results.items()
                },
                "started_at": args.started_at,
                "completed_at": now,
            }
            observations.append(observation)
    for lane, state in tuple(lane_states.items()):
        lane_observations = [item for item in observations if item["runner_lane"] == lane]
        if state != "unpublished" and all(
            item["evidence_receipt"] is not None for item in lane_observations
        ):
            lane_states[lane] = "executed"
    narrowing_decision = catalog.get("claim_narrowing_decision")
    if narrowing_decision is not None and not re.fullmatch(
        r"https://github\.com/honua-io/geospatial-grpc/issues/88#issuecomment-[0-9]+",
        narrowing_decision,
    ):
        raise ValueError("claim narrowing decision must be a recorded issue #88 comment URL")
    all_claimed_clients_executed = all(state == "executed" for state in lane_states.values())
    all_claimed_cells_passed = all(item["result"] == "pass" for item in observations)
    # A comment URL is provenance for a decision, not a waiver for failed cells.
    # An adopted support change must update the governed denominator itself.
    rollup_passes = all_claimed_clients_executed and all_claimed_cells_passed
    return {
        "schema": "honua.protocol-certification-fragment/v1",
        "producer": PRODUCER,
        "execution_failures": execution_failures,
        "generated_at": now,
        "candidate": {"source_sha": args.server_source_sha, "image_digest": image_digest, "cut_at": args.candidate_cut},
        "operation_scope": {
            "complete": True,
            "owner_issue": OWNER,
            "matrix_sha256": "sha256:" + hashlib.sha256(canonical_bytes(catalog)).hexdigest(),
        },
        "client_rollup": {
            "state": "pass" if rollup_passes else "red",
            "client_states": lane_states,
            "all_claimed_clients_executed": all_claimed_clients_executed,
            "all_claimed_cells_passed": all_claimed_cells_passed,
            "claim_narrowing_decision": narrowing_decision,
        },
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--channel-target", required=True)
    parser.add_argument("--server-image", required=True)
    parser.add_argument("--server-source-sha", required=True)
    parser.add_argument("--image-source-revision", required=True)
    parser.add_argument("--producer-source-sha", required=True)
    parser.add_argument("--candidate-cut", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--completed-at")
    parser.add_argument("--tier", choices=("pr", "nightly", "release"), default="pr")
    args = parser.parse_args()
    fragment = build_fragment(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fragment, indent=2) + "\n")
    errors = certification_errors(fragment, args.tier)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
