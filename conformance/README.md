# Conformance fixtures and regression harness

This directory holds **canonical request/response fixtures** for the core
`geospatial.v1` workflows and a **contract-level regression harness** that
catches schema drift before it reaches downstream generated SDKs
(`honua-server`, `honua-sdk-dotnet`, and the other generated clients).

The harness is language-agnostic: it validates fixtures directly against the
`.proto` source of truth using `buf` (already pinned by CI), so it needs no
per-language code generation or runtime.

## Layout

```
conformance/
  VERSION                   # Fixture-set version (== proto/schema release; see below)
  fixtures/                 # Canonical workflow payloads (protobuf JSON mapping)
    manifest.txt            #   fixture file -> fully-qualified message type
    *_request.json          #   canonical request payloads
    *_response.json         #   canonical response payloads
  golden/                   # Canonical round-trip output, regenerated from the schema
  run.sh                    # Regression harness (in-repo or bundled mode)
  package.sh                # Builds the versioned, downloadable fixture artifact
  fetch-fixtures.sh         # Downstream helper: pull + verify a pinned version
  check-version.sh          # Asserts VERSION matches the .NET package <Version>
  README.md
```

## What is covered

Canonical fixtures exist for the core workflows of the primary services:

| Service            | Workflow                          | Fixtures                                              |
| ------------------ | --------------------------------- | ----------------------------------------------------- |
| `FeatureService`   | Query features                    | `feature_query_{request,response}.json`               |
| `FeatureService`   | Apply edits (add/update/delete)   | `feature_apply_edits_{request,response}.json`         |
| `FormService`      | Get form definition               | `form_get_definition_{request,response}.json`         |
| `FormService`      | Submit form data                  | `form_submit_{request,response}.json`                 |
| `ProcessService`   | Execute plan (synchronous)        | `process_execute_plan_{request,response}.json`        |
| `WorkspaceService` | Create workspace                  | `workspace_create_{request,response}.json`            |

Fixtures use the canonical [protobuf JSON
mapping](https://protobuf.dev/programming-guides/proto3/#json) (camelCase field
names, enum value names as strings, `int64` as strings). They double as
copy-paste reference payloads for the language examples and for downstream SDK
integration tests.

## How the harness works

For each entry in `fixtures/manifest.txt`, `run.sh`:

1. confirms the declared message type still exists in the schema;
2. round-trips the fixture JSON through the live schema
   (`JSON -> binary -> canonical JSON`) with `buf convert`, interpreting it
   against the current `.proto` definitions; and
3. compares the canonical JSON to the committed golden in `golden/`.

Because step 2 is interpreted against the current schema, **contract drift**
that changes the canonical JSON of a fixture — a changed field type, a dropped
enum value, or a removed/renamed field that a fixture exercises with a
non-default value — either fails the conversion or changes the canonical
output, so the golden comparison fails. This complements `buf breaking` (which
compares the schema to its own history) by asserting that *concrete, real-world
payloads for the canonical workflows* still behave as committed.

> **Detection scope.** The canonical protobuf JSON mapping omits proto3
> default-valued fields, and `buf convert` silently drops JSON keys the schema
> no longer recognizes (exit 0). A removed or renamed field is therefore only
> caught here when some fixture sets it to a **non-default** value; drift in a
> field that is absent — or present only with its proto3 default — in every
> fixture is not caught by this round-trip (`buf breaking` covers that case).
> To extend coverage to a field, add a fixture that exercises it with a
> non-default value.

## Running locally

```bash
# Verify all fixtures against their goldens.
conformance/run.sh

# Regenerate goldens after an intentional, reviewed schema change.
conformance/run.sh --update
```

The only requirement is `buf` on `PATH` (CI pins `1.66.0`).

## Versioning: fixtures are the published source of truth

The fixture set is **versioned** so that downstream SDKs
(`honua-sdk-dotnet`, `honua-sdk-js`, `honua-sdk-python`, `honua-mobile`) can pin
and pull the *same* canonical payloads instead of copying files out of this
repo's tree.

- The version lives in **`conformance/VERSION`** (e.g. `1.0.0`).
- It is the **same version** as the .NET protocol package
  (`src/Geospatial.Grpc/Geospatial.Grpc.csproj` `<Version>`). CI enforces this
  with `conformance/check-version.sh`, so a fixture version maps **1:1 to a
  `geospatial.v1` schema/proto release** — there is exactly one fixture set per
  release, and it is the set that was validated against that release's protos.
- On an exact stable release-tag push, CI packages the fixtures and attaches the
  artifact to a GitHub Release tagged **`v<VERSION>`** (e.g. `v1.0.0`). The
  release is created only after BSR and nuget.org public-consumption checks pass.

