#!/usr/bin/env bash
#
# Breaking-gate regression test for the geospatial.v1 protocol surface.
#
# This is a meta-test of the `buf breaking` configuration in buf.yaml, NOT a
# conformance fixture. It proves that the breaking gate actually catches
# RPC/service deletion and rename.
#
# Why this exists: buf.yaml originally used only the WIRE_JSON ruleset, which
# enforces field/enum wire+JSON compatibility but does NOT include the
# RPC/service no-delete rules. Deleting or renaming an RPC or service changes
# the gRPC method path /geospatial.v1.<Service>/<Method> — part of the wire
# contract every client depends on — yet passed the CI breaking gate silently
# (a "weak gate" / false-conformance defect). buf.yaml now adds RPC_NO_DELETE
# and PACKAGE_SERVICE_NO_DELETE alongside WIRE_JSON. This harness asserts those
# rules are in force so the config can never silently regress back to a
# permissive gate.
#
# The test builds an isolated throwaway git repo containing the current proto
# tree + buf.yaml, commits it as the baseline, then applies each mutation to the
# working tree and asserts `buf breaking --against <baseline>` fails. A negative
# control (no mutation) asserts the gate passes, so a gate that always errors is
# also flagged.
#
# Usage:
#   conformance/breaking-gate-test.sh
#
# Requirements: `buf` and `git` on PATH. No language toolchains needed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -f "${REPO_ROOT}/buf.yaml" || ! -d "${REPO_ROOT}/geospatial" ]]; then
  echo "ERROR: must run from the geospatial-grpc repo (buf.yaml + geospatial/ required)." >&2
  exit 2
fi

for tool in buf git; do
  command -v "${tool}" >/dev/null 2>&1 || { echo "ERROR: '${tool}' not found on PATH." >&2; exit 2; }
done

# Discover a stable service + RPC to mutate, so the test does not hard-code
# names that a future rename could invalidate. Pick the first proto file that
# declares a service, then the first service and the first RPC in it.
TARGET_FILE="$(grep -rl '^service ' "${REPO_ROOT}/geospatial" | sort | head -n1 || true)"
if [[ -z "${TARGET_FILE}" ]]; then
  echo "ERROR: no service definition found under geospatial/." >&2
  exit 2
fi
REL_FILE="${TARGET_FILE#"${REPO_ROOT}"/}"
SERVICE_NAME="$(grep -m1 '^service ' "${TARGET_FILE}" | sed -E 's/^service +([A-Za-z0-9_]+).*/\1/')"
RPC_NAME="$(grep -m1 -E '^[[:space:]]*rpc ' "${TARGET_FILE}" | sed -E 's/^[[:space:]]*rpc +([A-Za-z0-9_]+).*/\1/')"

if [[ -z "${SERVICE_NAME}" || -z "${RPC_NAME}" ]]; then
  echo "ERROR: could not extract a service/RPC name from ${REL_FILE}." >&2
  exit 2
fi

echo "Breaking-gate test target: ${REL_FILE} (service ${SERVICE_NAME}, rpc ${RPC_NAME})"

WORK="$(mktemp -d)"
cleanup() { rm -rf "${WORK}"; }
trap cleanup EXIT

# Build an isolated baseline repo: proto tree + buf.yaml only.
cp -R "${REPO_ROOT}/geospatial" "${WORK}/geospatial"
cp "${REPO_ROOT}/buf.yaml" "${WORK}/buf.yaml"

git -C "${WORK}" init -q
git -C "${WORK}" -c user.email=ci@honua.io -c user.name=ci add -A
git -C "${WORK}" -c user.email=ci@honua.io -c user.name=ci commit -q -m baseline

WORK_FILE="${WORK}/${REL_FILE}"
PRISTINE="$(cat "${WORK_FILE}")"

FAILURES=0

# assert_breaking <expect: fail|pass> <label>
# Runs the gate against the committed baseline and checks the exit code.
assert_breaking() {
  local expect="$1" label="$2" rc=0
  ( cd "${WORK}" && buf breaking --against '.git#ref=HEAD' ) >/dev/null 2>&1 || rc=$?
  case "${expect}" in
    fail)
      if [[ "${rc}" -ne 0 ]]; then
        echo "  PASS: ${label} (gate flagged the change, exit ${rc})"
      else
        echo "  FAIL: ${label} — gate did NOT flag the change (exit 0)" >&2
        FAILURES=$((FAILURES + 1))
      fi
      ;;
    pass)
      if [[ "${rc}" -eq 0 ]]; then
        echo "  PASS: ${label} (gate allowed the change)"
      else
        echo "  FAIL: ${label} — gate errored on an unchanged surface (exit ${rc})" >&2
        FAILURES=$((FAILURES + 1))
      fi
      ;;
  esac
}

restore() { printf '%s' "${PRISTINE}" > "${WORK_FILE}"; }

# Negative control: an unmodified surface must pass, else the gate is misconfigured.
restore
assert_breaking pass "no change (negative control)"

# RPC deletion: remove the RPC entirely (RPC_NO_DELETE must fire).
restore
sed -i -E "/^[[:space:]]*rpc ${RPC_NAME}\(/d" "${WORK_FILE}"
assert_breaking fail "delete RPC ${RPC_NAME}"

# RPC rename: buf treats a rename as delete-of-old (RPC_NO_DELETE must fire).
restore
sed -i -E "s/\brpc ${RPC_NAME}\(/rpc ${RPC_NAME}Renamed(/" "${WORK_FILE}"
assert_breaking fail "rename RPC ${RPC_NAME}"

# Service rename: buf treats a rename as delete-of-old service
# (PACKAGE_SERVICE_NO_DELETE must fire).
restore
sed -i -E "s/\bservice ${SERVICE_NAME}\b/service ${SERVICE_NAME}Renamed/" "${WORK_FILE}"
assert_breaking fail "rename service ${SERVICE_NAME}"

restore

if [[ "${FAILURES}" -ne 0 ]]; then
  echo "Breaking-gate test FAILED (${FAILURES} assertion(s)). The buf.yaml breaking" >&2
  echo "config no longer catches RPC/service deletion or rename — restore" >&2
  echo "RPC_NO_DELETE and PACKAGE_SERVICE_NO_DELETE to buf.yaml." >&2
  exit 1
fi

echo "Breaking-gate test passed: RPC/service deletion and rename are caught."
