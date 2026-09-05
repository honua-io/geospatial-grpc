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
4. **Published generated clients share one version.** `Geospatial.Grpc`,
   `geospatial-grpc` on PyPI, and `@honua/geospatial-grpc` on npm are built from
   the same tagged schema. Their manifest versions and `conformance/VERSION`
   move together. See the
   [generated-client publication runbook](generated-client-publication.md).
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
- [ ] **Bump the release version** in `src/Geospatial.Grpc/Geospatial.Grpc.csproj`,
  `packages/python/pyproject.toml`, `packages/typescript/package.json`, and
  `conformance/VERSION` following the minor/patch rules in
  [VERSIONING.md](../VERSIONING.md#version-numbering). The release tag must match
  this value exactly (`v<Version>`), as enforced by the publish
  workflow.
- [ ] **Examples and docs updated** for any observable behavior change.
- [ ] **Downstream impact noted in the PR description**: list the SDKs/repos that
  must regenerate (cross-reference [proto-ownership.md](proto-ownership.md)'s
  consumer table) and link or open the tracking issue.

## Release Checklist (after merge to `trunk`)

- [ ] **Confirm repository rules require CI before merge.** The `trunk`
  ruleset must require the CI workflow/status checks; defining the jobs in the
  repository does not make them required in GitHub settings.
- [ ] **Confirm CI is green on `trunk`** (lint, breaking, format, multi-language
  generation, descriptor export, .NET pack).
- [ ] **Confirm immutable tag authority.** The active `v*` tag ruleset must deny
  tag updates and deletions without bypasses, and the `production` environment
  must admit only selected `v*` tags. This release contract intentionally does
  not treat a cryptographic Git tag signature as an identity invariant: the
  protected immutable GitHub ref, tag-triggered Actions identity, and workflow
  checks that tag, checkout, and `GITHUB_SHA` resolve to one commit are the
  accepted authority boundary.
- [ ] **Provision production credentials before tagging**:
  - Ensure the BSR owner `honua-io` exists (an organization, or a user account
    holding that name — the module path is identical either way; the CLI can
    create the module but not a missing owner), then issue a `BUF_TOKEN` that
    can create/push the public `buf.build/honua-io/geospatial-grpc` module.
    `BUF_TOKEN` is an Actions secret on the `production` environment.
  - nuget.org uses **Trusted Publishing — no long-lived `NUGET_API_KEY` secret
    exists or may be created.** On nuget.org, configure (or when rotating
    ownership, re-create) a Trusted Publishing policy for publisher
    GitHubActions, repository `honua-io/geospatial-grpc`, workflow
    `publish-dotnet-protocol.yml`, environment `production`, package glob
    `Geospatial.Grpc*`. The publish job exchanges its OIDC identity for a
    short-lived key via `NuGet/login`; the policy's `user:` on the login step
    must match the nuget.org account holding the policy.
  - The workflow fails before publishing either registry when the `BUF_TOKEN`
    secret is absent or the Trusted Publishing exchange yields no key.
  - `PYPI_API_TOKEN` can create/publish `geospatial-grpc`, and `NPM_TOKEN` can
    publish public packages under `@honua`. These are also Actions secrets
    available to the `production` environment; see the generated-client
    [operator checklist](generated-client-publication.md#first-publish-operator-checklist).
- [ ] **Run validation-only** with `workflow_dispatch`. A manual run never
  publishes; inspect the packed `.nupkg`, `.snupkg`, conformance artifact, and
  local install smoke result.
- [ ] **Tag the release once**: `v<Version>`, where `<Version>` matches both the
  `.csproj` and `conformance/VERSION`. Pushing this exact tag triggers
  `publish-dotnet-protocol.yml`; do not create a `geospatial-grpc-v*` tag.
- [ ] **Verify the registry transaction**:
  - occupied BSR/NuGet coordinates are accepted only when their public content
    matches the artifact built from the tag;
  - the BSR `v<Version>` label resolves to a recorded immutable commit;
  - nuget.org contains the exact runtime package and accepts the `.snupkg`;
  - a fresh job with no registry credentials builds the BSR commit and restores
    and compiles `Geospatial.Grpc <Version>` using nuget.org alone.
- [ ] **Verify the GitHub release is evidence-complete**. It must target the
  tagged commit and contain the `.nupkg`, `.snupkg`, immutable BSR archive,
  conformance tarball/checksum, clean-consumption result,
  `release-receipt.json`, and `SHA256SUMS`. If a job fails, use GitHub's
  **Re-run failed jobs** action so the successful build job and its immutable
  artifacts are reused. Do not use **Re-run all jobs**: NuGet pack archives are
  not guaranteed byte-identical across independent builds, and the workflow
  deliberately refuses to overwrite same-name build evidence. Re-runs of the
  downstream failed jobs compare an existing release byte-for-byte instead of
  silently replacing assets.
- [ ] **Record the released coordinate** on the tracking issue: tag, package
  version, Git commit, immutable BSR commit, release receipt URL, and downstream
  pins.

### How release-consumer restores are hash-locked

Both release acceptance restores use `--locked-mode` with the reviewed
third-party dependency versions and hashes in
`.github/requirements/dotnet-smoke.lock.json`. Before the first restore,
`.github/scripts/prepare-nuget-smoke-lock.py` verifies that the release package's
identity and dependency declarations match that contract, then binds only its
version and hash to the already verified artifact. Dependency changes require
an explicit lock update; the workflow never learns third-party hashes from a
fresh resolution during the release.

The local smoke consumes the just-built package through a dedicated source
mapping. Before the public smoke, the workflow compares the repository-signed
nuget.org payload against that build and checks the immutable BSR commit. The
public lock uses NuGet's unsigned content hash from the retained build artifact;
repository signing preserves that content identity. The consumer still has
only nuget.org, no registry credentials, and fresh package and HTTP caches;
different package contents or dependency hashes fail the locked restore.

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
