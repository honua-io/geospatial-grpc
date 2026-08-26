#!/usr/bin/env python3
"""Build governed multi-client gRPC certification evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
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


def validate_identity(args: argparse.Namespace) -> tuple[str, str]:
    parsed = urlsplit(args.channel_target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
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
    reports = {}
    payloads = []
    for report_path in args.report:
        raw = report_path.read_bytes()
        report = json.loads(raw)
        lane = report["runner_lane"]
        if lane not in CLIENT_IDS or lane in reports:
            raise ValueError(f"invalid or duplicate runner lane: {lane}")
        reports[lane] = report
        payloads.append({"name": report_path.name, "content_base64": base64.b64encode(raw).decode()})

    now = args.completed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload_base64 = base64.b64encode(canonical_bytes(payloads)).decode()
    observations = []
    for client in catalog["clients"]:
        lane = client["client_lane"]
        report = reports.get(lane, {})
        outcomes = report.get("operations", {})
        for operation in catalog["operations"]:
            outcome = outcomes.get(operation["operation"])
            result = outcome.get("result") if outcome else "skip"
            if result not in {"pass", "fail", "skip"}:
                raise ValueError(f"unsupported result for {lane}/{operation['operation']}: {result}")
            reason = None if result != "skip" else (
                (outcome or {}).get("reason")
                or report.get("unexecuted_reason")
                or f"No canonical published-client execution result; owner: {OWNER}"
            )
            facets = operation["scenario_facets"]
            receipt_facets = {facet: result for facet in facets}
            receipt = None
            digest = None
            if result != "skip":
                receipt = {
                    "schema": "honua.certification-evidence-receipt/v1",
                    "identity": {
                        "capability_key": operation["capability_key"],
                        "surface": operation["surface"],
                        "operation": operation["operation"],
                        "canonical_client": client["canonical_client"],
                        "client_version": client["client_version"],
                        "deployment_target": client["deployment_target"],
                        "source_sha": args.server_source_sha,
                        "producer_source_sha": args.producer_source_sha,
                        "image_digest": image_digest,
                        "fixture_revision": catalog["fixture_revision"],
                        "contract_revision": catalog["contract_revision"],
                        "auth_policy_revision": operation["auth_policy_revision"],
                        "started_at": args.started_at,
                        "completed_at": now,
                    },
                    "result": result,
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
                "exercised_capabilities": facets if result == "pass" else [],
                "client_version": client["client_version"],
                "deployment_target": client["deployment_target"],
                "result": result,
                "skip_reason": reason,
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
                    facet: {"result": result, "evidence_digest": digest} for facet in facets
                },
                "started_at": args.started_at,
                "completed_at": now,
            }
            observations.append(observation)
    return {
        "schema": "honua.protocol-certification-fragment/v1",
        "producer": PRODUCER,
        "generated_at": now,
        "candidate": {"source_sha": args.server_source_sha, "image_digest": image_digest, "cut_at": args.candidate_cut},
        "operation_scope": {
            "complete": True,
            "owner_issue": OWNER,
            "matrix_sha256": "sha256:" + hashlib.sha256(canonical_bytes(catalog)).hexdigest(),
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
    args = parser.parse_args()
    fragment = build_fragment(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fragment, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
