# Versioning and Schema Evolution Policy

This document governs how the `geospatial.v1` proto surface evolves.
It is the canonical reference for maintainers and contributors making proto changes.

## Version Numbering

| Component | Format | Example |
|-----------|--------|---------|
| Proto package | `geospatial.v<MAJOR>` | `geospatial.v1` |
| Git release tag | `v<MAJOR>.<MINOR>.<PATCH>` | `v1.2.0` |

- **MAJOR** — matches the proto package major version (currently `1`).
- **MINOR** — additive proto surface changes (new fields, enums, RPCs, messages).
- **PATCH** — documentation-only, comment, or config changes with no proto surface impact.

> **Note:** Earlier releases used CalVer tags (`v<YYYY.MM.DD>-<hash>`).
> New releases follow semver. Existing CalVer tags remain for historical reference.

## Compatibility Guarantees Within a Major Version

Within `geospatial.v1`, all tagged releases guarantee:

- **Wire compatibility** — existing serialized messages remain deserializable.
- **JSON mapping stability** — field names used in JSON serialization do not change.
- **Field number stability** — numbers are never reused for different semantics.
- **Enum value stability** — numeric values are never reused for different semantics.
- **RPC surface stability** — method names, request types, and response types do not change.

**Not guaranteed:**

- Generated source-code API names (language plugin concern).
- Default values of newly added fields.
- Ordering of elements in repeated fields.

**Consumer contract:** any tag within the same MAJOR version is safe to upgrade without application code changes.

## Change Classification

| Category | Examples | Version Bump | Process |
|----------|----------|:------------:|---------|
| **Additive** | New optional field, new enum value, new RPC, new message, new service | Minor | Standard PR review |
| **Additive-with-care** | New field in a `oneof`, new proto file in `geospatial/v1/` | Minor | PR description must note impact on generated `switch`/`match` |
| **Documentation** | Comment changes, spec updates | Patch | Standard PR review |
| **Breaking** | Remove/rename field, change field type/number, move field into/out of `oneof`, change streaming direction, change request/response type, reuse reserved number | New major | Full governance gate (see below) |

## Deprecation Policy

1. Add the `[deprecated = true]` field option to the element.
2. Add a comment: `// Deprecated since v1.<MINOR>. Use <replacement> instead. Removal target: v2.`
3. The deprecated annotation must remain for **at least two subsequent minor releases** before removal in the next major version.
4. Deprecated elements must continue to function identically on the wire within their major version.

## Field Number Reservation

When a field is removed in a new major version:

1. Add `reserved <number>;` and `reserved "<field_name>";` to the message.
2. Document the removal version and reason in a comment above the reservation.
3. Reserved numbers and names must never be reused.

Within a major version, fields are never removed — only deprecated (see above).

## Breaking Change Governance

Breaking changes follow a structured process:

1. **Proposal** — open a GitHub issue titled `Breaking change proposal: <summary>` with label `breaking-change-proposal`. Include:
   - What changes and why.
   - Affected messages, fields, or RPCs.
   - Migration path for consumers.
   - Cross-language impact, specifically C# / .NET AOT and trimming considerations.

2. **Deprecation first** — the element must be deprecated in `v1` per the deprecation policy above before removal.

3. **Maintainer approval** — at least one maintainer must comment `LGTM-breaking` on the proposal issue.

4. **New package** — create `geospatial/v2/` alongside `geospatial/v1/`. The prior major version is frozen (critical fixes only). Both coexist in the repository.

5. **CI update** — update `buf.yaml` breaking-check configuration for per-package baselines.

6. **Migration guide** — the PR must include `docs/migration-v1-to-v2.md`.

## Release Process

- Every merge to `trunk` that modifies `.proto` files should result in a tagged semver release.
- Documentation-only changes may be batched into a single patch release.

## CI Enforcement

The following automated checks run on every PR and are not optional (they are
required status checks on the `trunk` branch protection):

| Check | Purpose |
|-------|---------|
| `buf lint` | Style and API design rules (DEFAULT category, minus documented exceptions) |
| `buf breaking --against '.git#branch=<base>'` | Wire + JSON compatibility against the target branch (PR) |
| `buf breaking --against '.git#tag=<prev-release>'` | Wire + JSON compatibility against the previous release tag (push to `trunk`) |
| `buf format --diff --exit-code` | Consistent formatting |
| `conformance/check-version.sh` | `conformance/VERSION` matches the .NET package `<Version>` |
| `conformance/run.sh` | Canonical workflow payloads still round-trip against the live schema |

### Breaking-change gate coverage

The `buf breaking` gate (`WIRE_JSON` + `RPC_NO_DELETE` +
`PACKAGE_SERVICE_NO_DELETE` rules in `buf.yaml`) runs on **two paths** so a
wire/JSON-breaking proto edit (removed/renamed field, changed type or number,
dropped enum value, reused reserved number) **or a removed/renamed RPC or
service** cannot land:

- **Pull requests** — `buf breaking --against '.git#branch=<base>'` compares the
  PR head to its target branch. This is the primary required check.
- **Direct push to `trunk`** — `buf breaking --against '.git#tag=<prev-release>'`
  compares the pushed state to the most recent `v*` release tag, so a breaking
  change cannot slip in via a non-PR push. (If no release tag exists yet, there
  is no baseline and the push-time check is a no-op.)

`WIRE_JSON` alone does **not** include the RPC/service no-delete rules — the
gRPC method path `/geospatial.v1.<Service>/<Method>` is part of the wire
contract, so `RPC_NO_DELETE` and `PACKAGE_SERVICE_NO_DELETE` are added to close
that gap. `conformance/breaking-gate-test.sh` (run in CI) asserts the gate
actually catches RPC/service deletion and rename, so the config cannot silently
regress to a permissive gate.

CI catches accidental breakage. This policy adds the human governance layer for **intentional** breakage, deprecation tracking, field reservation, and consumer-facing compatibility promises.

## Conformance fixtures as a released artifact

The conformance fixtures (`conformance/`) ride the **same release version** as
the proto surface and the .NET package. `conformance/VERSION` equals the
`Geospatial.Grpc` `<Version>` (CI-enforced by `conformance/check-version.sh`),
so one fixture set maps 1:1 to one `geospatial.v1` schema release. On push to
`trunk`, the `publish` job packages the fixtures and attaches
`conformance-fixtures-<version>.tar.gz` (+ `.sha256`) to a GitHub Release tagged
`v<version>`. Downstream consumers pull a pinned version with
`conformance/fetch-fixtures.sh --version <version>`. See
`conformance/README.md` for the full consumer contract.
