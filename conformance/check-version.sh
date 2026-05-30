#!/usr/bin/env bash
#
# Assert the conformance fixture version is a single, consistent source of truth.
#
# The fixture-set version lives in conformance/VERSION and MUST equal the .NET
# protocol package <Version> in src/Geospatial.Grpc/Geospatial.Grpc.csproj, so
# a fixture set is unambiguously tied to one proto/schema release (see
# VERSIONING.md). CI runs this so the two can never drift apart silently.
#
# Usage: conformance/check-version.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_FILE="${REPO_ROOT}/conformance/VERSION"
CSPROJ="${REPO_ROOT}/src/Geospatial.Grpc/Geospatial.Grpc.csproj"

if [[ ! -f "${VERSION_FILE}" ]]; then
  echo "error: ${VERSION_FILE} not found" >&2
  exit 1
fi

fixture_version="$(tr -d '[:space:]' < "${VERSION_FILE}")"
if [[ -z "${fixture_version}" ]]; then
  echo "error: conformance/VERSION is empty" >&2
  exit 1
fi

if [[ ! -f "${CSPROJ}" ]]; then
  echo "error: ${CSPROJ} not found" >&2
  exit 1
fi

# Extract the first <Version>...</Version> from the csproj.
csproj_version="$(grep -oE '<Version>[^<]+</Version>' "${CSPROJ}" \
  | head -n1 \
  | sed -E 's#</?Version>##g' \
  | tr -d '[:space:]')"

if [[ -z "${csproj_version}" ]]; then
  echo "error: could not read <Version> from ${CSPROJ}" >&2
  exit 1
fi

if [[ "${fixture_version}" != "${csproj_version}" ]]; then
  echo "error: conformance fixture version drift detected." >&2
  echo "  conformance/VERSION         = ${fixture_version}" >&2
  echo "  Geospatial.Grpc <Version>   = ${csproj_version}" >&2
  echo "Bump both together so the fixture set maps to one schema release." >&2
  exit 1
fi

echo "Conformance fixture version OK: ${fixture_version} (matches Geospatial.Grpc <Version>)."
