# Release Checklist and Generated-Client Coordination

This document is the canonical release-coordination contract for `geospatial-grpc`.
Its purpose is to ensure that proto changes never strand downstream SDKs: every
change that touches the wire surface has an explicit, repeatable path from a
merged `.proto` edit to regenerated, published, and consumed client artifacts.

It complements two existing documents and does not duplicate them:

- [VERSIONING.md](../VERSIONING.md) — *what* counts as additive vs. breaking,
  version numbering, deprecation, and breaking-change governance.
- [docs/proto-ownership.md](proto-ownership.md) — *who* owns which contract and
  the downstream-repo sync rules.

This checklist is the *when and how* of releasing: the owner workflow and the
gate a proto change passes through before downstream SDKs regenerate.

## Audience and Roles

| Role | Who | Responsibility |
| --- | --- | --- |
| **Proto owner** | Author of the proto PR in this repo | Drives the change through this checklist end to end, including coordinating downstream regeneration. Owns the change until every affected SDK consumes it. |
| **Maintainer / reviewer** | A `geospatial-grpc` maintainer | Verifies CI is green, the change is correctly classified, and the downstream coordination plan exists before merge. |
| **Downstream SDK owner** | Owner of `honua-server`, `honua-sdk-dotnet`, `honua-mobile`, etc. | Regenerates/pins clients from the released revision and confirms back on the tracking issue. |

The proto owner stays accountable for the change until downstream regeneration
is confirmed. "Merged" is not "done"; "consumed by every affected SDK" is.

## Generated-Client Expectations (explicit, not tribal)

These are the standing expectations for what a proto change must produce.

1. **The protos are the only source of truth.** No downstream repo edits a local
   `.proto`; they generate or pin from a tagged revision / Buf digest / published
   package of this repo. See [proto-ownership.md](proto-ownership.md).
2. **Every wire-surface change is released, not just merged.** A change to any
   `geospatial/v1/*.proto` that affects the wire or JSON surface results in a
   tagged semver release (see [VERSIONING.md](../VERSIONING.md#release-process)),
   so downstream consumers have a stable coordinate to pin to.
3. **Generation targets stay in lockstep.** The change must regenerate cleanly
   for every configured language in `buf.gen.yaml` (C#, Go, TypeScript, Java,
   Python, Rust, Swift, plus API docs). CI runs `buf generate`; a target that
   no longer generates is a release blocker, not a follow-up.
4. **The .NET package is the reference SDK.** `src/Geospatial.Grpc/` packs the
   `Geospatial.Grpc` NuGet package and must build warning-clean under
   `TreatWarningsAsErrors=true`. Its `<Version>` is bumped in the same PR as the
   proto change (see the per-change steps below).
5. **Examples and docs move with the surface.** When a change alters or adds
   observable behavior, update the affected entries under `examples/` and the
   relevant `docs/` (`specification.md`, `features/README.md`, generated
   `docs/api`).
6. **Coordination is recorded, not remembered.** A tracking issue captures the
   released coordinate (commit, Buf digest, package version, or tag) and the
   per-downstream regeneration status. Tribal knowledge is not a coordination
   mechanism.

## Pre-Merge Checklist (proto owner, in this repo)

Run before requesting review / merging the proto PR.

- [ ] **Classify the change** per the table in
  [VERSIONING.md](../VERSIONING.md#change-classification): Additive,
  Additive-with-care, Documentation, or Breaking. Breaking changes follow the
  governance gate in VERSIONING.md and do **not** use this fast-path checklist —
  they create a new package path (`geospatial/v2`) and a migration guide.
- [ ] **Local validation passes** (pinned buf `1.66.0`):
  - [ ] `buf format --diff --exit-code`
  - [ ] `buf lint`
  - [ ] `buf breaking --against '.git#branch=trunk'`
  - [ ] `buf generate` (all `buf.gen.yaml` targets regenerate cleanly)
- [ ] **.NET package** packs and builds warning-clean:
  `dotnet pack src/Geospatial.Grpc/Geospatial.Grpc.csproj --configuration Release -o ./nupkgs /p:TreatWarningsAsErrors=true`
- [ ] **Bump the package version** in `src/Geospatial.Grpc/Geospatial.Grpc.csproj`
  (`<Version>`) following the minor/patch rules in
  [VERSIONING.md](../VERSIONING.md#version-numbering). The release tag must match
  this value exactly (`geospatial-grpc-v<Version>`), as enforced by the publish
  workflow.
- [ ] **Examples and docs updated** for any observable behavior change.
- [ ] **Downstream impact noted in the PR description**: list the SDKs/repos that
  must regenerate (cross-reference [proto-ownership.md](proto-ownership.md)'s
  consumer table) and link or open the tracking issue.

## Release Checklist (after merge to `trunk`)

- [ ] **Confirm CI is green on `trunk`** (lint, breaking, format, multi-language
  generation, descriptor export, .NET pack).
- [ ] **Tag the release**: `geospatial-grpc-v<Version>`, where `<Version>`
  matches the `.csproj` `<Version>` exactly. Pushing this tag triggers
  `publish-dotnet-protocol.yml`.
- [ ] **Verify the publish workflow** succeeds: package smoke (pack + install
  smoke against a fresh `net10.0` project) and publish to GitHub Packages.
  - A `workflow_dispatch` with `dry_run: true` validates packaging without
    publishing if you want a pre-tag check.
- [ ] **Publish Buf artifacts** if the registry is in use for this change
  (`buf push`, CI-side, needs `BUF_TOKEN`); record the resulting module digest.
- [ ] **Record the released coordinate** on the tracking issue: tag, `.csproj`
  version, commit SHA, and Buf digest (whichever downstream consumers will pin).

## Downstream Coordination Checklist (per affected SDK)

The proto owner drives this; the downstream SDK owner executes and confirms.
This mirrors the per-repo steps in
[proto-ownership.md](proto-ownership.md#downstream-sync-checklist).

- [ ] For each consumer in scope (`honua-server`, `honua-sdk-dotnet`,
  `honua-mobile`, `honua-server-admin`, …): open or link a downstream issue/PR
  that pins the new released coordinate.
- [ ] Downstream regenerates or updates package references (.NET consumers use
  the `Geospatial.Grpc` NuGet package; others use generated artifacts / Buf
  digest).
- [ ] Downstream runs its compile, analyzer, and protocol integration tests
  against the new revision.
- [ ] Downstream confirms back on the tracking issue; the proto owner marks that
  consumer done.
- [ ] **Close the loop**: the change is "done" only when every affected SDK has
  confirmed consumption (or explicitly deferred with a tracked follow-up).

## Quick Reference: which doc do I need?

| Question | Document |
| --- | --- |
| Is my change additive or breaking? How do I version/deprecate it? | [VERSIONING.md](../VERSIONING.md) |
| Who owns this contract? What must each downstream repo do? | [proto-ownership.md](proto-ownership.md) |
| What are the steps to release and coordinate regeneration? | **This document** |
