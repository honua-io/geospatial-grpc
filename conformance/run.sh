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
# any contract drift that changes the wire/JSON shape of a canonical workflow
# message — a removed or renamed field, a changed type, a dropped enum value —
# either fails the conversion or changes the canonical output, so the golden
# comparison fails. This catches drift in this repo before it reaches the
# downstream generated SDKs.
#
# Usage:
#   conformance/run.sh            # verify all fixtures against goldens
#   conformance/run.sh --update   # regenerate goldens from current schema
#
# Requirements: `buf` on PATH (CI pins 1.66.0). No language toolchains needed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="${REPO_ROOT}/conformance/fixtures"
GOLDEN_DIR="${REPO_ROOT}/conformance/golden"
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

# Build the schema descriptor once and reuse it for every conversion. The
# .binpb suffix tells buf to treat the image as a binary descriptor set.
IMAGE="$(mktemp).binpb"
trap 'rm -f "${IMAGE}"' EXIT
(cd "${REPO_ROOT}" && buf build -o "${IMAGE}")

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
