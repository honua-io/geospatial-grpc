# Geospatial gRPC Protocol Standard

[![CI](https://github.com/honua-io/geospatial-grpc/actions/workflows/ci.yml/badge.svg)](https://github.com/honua-io/geospatial-grpc/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/honua-io/geospatial-grpc/badge)](https://scorecard.dev/viewer/?uri=github.com/honua-io/geospatial-grpc)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/honua-io/geospatial-grpc?include_prereleases)](https://github.com/honua-io/geospatial-grpc/releases)

An open, vendor-neutral gRPC/Protobuf protocol standard for geospatial systems:
feature access, mobile data collection, styles, elevation, 3D scenes/tiles, and
execution workflows (processes, pipelines, rendering, app building, deployment).
Existing geospatial interop standards are REST/XML-first; this project defines
the equivalent contracts as strongly typed, streaming-capable gRPC services so
servers and clients in any language can interoperate over one schema.

This is a **schema/contract repository** — the `.proto` files under
[`geospatial/v1/`](geospatial/v1/) are the source of truth. There is no server
or application code here; implementations and SDKs generate clients from these
definitions ([ownership rules](docs/proto-ownership.md)).

## Status

**Stable v1.** `v1.0.0` closes the pre-release stabilization window. The full
within-major compatibility guarantees in [VERSIONING.md](VERSIONING.md) now
apply without exception. Every PR is gated by `buf lint`, `buf format`,
`buf breaking` (WIRE_JSON + RPC/service no-delete rules), multi-language
codegen, and a conformance-fixture round-trip.

## What the standard defines

All services live in the `geospatial.v1` package, one service per file. Each
execution-plane service follows a validate / dry-run / execute pattern.

| Service | Purpose |
|---------|---------|
| `FeatureService` | Feature CRUD: query, server-streaming pages, batch edits |
| `FormService` | Mobile data collection: dynamic forms, validation, submission |
| `WorkspaceService` | Workspace lifecycle: create/open/list, promote, retain/release, quotas |
| `ArtifactService` | Artifact lifecycle: publish/read/inspect, retention policies |
| `ProcessService` | Geospatial process execution: plan validation, dry-run, sync/streaming/async |
| `PipelineService` | Data publishing pipelines: validation, dry-run, stage-by-stage execution |
| `RenderService` | Map composition; produces MapLibre-compatible `MapPackage` bundles |
| `BuilderService` | Application bundle synthesis; produces `AppPackage` bundles |
| `DeploymentService` | Promotion to live targets with health telemetry and rollback |
| `SpecService` | Declarative spec plan/apply workflows with streaming progress |
| `StyleService` | 2D style catalog: `StyleRef` styles with typed encodings (MapLibre, SLD, Esri drawing info) |
| `ElevationService` | Point elevation and geodesic profile sampling |
| `SceneService` | 3D scene catalog backed by 3D Tiles tilesets and optional terrain |
| `TileService` | 3D tile delivery by node, or streamed by LOD and extent |

Shared type modules: `common.proto`, `spatial_types.proto` (geometries with
Z/M support), `execution_types.proto` (plans, steps, jobs, provenance,
structured errors), `packaging_types.proto` (`MapPackage`, `AppPackage`,
`DeploymentSpec`), `workspace_artifact_types.proto` (typed
`WorkspaceRef`/`ArtifactRef`/`RetentionPolicyRef` handles and lifecycle enums),
`style_types.proto`, and `scene_types.proto`.

The full capability map is in [docs/features/README.md](docs/features/README.md);
message-level detail is in the [protocol specification](docs/specification.md).

## Quick start

### Generate client code

```bash
git clone https://github.com/honua-io/geospatial-grpc.git
cd geospatial-grpc

# Install the Buf CLI (https://buf.build/docs/installation), e.g.:
npm install -g @bufbuild/buf

# Generate every configured language from the immutable stable public schema
buf generate buf.build/honua-io/geospatial-grpc:v1.0.0
# gen/csharp, gen/go, gen/java, gen/python, gen/rust, gen/swift, gen/typescript

# Or generate the local checkout / a single language with its dedicated template
buf generate
buf generate --template buf.gen.go.yaml --output generated/go
# also: buf.gen.csharp.yaml, buf.gen.python.yaml, buf.gen.javascript.yaml, buf.gen.java.yaml
```

`gen/` is build output — it is never committed; regenerate it from the protos.

### .NET: use the published protocol package

gRPC remains **supported for 2026.1**. The `Geospatial.Grpc` NuGet package
(netstandard2.0, protos compiled via `Grpc.Tools`) releases through
[GitHub Packages](https://github.com/orgs/honua-io/packages?repo_name=geospatial-grpc).
Historical versions remain on [nuget.org](https://www.nuget.org/packages/Geospatial.Grpc).
Downstream .NET projects should pin a published version instead of copying protos.

Add this `nuget.config` beside the consumer project. The mapping resolves
`Geospatial.Grpc` from GitHub Packages and other dependencies from nuget.org:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="github" value="https://nuget.pkg.github.com/honua-io/index.json" />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
  <packageSourceMapping>
    <packageSource key="github"><package pattern="Geospatial.Grpc" /></packageSource>
    <packageSource key="nuget.org"><package pattern="*" /></packageSource>
  </packageSourceMapping>
</configuration>
```

GitHub's NuGet registry requires authentication even for public packages.
For local restores, have the operator supply a personal access token (classic)
with `read:packages` and package access through a credential provider or the
`NuGetPackageSourceCredentials_github` environment variable, whose format is
`Username=GITHUB_LOGIN;Password=TOKEN;ValidAuthenticationTypes=Basic`.
Never commit credentials to `nuget.config` or print them in logs.
In GitHub Actions, use `GITHUB_TOKEN` with `packages: read` and grant the consumer
repository read access under the package's **Manage Actions access** settings.
See [GitHub NuGet authentication](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-nuget-registry).

Replace `X.Y.Z` with an exact version listed in GitHub Packages:

```bash
dotnet add package Geospatial.Grpc --version X.Y.Z
```

You can also pack it locally:

```bash
dotnet pack src/Geospatial.Grpc/Geospatial.Grpc.csproj --configuration Release -o ./nupkgs
```

The [.NET GitHub Packages workflow](.github/workflows/publish-dotnet-github-packages.yml)
packs and verifies a synthetic prerelease on every PR to `trunk`; manual runs
also only pack. Pushing a `vMAJOR.MINOR.PATCH[-PRERELEASE]` tag packs that SemVer,
attests the runtime and symbol archives, then pushes the exact runtime archive
using only `GITHUB_TOKEN` with `packages: write`. Build metadata (`+...`) is
rejected because NuGet strips it from package identity. An occupied version
fails publication; choose a new version instead of overwriting a release.
The workflow is independent of the legacy BSR/nuget.org release credentials.
Symbol archives remain in the workflow artifact; GitHub Packages does not serve
`.snupkg` symbols. Verify a downloaded archive's provenance with:

```text
gh attestation verify Geospatial.Grpc.X.Y.Z.nupkg --repo honua-io/geospatial-grpc
```

### First query

.NET:

```csharp
using Geospatial.V1;
using Grpc.Net.Client;

using var channel = GrpcChannel.ForAddress("https://api.example.com");
var client = new FeatureService.FeatureServiceClient(channel);

var response = await client.QueryFeaturesAsync(new QueryFeaturesRequest
{
    ServiceId = "parcels",
    LayerId = 0,
    Where = "AREA > 1000",
    ReturnGeometry = true
});

foreach (var feature in response.Features)
{
    Console.WriteLine($"Feature {feature.Id}: {feature.Attributes}");
}
```

TypeScript (protobuf-es + Connect v2):

```typescript
import { FeatureService } from './gen/typescript/geospatial/v1/feature_service_pb.js';
import { createClient } from '@connectrpc/connect';
import { createGrpcTransport } from '@connectrpc/connect-node';

const transport = createGrpcTransport({ baseUrl: 'https://api.example.com' });
const client = createClient(FeatureService, transport);

const response = await client.queryFeatures({
  serviceId: 'parcels',
  layerId: 0,
  where: 'AREA > 1000',
  returnGeometry: true,
});

response.features.forEach((feature) => {
  console.log(`Feature ${feature.id}:`, feature.attributes);
});
```

Python:

```python
import grpc
from geospatial.v1 import feature_service_pb2
from geospatial.v1 import feature_service_pb2_grpc

channel = grpc.secure_channel('api.example.com:443', grpc.ssl_channel_credentials())
client = feature_service_pb2_grpc.FeatureServiceStub(channel)

response = client.QueryFeatures(feature_service_pb2.QueryFeaturesRequest(
    service_id='parcels',
    layer_id=0,
    where='AREA > 1000',
    return_geometry=True,
))
for feature in response.features:
    print(f'Feature {feature.id}: {feature.attributes}')
```

Runnable end-to-end samples live in [`examples/`](examples/):

| Example | Run |
|---------|-----|
| [JavaScript/TypeScript](examples/javascript/) | `npm install && npm run generate && npm run dev` |
| [Python](examples/python/) | `pip install -r requirements.txt && python main.py` |
| [.NET](examples/dotnet/) | `dotnet run` |

## Conformance suite

[`conformance/`](conformance/) holds canonical request/response fixtures for
the core workflows plus a language-agnostic regression harness that round-trips
them against the live schema with `buf convert` — catching contract drift
before it reaches generated SDKs:

```bash
conformance/run.sh            # verify fixtures against committed goldens
conformance/run.sh --update   # regenerate goldens after a reviewed schema change
```

Each schema release publishes the fixture set as a versioned, checksummed
tarball on the matching [GitHub Release](https://github.com/honua-io/geospatial-grpc/releases)
(`conformance-fixtures-<version>.tar.gz`). Implementations pin a version with
`conformance/fetch-fixtures.sh --version <version>` and run the bundled harness
in their own CI. See [conformance/README.md](conformance/README.md) for the
consumer contract.

## Versioning and stability

[VERSIONING.md](VERSIONING.md) is the canonical policy. In short:

- Proto package majors (`geospatial.v1`) align with release-tag majors.
- Within a major: wire compatibility, JSON mapping stability, field/enum number
  stability, and RPC surface stability are guaranteed between tagged releases.
- Breaking changes require deprecation first, maintainer sign-off, and a new
  package version path (`geospatial/v2`) — enforced in CI by `buf breaking`
  on every PR and on every push to `trunk` against the previous release tag.
- The historical pre-1.0 exception is closed. It remains documented only to
  explain the alpha baselines; it cannot be used for `v1` changes.

## Implementing the standard

1. Generate server stubs for your language (`buf generate`, or the per-language
   templates).
2. Implement the services relevant to your product — the standard does not
   require every service.
3. Validate payload compatibility against the pinned
   [conformance fixtures](conformance/README.md) in your CI.
4. Follow [CONTRIBUTING.md](CONTRIBUTING.md) to propose schema changes —
   contracts evolve here first, never in downstream copies
   ([proto ownership](docs/proto-ownership.md)).

Known implementations and clients:

- [Honua Server](https://github.com/honua-io/honua-server) — reference server implementation (ELv2)
- [Honua .NET SDK](https://github.com/honua-io/honua-sdk-dotnet) and [Honua Mobile](https://github.com/honua-io/honua-mobile) — .NET / MAUI clients
- [Honua JS SDK](https://github.com/honua-io/honua-sdk-js) — JavaScript/TypeScript clients
- Your implementation here — PRs welcome.

## Documentation

| Document | Contents |
|----------|----------|
| [Protocol specification](docs/specification.md) | Design principles and per-service protocol detail |
| [Getting started](docs/getting-started.md) | Tooling setup and per-language walkthroughs |
| [Feature map](docs/features/README.md) | Implemented protocol surfaces and boundaries |
| [Proto ownership](docs/proto-ownership.md) | Canonical-source and downstream sync rules |
| [Versioning policy](VERSIONING.md) | Compatibility guarantees and breaking-change governance |
| [Release checklist](docs/release-checklist.md) | Release coordination and client regeneration |
| [Changelog](CHANGELOG.md) | Release history, including acknowledged alpha baselines |

## Related projects

- [geospatial-mcp](https://github.com/honua-io/geospatial-mcp) — companion open standard: geospatial tools over the Model Context Protocol
- [geobench](https://github.com/honua-io/geobench) — vendor-neutral benchmark suite for geospatial servers

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for local
validation (`buf lint`, `buf format --diff --exit-code`,
`buf breaking --against '.git#branch=trunk'`), the proto change workflow, and
what must not change within `v1`. Questions and proposals go through
[GitHub Issues](https://github.com/honua-io/geospatial-grpc/issues).

## Security

Report vulnerabilities privately to [security@honua.io](mailto:security@honua.io)
— see the [security policy](https://github.com/honua-io/.github/blob/main/SECURITY.md).
Do not open public issues for security reports.

## License

[Apache License 2.0](LICENSE).
