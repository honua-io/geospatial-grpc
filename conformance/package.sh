#!/usr/bin/env bash
#
# Package the conformance fixture set into a versioned, downloadable artifact.
#
# Produces (under the output dir, default: dist/):
#
#   conformance-fixtures-<version>.tar.gz   the fixture set (see layout below)
#   conformance-fixtures-<version>.tar.gz.sha256   its SHA-256 checksum
#
# The tarball is the source-of-truth artifact that downstream SDK repos pin and
# pull (see conformance/README.md "Consuming a pinned fixture version"). It is
# attached to the matching `geospatial-grpc` GitHub Release by CI on tag push.
#
# Tarball layout (rooted at conformance-fixtures-<version>/):
#
#   VERSION                 the fixture-set version (== proto/schema release)
#   fixtures/               canonical request/response payloads + manifest.txt
#   golden/                 canonical round-trip goldens
#   run.sh                  the language-agnostic verification harness
#   README.md               this directory's docs
#   SHA256SUMS              per-file checksums of every packaged file
#
# A consumer can therefore run the *exact* harness that produced the goldens
# against the *exact* fixtures, with no dependency on the repo git tree.
#
# Usage:
#   conformance/package.sh                 # version from conformance/VERSION
#   conformance/package.sh --version X.Y.Z # override version
#   conformance/package.sh --output DIR    # override output dir (default dist/)
#
# Requirements: tar, sha256sum (coreutils), GNU/BSD tar.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF_DIR="${REPO_ROOT}/conformance"

VERSION=""
OUTPUT_DIR="${REPO_ROOT}/dist"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      echo "usage: $0 [--version X.Y.Z] [--output DIR]" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${VERSION}" ]]; then
  if [[ ! -f "${CONF_DIR}/VERSION" ]]; then
    echo "error: conformance/VERSION not found and --version not given" >&2
    exit 1
  fi
  VERSION="$(tr -d '[:space:]' < "${CONF_DIR}/VERSION")"
fi

if [[ -z "${VERSION}" ]]; then
  echo "error: empty version" >&2
  exit 1
fi

for tool in tar sha256sum; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "error: ${tool} not found on PATH" >&2
    exit 1
  fi
done

STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

PKG_NAME="conformance-fixtures-${VERSION}"
PKG_ROOT="${STAGE}/${PKG_NAME}"
mkdir -p "${PKG_ROOT}"

# Stage the source-of-truth contents.
cp -R "${CONF_DIR}/fixtures" "${PKG_ROOT}/fixtures"
cp -R "${CONF_DIR}/golden" "${PKG_ROOT}/golden"
cp "${CONF_DIR}/run.sh" "${PKG_ROOT}/run.sh"
cp "${CONF_DIR}/README.md" "${PKG_ROOT}/README.md"
printf '%s\n' "${VERSION}" > "${PKG_ROOT}/VERSION"
chmod +x "${PKG_ROOT}/run.sh"

# Per-file checksums (stable, sorted) so consumers can verify any single file.
(
  cd "${PKG_ROOT}"
  find . -type f ! -name SHA256SUMS -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 sha256sum > SHA256SUMS
)

mkdir -p "${OUTPUT_DIR}"
TARBALL="${OUTPUT_DIR}/${PKG_NAME}.tar.gz"

# Deterministic tarball: fixed mtime/owner, sorted entries, no gzip timestamp.
TAR_MTIME="2020-01-01 00:00:00"
if tar --version 2>/dev/null | grep -qi 'gnu tar'; then
  tar --sort=name \
      --mtime="${TAR_MTIME}" \
      --owner=0 --group=0 --numeric-owner \
      -C "${STAGE}" -cf "${STAGE}/${PKG_NAME}.tar" "${PKG_NAME}"
  gzip -n -9 -c "${STAGE}/${PKG_NAME}.tar" > "${TARBALL}"
else
  # BSD/macOS tar fallback: no --sort, still reproducible enough for release use.
  tar -C "${STAGE}" -czf "${TARBALL}" "${PKG_NAME}"
fi

(
  cd "${OUTPUT_DIR}"
  sha256sum "${PKG_NAME}.tar.gz" > "${PKG_NAME}.tar.gz.sha256"
)

echo "Packaged ${PKG_NAME}:"
echo "  ${TARBALL}"
echo "  ${TARBALL}.sha256"
echo
cat "${TARBALL}.sha256"
