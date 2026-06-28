#!/usr/bin/env bash
#
# Conformance regression harness for the geospatial.v1 protocol surface.
#
# For every fixture listed in conformance/fixtures/manifest.txt this harness:
#
#   1. confirms the fixture's declared message type still exists in the schema;
#   2. round-trips the fixture JSON through the live schema
#      (JSON -> binary -> canonical JSON) using `buf convert`; and
#   3. compares the canonical JSON to the committed golden in
#      conformance/golden/.
#
# Because the round-trip is interpreted against the current .proto definitions,
# contract drift that changes the canonical JSON of a fixture changes the golden
# comparison and fails the harness. This catches drift in this repo before it
# reaches the downstream generated SDKs.
#
# Detection scope (important): the canonical protobuf JSON mapping omits
# proto3 default-valued fields, and `buf convert` silently drops JSON keys the
# schema no longer recognizes (exit 0). So a removed or renamed field is only
# detectable here when a fixture sets that field to a NON-default value — that
# value either appears in the golden (and disappears on removal/rename) or makes
# the conversion fail. Drift in a field that is absent, or present only with its
# proto3 default value, in every fixture is NOT caught by this round-trip; rely
# on `buf breaking` for that class. To extend coverage to a given field, add a
# fixture that exercises it with a non-default value.
#
# Usage:
#   conformance/run.sh            # verify all fixtures against goldens
#   conformance/run.sh --update   # regenerate goldens from current schema
#
# Requirements: `buf` on PATH (CI pins 1.66.0). No language toolchains needed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# This harness runs in two layouts:
#   - In-repo:  conformance/run.sh, with the .proto source tree one level up,
#               so the schema descriptor is built from source with `buf build`.
#   - Bundled:  the packaged conformance-fixtures-<version> tarball, where
#               run.sh sits beside fixtures/ and golden/ but there is no proto
#               tree. In that case a prebuilt descriptor image must be supplied
#               via CONFORMANCE_IMAGE=/path/to/image.binpb (export it from a
#               pinned schema, e.g. `buf build -o image.binpb` against the
#               matching geospatial-grpc release, or the published descriptor).
PARENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
if [[ -f "${PARENT_DIR}/buf.yaml" || -d "${PARENT_DIR}/geospatial" ]]; then
  # In-repo: conformance/run.sh with the proto source tree one level up.
  REPO_ROOT="${PARENT_DIR}"
  FIXTURE_DIR="${REPO_ROOT}/conformance/fixtures"
  GOLDEN_DIR="${REPO_ROOT}/conformance/golden"
else
  # Bundled: run.sh sits beside fixtures/ and golden/ in the extracted tarball.
  REPO_ROOT="${SCRIPT_DIR}"
  FIXTURE_DIR="${SCRIPT_DIR}/fixtures"
  GOLDEN_DIR="${SCRIPT_DIR}/golden"
fi
MANIFEST="${FIXTURE_DIR}/manifest.txt"

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
  UPDATE=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--update]" >&2
  exit 2
fi

if ! command -v buf >/dev/null 2>&1; then
  echo "error: buf not found on PATH" >&2
  exit 1
fi

mkdir -p "${GOLDEN_DIR}"

# Obtain the schema descriptor once and reuse it for every conversion. The
# .binpb suffix tells buf to treat the image as a binary descriptor set.
CLEANUP_IMAGE=""
if [[ -n "${CONFORMANCE_IMAGE:-}" ]]; then
  # Use a caller-supplied descriptor (required in the bundled layout).
  if [[ ! -f "${CONFORMANCE_IMAGE}" ]]; then
    echo "error: CONFORMANCE_IMAGE=${CONFORMANCE_IMAGE} not found" >&2
    exit 1
  fi
  IMAGE="${CONFORMANCE_IMAGE}"
elif [[ -f "${REPO_ROOT}/buf.yaml" || -d "${REPO_ROOT}/geospatial" ]]; then
  # In-repo: build the descriptor from the proto source of truth.
  IMAGE="$(mktemp).binpb"
  CLEANUP_IMAGE="${IMAGE}"
  (cd "${REPO_ROOT}" && buf build -o "${IMAGE}")
else
  echo "error: no proto source tree found and CONFORMANCE_IMAGE is not set." >&2
  echo "       In a packaged fixture bundle, export CONFORMANCE_IMAGE to a" >&2
  echo "       descriptor built from the matching geospatial-grpc release," >&2
  echo "       e.g.: buf build -o image.binpb  (run in a geospatial-grpc checkout)" >&2
  exit 1
fi
trap '[[ -n "${CLEANUP_IMAGE}" ]] && rm -f "${CLEANUP_IMAGE}"' EXIT

pass=0
fail=0
failed_names=()

while read -r fixture type _rest; do
  # Skip comments and blank lines.
  [[ -z "${fixture}" || "${fixture}" == \#* ]] && continue

  fixture_path="${FIXTURE_DIR}/${fixture}"
  golden_path="${GOLDEN_DIR}/${fixture}"

  if [[ ! -f "${fixture_path}" ]]; then
    echo "FAIL ${fixture} — fixture file missing"
    fail=$((fail + 1))
    failed_names+=("${fixture}")
    continue
  fi

  # Round-trip JSON -> binary -> canonical JSON against the live schema.
  # A type that no longer exists, or a fixture field the schema can no longer
  # accept, makes this conversion fail.
  if ! actual="$(buf convert "${IMAGE}" --type "${type}" \
      --from "${fixture_path}#format=json" --to "-#format=json" 2>/tmp/convert.err)"; then
    echo "FAIL ${fixture} (${type}) — conversion failed:"
    sed 's/^/    /' /tmp/convert.err
    fail=$((fail + 1))
    failed_names+=("${fixture}")
    continue
  fi

  if [[ "${UPDATE}" -eq 1 ]]; then
    printf '%s\n' "${actual}" > "${golden_path}"
    echo "WROTE ${fixture} (${type})"
    pass=$((pass + 1))
    continue
  fi

  if [[ ! -f "${golden_path}" ]]; then
    echo "FAIL ${fixture} (${type}) — golden missing; run: conformance/run.sh --update"
    fail=$((fail + 1))
    failed_names+=("${fixture}")
    continue
  fi

  if [[ "${actual}" == "$(cat "${golden_path}")" ]]; then
    echo "PASS ${fixture} (${type})"
    pass=$((pass + 1))
  else
    echo "FAIL ${fixture} (${type}) — canonical output drifted from golden:"
    diff <(cat "${golden_path}") <(printf '%s\n' "${actual}") | sed 's/^/    /' || true
    fail=$((fail + 1))
    failed_names+=("${fixture}")
  fi
done < "${MANIFEST}"

echo
if [[ "${UPDATE}" -eq 1 ]]; then
  echo "Updated ${pass} golden(s)."
  exit 0
fi

echo "Conformance: ${pass} passed, ${fail} failed."
if [[ "${fail}" -gt 0 ]]; then
  echo "Drifted/failed fixtures: ${failed_names[*]}"
  echo "If this change is intentional, review the diff and run: conformance/run.sh --update"
  exit 1
fi
