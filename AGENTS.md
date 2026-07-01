# AGENTS.md

## Overview

`geospatial-grpc` is the **canonical, open-source home for shared gRPC/Protobuf
protocol definitions** for geospatial data access, mobile data collection, and
execution workflows (Honua ecosystem). It is a **schema/contract repository** —
there is no server or application logic here. The `.proto` files are the source
of truth; downstream repos (`honua-server`, `honua-sdk-dotnet`, etc.) generate
or pin clients from them and must not own independent copies.

Protocol package: `geospatial.v1`. License: Apache-2.0.

## Tech Stack

- **Protocol Buffers / gRPC** — definitions in `geospatial/v1/*.proto`.
- **[Buf](https://buf.build)** — lint, format, breaking-change checks, code
  generation, and registry publishing. CI pins **buf `1.66.0`**.
- **.NET** — `src/Geospatial.Grpc/` packs a NuGet protocol package
  (`Geospatial.Grpc`), targeting **netstandard2.0**, built with the **.NET 10
  SDK (`10.0.x`)** in CI. Uses `Grpc.Tools` to compile protos at build time.
- **Examples** in .NET (net10.0), Python, and TypeScript/JavaScript.
- Code generation targets (via Buf remote plugins): C#, Go, Java, Python,
  TypeScript (Connect-ES), Rust, Swift, plus API docs.

## Setup

No repo-local install for the protos themselves. Install the toolchains you need:

```bash
# Buf CLI (used for all proto validation/generation)
npm install -g @bufbuild/buf      # or download the pinned 1.66.0 binary

# .NET SDK 10.0.x (only for the Geospatial.Grpc package / dotnet examples)
```

## Commands

All Buf commands run from the repo root.

```bash
# Lint protobuf
buf lint

# Format check (CI uses --exit-code; fails on unformatted files)
buf format --diff --exit-code
buf format -w                       # auto-format in place

# Breaking-change check against trunk
buf breaking --against '.git#branch=trunk'

# Generate all configured languages into gen/ (uses buf.gen.yaml)
buf generate

# Generate a single language (per-language templates)
buf generate --template buf.gen.go.yaml --output generated/go
buf generate --template buf.gen.csharp.yaml --output generated/csharp
# also: buf.gen.python.yaml, buf.gen.javascript.yaml, buf.gen.java.yaml

# Build schema descriptors
buf build -o descriptors/image.bin
buf build -o descriptors/image.json

# Publish to Buf registry (CI only, needs BUF_TOKEN)
buf push
```

.NET protocol package (from repo root):

```bash
# Pack the NuGet package (CI adds /p:TreatWarningsAsErrors=true)
dotnet pack src/Geospatial.Grpc/Geospatial.Grpc.csproj --configuration Release -o ./nupkgs
```

Examples (each in its own directory):

```bash
cd examples/javascript && npm install && npm run generate && npm run dev
cd examples/python && pip install -r requirements.txt && python main.py
cd examples/dotnet && dotnet run
```

Schema validation is `buf lint` / `buf breaking` / `buf format` plus the .NET
pack/build smoke test in CI. The `conformance/` directory adds a language-
agnostic regression harness — canonical workflow fixtures that are round-tripped
against the live schema with `buf convert` to catch contract drift:

```bash
conformance/run.sh            # verify fixtures against committed goldens
conformance/run.sh --update   # regenerate goldens after a reviewed schema change
```

## Architecture

Each service lives in its own `.proto` and follows a validate / dry-run /
execute pattern. Shared types are factored into `*_types.proto` files.

Core services (all under `geospatial.v1`):

- `FeatureService` — geospatial feature CRUD, query, streaming.
- `FormService` — mobile data collection (dynamic forms, validation).
- `WorkspaceService` / `ArtifactService` — workspace & artifact lifecycle.
- `ProcessService` / `PipelineService` — process & data-publishing execution.
- `RenderService` — map composition, produces `MapPackage`.
- `BuilderService` — app bundle synthesis, produces `AppPackage`.
- `DeploymentService` — promotion, rollback, health telemetry.
- `SpecService` — spec plan/apply workflows.

Shared type modules: `common.proto`, `spatial_types.proto`,
`execution_types.proto`, `scene_types.proto`, `packaging_types.proto`,
`workspace_artifact_types.proto`.

Generation flow: `buf.gen.yaml` (v2) drives multi-language output to `gen/`
with managed-mode package prefixes (`github.com/geospatial-grpc/proto-go`,
`io.grpc.geospatial`, C# base namespace `GeospatialGrpc`). The .NET package
instead compiles the protos directly via `Grpc.Tools` (`GrpcServices=Both`).

## Directory Layout

```
geospatial/v1/          # Protocol definitions (source of truth)
  *_service.proto       #   one service per file
  *_types.proto, common.proto, spatial_types.proto  # shared messages/enums
src/Geospatial.Grpc/    # .NET NuGet protocol package project
examples/dotnet|python|javascript/   # language usage samples
conformance/            # canonical workflow fixtures + buf-based regression harness
docs/                   # specification, getting-started, proto-ownership, features
.github/workflows/      # ci.yml, publish-dotnet-protocol.yml
buf.yaml                # Buf module config (lint/breaking rules)
buf.gen.yaml            # All-language generation template (v2)
buf.gen.<lang>.yaml     # Per-language generation templates
VERSIONING.md, CONTRIBUTING.md
gen/                    # Generated client libraries (output, not committed source)
```

## Conventions & Gotchas

- **Schema-first / canonical source.** Change protos here first; do not edit
  downstream `.proto` copies. See `docs/proto-ownership.md`.
- **Backward compatibility (`geospatial.v1`):** prefer additive changes; never
  reuse field numbers; reserve removed field numbers/names; do not rename
  fields, messages, services, or enum values. Breaking changes require a new
  version path (e.g. `geospatial/v2`). `buf breaking` uses the `WIRE_JSON`
  ruleset plus `RPC_NO_DELETE` and `PACKAGE_SERVICE_NO_DELETE` (WIRE_JSON alone
  does not catch RPC/service deletion or rename;
  `conformance/breaking-gate-test.sh` guards that in CI).
- **Typed ref pattern:** new writes should use `WorkspaceRef`, `ArtifactRef.*`,
  and `ExecutionContext.workspace`; legacy string fields exist only for v1
  wire/JSON compatibility.
- **Lint:** `buf.yaml` uses the `STANDARD` ruleset minus `ENUM_VALUE_PREFIX`,
  `ENUM_ZERO_VALUE_SUFFIX`, `RPC_REQUEST_RESPONSE_UNIQUE`,
  `RPC_REQUEST_STANDARD_NAME`, `RPC_RESPONSE_STANDARD_NAME`.
- **Version mismatch to be aware of:** `buf.yaml` declares `version: v1` while
  the generation templates use `version: v2`. Match the existing file's version
  when editing either.
- **CI must pass formatting** (`buf format --diff --exit-code`), lint, breaking
  (on PRs), multi-language generation, descriptor export, and the .NET pack —
  all with the pinned buf `1.66.0` and .NET `10.0.x`.
- **.NET package builds with `TreatWarningsAsErrors=true`** and all analyzers
  enabled (`AnalysisMode=AllEnabledByDefault`); generated/compiled proto code
  must stay warning-clean. Bump `<Version>` in the `.csproj`; the publish
  workflow requires the `geospatial-grpc-v*` tag version to match it exactly.

## Shared dev-environment rules (multi-agent WSL)

This machine runs many agents concurrently (**Codex + Claude**, often via agentflow with multiple tabs/agents). To prevent host lockups and lost work, every agent MUST follow these:

1. **Heavy builds/tests are throttled by a shared lock.** `dotnet` and `npm` are PATH-shimmed, so their build/test/publish/pack and ci/install/test/run-build/run-test subcommands automatically run under a global semaphore (default 1 concurrent, `HONUA_BUILD_SLOTS`). For other heavy tools, call the wrapper explicitly: `with-build-lock pytest ...`, `with-build-lock cargo build`, `with-build-lock make build`. The lock is shared across ALL of this user's processes (every Codex/Claude tab, agentflow children). Do not bypass it for compiles or test suites. Long-running servers (`dotnet run`, `npm run dev`) are intentionally NOT locked — never wrap those.

2. **Commit and push when you finish a task** so your worktree can be reclaimed. An hourly job (`honua-clean`) removes a worktree ONLY when it is clean AND fully pushed (merged, remote-gone, or idle >=2d). Dirty or unpushed worktrees are NEVER touched — but uncommitted/unpushed work blocks reclamation and is at risk if the instance is reset. Build artifacts (bin/obj and untracked node_modules) are reclaimed automatically and safely.

3. **Commit hygiene — no agent attribution.** Author every commit as the repo owner only (git identity: Mike McDougall <mike@honua.io>). Do **NOT** add any agent/tool attribution to commits: no `Co-Authored-By: Claude ...`, no `Co-Authored-By: Codex ...` (or other bot co-authors), and no "Generated with Claude Code" / "Generated with Codex" / "🤖" lines in the message or PR body. Write a plain, descriptive commit message and stop.