### The published artifact

`conformance/package.sh` builds a deterministic, downloadable tarball:

```
conformance-fixtures-<version>.tar.gz          # the fixture set
conformance-fixtures-<version>.tar.gz.sha256   # its SHA-256 checksum
```

The tarball expands to `conformance-fixtures-<version>/` containing:

```
VERSION         # the fixture-set version (== proto/schema release)
fixtures/       # canonical payloads + manifest.txt
golden/         # canonical round-trip goldens
run.sh          # the verification harness (bundled mode)
README.md       # this file
SHA256SUMS      # per-file checksums of everything in the bundle
```

It is attached as a release asset on the `v<version>` GitHub Release of
`honua-io/geospatial-grpc`. Build it locally with:

```bash
conformance/package.sh                 # version from conformance/VERSION
conformance/package.sh --version X.Y.Z # override
```

## Consuming a pinned fixture version (downstream SDKs)

A downstream consumer pulls an **exact** fixture version (never "latest", never
a git copy) with the bundled helper:

```bash
# In the consumer repo's CI, fetch a pinned version into ./conformance-fixtures/
conformance/fetch-fixtures.sh --version 1.0.0 --dest ./conformance-fixtures
```

`fetch-fixtures.sh`:

1. downloads `conformance-fixtures-<version>.tar.gz` (+ `.sha256`) from the
   `v<version>` GitHub Release of `honua-io/geospatial-grpc` (via `gh release
   download` if available, else `curl`/`wget`);
2. verifies the tarball SHA-256;
3. extracts it and re-verifies **every** file against the in-tarball
   `SHA256SUMS`;
4. asserts the embedded `VERSION` equals the requested pin;
5. leaves the verified `fixtures/`, `golden/`, `run.sh`, and `VERSION` in
   `--dest`.

Consumers do not need this repo checked out — copy `fetch-fixtures.sh` into the
consumer (or vendor it once) and call it with the pinned version. Equivalent raw
download, if you prefer not to use the helper:

```bash
v=1.0.0
base="https://github.com/honua-io/geospatial-grpc/releases/download/v${v}"
curl -fsSLO "${base}/conformance-fixtures-${v}.tar.gz"
curl -fsSLO "${base}/conformance-fixtures-${v}.tar.gz.sha256"
sha256sum -c "conformance-fixtures-${v}.tar.gz.sha256"
tar -xzf "conformance-fixtures-${v}.tar.gz"
```

### Verifying with the bundled harness

The bundled `run.sh` runs in **bundled mode** (it detects no proto tree beside
it). Supply a schema descriptor for the matching release via
`CONFORMANCE_IMAGE`:

```bash
# Build a descriptor from a pinned geospatial-grpc checkout/tag, or reuse the
# CI-published descriptor image:
buf build -o image.binpb            # run inside a geospatial-grpc checkout at v<version>

CONFORMANCE_IMAGE=image.binpb ./conformance-fixtures/conformance-fixtures-<version>/run.sh
```

In the Compatibility-Train model (epic #18), consumers additionally exercise the
`fixtures/` request payloads against a pinned `honua-server:nightly` and assert
the responses match the `golden/` set — failing CI on any drift (the
honua-server#1238 class of regression).

### How fixture versions map to releases

| Anchor | Value | Source |
| --- | --- | --- |
| Fixture set version | `conformance/VERSION` | this repo |
| .NET package version | `<Version>` in `Geospatial.Grpc.csproj` | enforced equal by `check-version.sh` |
| GitHub Release / tag | `v<VERSION>` | created by the `publish` job on `trunk` |
| Proto/schema state | the `geospatial/v1/*.proto` at that tag | round-tripped by the bundled `run.sh` |

To cut a new fixture release: make the reviewed schema change, run
`conformance/run.sh --update`, bump **both** `conformance/VERSION` and the
`.csproj` `<Version>` to the new release version, and merge. The `publish` job
packages and attaches the artifact to the `v<VERSION>` release automatically.

## Adding a fixture

1. Write the payload as protobuf JSON under `fixtures/` (use an existing fixture
   as a template).
2. Add a `fixture-file  fully.qualified.MessageType` line to
   `fixtures/manifest.txt`.
3. Run `conformance/run.sh --update` to generate the golden, then
   `conformance/run.sh` to confirm it passes.
4. Commit the fixture, the manifest entry, and the golden together.

## Reacting to a failure

A failing harness means a canonical payload no longer round-trips the same way.
Inspect the printed diff:

- **Unintended drift** (an accidental breaking change): fix the `.proto`.
- **Intentional change** (reviewed and deliberate): run
  `conformance/run.sh --update`, review the golden diff, and commit it alongside
  the schema change so reviewers can see the contract impact.
