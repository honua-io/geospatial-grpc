#!/usr/bin/env bash
# Prove the stable schema and NuGet package from public endpoints only.

set -euo pipefail

VERSION=""
BSR_COMMIT=""
REPO_ROOT=""
OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="${2:-}"; shift 2 ;;
    --bsr-commit) BSR_COMMIT="${2:-}"; shift 2 ;;
    --root) REPO_ROOT="${2:-}"; shift 2 ;;
    --output) OUTPUT="${2:-}"; shift 2 ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "${VERSION}" || -z "${BSR_COMMIT}" || -z "${REPO_ROOT}" || -z "${OUTPUT}" ]]; then
  echo "usage: $0 --version VERSION --bsr-commit COMMIT --root ROOT --output FILE" >&2
  exit 2
fi
if [[ ! "${VERSION}" =~ ^[1-9][0-9]*\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: invalid stable version: ${VERSION}" >&2
  exit 1
fi
if [[ ! "${BSR_COMMIT}" =~ ^[0-9a-f]{32}$ ]]; then
  echo "error: invalid immutable BSR commit: ${BSR_COMMIT}" >&2
  exit 1
fi
if [[ -n "${BUF_TOKEN:-}" || -n "${NUGET_API_KEY:-}" ]]; then
  echo "error: clean public consumption must run without registry credentials" >&2
  exit 1
fi

for tool in buf curl dotnet python3 sha256sum; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "error: ${tool} not found on PATH" >&2
    exit 1
  }
done

CONSUMER_DIR="$(mktemp -d)"
trap 'rm -rf "${CONSUMER_DIR}"' EXIT
APP_DIR="${CONSUMER_DIR}/app"
mkdir -p "${APP_DIR}" "${CONSUMER_DIR}/packages" "${CONSUMER_DIR}/dotnet-cli"

BSR_ARCHIVE="${CONSUMER_DIR}/geospatial-grpc-${BSR_COMMIT}.zip"
BSR_URL="https://buf.build/honua-io/geospatial-grpc/archive/${BSR_COMMIT}.zip"
curl -fsSL --retry 5 --retry-all-errors --retry-delay 5 \
  -o "${BSR_ARCHIVE}" "${BSR_URL}"
python3 "${REPO_ROOT}/scripts/verify_bsr_archive.py" \
  --root "${REPO_ROOT}" --archive "${BSR_ARCHIVE}" --json >/dev/null

# This resolves the immutable BSR commit on a credential-free machine and proves
# it is a valid Buf input, independently of the downloaded archive comparison.
buf build "buf.build/honua-io/geospatial-grpc:${BSR_COMMIT}" \
  -o "${CONSUMER_DIR}/public-schema.binpb"

cat > "${APP_DIR}/NuGet.config" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" protocolVersion="3" />
  </packageSources>
</configuration>
EOF

cat > "${APP_DIR}/PublicConsumer.csproj" <<EOF
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0</TargetFramework>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Geospatial.Grpc" Version="${VERSION}" />
    <PackageReference Include="Grpc.Net.Client" Version="2.80.0" />
  </ItemGroup>
</Project>
EOF

cat > "${APP_DIR}/Program.cs" <<'EOF'
using Geospatial.V1;
using Grpc.Net.Client;

using var channel = GrpcChannel.ForAddress("https://example.invalid");
_ = new FeatureService.FeatureServiceClient(channel);
_ = new ProcessService.ProcessServiceClient(channel);
_ = new SpecService.SpecServiceClient(channel);
_ = new QueryFeaturesRequest
{
    ServiceId = "parks",
    LayerId = 0,
    ReturnGeometry = true,
    OutSr = new SpatialReference { Wkid = 4326 }
};
EOF

export DOTNET_CLI_HOME="${CONSUMER_DIR}/dotnet-cli"
export NUGET_PACKAGES="${CONSUMER_DIR}/packages"
export NUGET_HTTP_CACHE_PATH="${CONSUMER_DIR}/http-cache"
# Keep the public-only restore fresh, with reviewed third-party hashes and the
# unsigned content hash of the build compared by check_public_registry.py.
# NuGet preserves that content hash when it repository-signs the public package.
python3 "${REPO_ROOT}/.github/scripts/prepare-nuget-smoke-lock.py" \
  --package "${REPO_ROOT}/release-inputs/Geospatial.Grpc.${VERSION}.nupkg" \
  --version "${VERSION}" --output "${APP_DIR}/packages.lock.json"
dotnet restore "${APP_DIR}/PublicConsumer.csproj" \
  --configfile "${APP_DIR}/NuGet.config" --no-cache --locked-mode
dotnet build "${APP_DIR}/PublicConsumer.csproj" \
  --configuration Release --no-restore /p:TreatWarningsAsErrors=true

mkdir -p "$(dirname "${OUTPUT}")"
SCHEMA_SHA256="$(sha256sum "${CONSUMER_DIR}/public-schema.binpb" | awk '{print $1}')"
python3 - "${OUTPUT}" "${VERSION}" "${BSR_COMMIT}" "${SCHEMA_SHA256}" <<'PY'
import json
import sys
from pathlib import Path

output, version, bsr_commit, schema_sha256 = sys.argv[1:]
receipt = {
    "schemaVersion": 1,
    "status": "passed",
    "credentialFree": True,
    "version": version,
    "bsrCommit": bsr_commit,
    "bsrDescriptorImageSha256": schema_sha256,
    "nugetSource": "https://api.nuget.org/v3/index.json",
    "bsrRef": f"buf.build/honua-io/geospatial-grpc:{bsr_commit}",
}
Path(output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "Public BSR and NuGet consumption passed for v${VERSION} (${BSR_COMMIT})."
