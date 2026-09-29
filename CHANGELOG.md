# Changelog

All notable changes to the `geospatial.v1` proto surface and its generated
client packages are recorded here. A single git release tag (`v<version>`)
identifies the matching NuGet, PyPI, npm, BSR, and `conformance/VERSION`
coordinates.

## v1.0.4

Conformance fixture and certification-harness release. There are no `.proto`,
wire-surface or generated-API changes from `v1.0.3`.

### Fixtures for every governed 2026.1 RPC

The 2026.1 scope ruling (#88) governs the 14 RPCs that honua-server implements.
v1.0.3 had live fixtures for only QueryFeatures and ApplyEdits. v1.0.4 adds the
other twelve:

- `FeatureService/QueryFeaturesStream`: `feature_query_stream_{request,response.1}.json`.
- `ProcessService/ValidatePlan`, `DryRunPlan`, `SubmitJob`, `GetJob`,
  `GetJobResult` and `CancelJob`: a one-step `geometry.buffer` plan, with
  `process_*` request and response fixtures for each RPC.
- `SpecService/PlanSpec`, `ApplySpec` and `CancelApply`: a two-node
  `compute.noop` document where `report` depends on `source` through `@source`.
  `spec_apply_response.N.json` holds one file per streamed event.
- `ElevationService/GetElevation` and `GetElevationProfile`, sampled over a
  synthetic elevation layer.

Streamed responses are stored one message per file (`<name>.N.json`), in order,
so every file is still a single protobuf message in the manifest. Requests may
carry `{{capture:<name>}}` tokens for ids a server assigns earlier in a
workflow, for example the job id `SubmitJob` returns. The certification runners
substitute the captured value into the request and into the expected response,
so an echoed id is compared exactly.

### Certification harness

- `certification/scenarios.v1.json` declares every scenario the .NET, Python and
  TypeScript runners execute: unary and server-streaming calls, captures, setup
  calls, polling until a job reaches a terminal state, and the ApplyEdits
  negative case. The runners are driven by that file and the installed
  package's own descriptors, so the three lanes execute the same scenarios.
- `server-assigned-fields.v1.json` lists the new server-assigned values (job
  and result ids, plan ids, spec content hashes, timestamps, raster ids and
  measured durations and bytes). Test coverage extends to every scenario, and
  bound echoes are never masked.
- `certification/seed/sf-parks.sql` seeds elevation layer 4701 (10 x column +
  row metres on a 0.01 degree grid). The certification workflow adds the Redis
  job substrate and runs the server with `Licensing__Mode=Disabled`, the 2026.1
  supported deployment mode.

## v1.0.3

Conformance fixture and certification-harness release. There are no `.proto`,
wire-surface or generated-API changes from `v1.0.2`.

### Fixture changes

- `feature_apply_edits_{request,response}.json` follow all-or-nothing batch
  semantics (`rollbackOnFailure: true`). The positive batch adds one feature,
  updates 42 and deletes 7, and every edit succeeds. The previous fixture mixed
  a failed delete of the missing feature 8 with successful edits, which a batch
  that fails as a whole can never return.
- New negative case `feature_apply_edits_missing_target_request.json`. A batch
  that updates 42 and deletes 7 and the missing 8 must fail as a whole with the
  gRPC status in `feature_apply_edits_missing_target_status.json` (`NOT_FOUND`)
  and apply no edit. The runners then read 7 and 42 back with
  `feature_apply_edits_missing_target_verify_{request,response}.json` and
  require the seeded values exactly, which proves the rejected batch left every
  target unchanged.
- `feature_service.proto` documents the `rollback_on_failure` contract (comment
  only, no wire change), and `docs/specification.md` gains an "ApplyEdits batch
  semantics" section. A batch whose update or delete names a missing feature
  fails as a whole with gRPC status `NOT_FOUND` and applies no edit.

### Certification harness

- `certification/server-assigned-fields.v1.json` lists the response values a
  server assigns and a fixture cannot predict: created feature ids, workspace
  ids and revisions, timestamps, job, result and artifact ids, and durations.
  The .NET, Python and TypeScript runners replace those values, and only
  those, with a placeholder before comparing. The value must still be present.
  `optional_operations` lists server-assigned values that may validly be the
  proto3 default, which the JSON mapping omits (an execution duration of zero
  seconds). Those paths are removed from both documents instead.
  `tests/test_server_assigned_fields.py` checks that every listed path resolves
  in the expected response and never covers a value the request supplied. The
  wire-oracle suite checks that a listed value may differ, that a listed value
  may not be missing, and that a client-supplied id is still compared.

## v1.0.2

Republishes the v1.0.1 content. The `v1.0.1` tag never reached nuget.org:
the pre-publish install smoke refused the package because
`.github/requirements/dotnet-smoke.lock.json` still pinned the v1.0.0
dependency graph (`Google.Protobuf` 3.35.1, `Grpc.Core.Api` 2.80.0). Release
tags are immutable, so the fix ships under a new patch version. There are no
`.proto`, fixture or generated-API changes from `v1.0.1`.

### Fixes

- The consumer smoke lock now pins `Google.Protobuf` 3.36.2 and
  `Grpc.Core.Api` 2.84.0, the dependencies the package declares.
- CI's .NET pack job runs the same lock binding on every change, so a
  dependency bump that leaves the lock stale fails before a tag is cut.

## v1.0.1

Patch release for the conformance fixture set. There are no `.proto`,
wire-surface or generated-API changes from `v1.0.0`. The packages are rebuilt so
`conformance/VERSION`, the release tag and every package version stay a single
coordinate, and they pick up the dependency and packaging changes merged since
`v1.0.0` (listed below).

### Fixes

- `workspace_create_request.json` and `workspace_create_response.json` bound the
  retention policy as `defaultRetention.ref.retentionPolicyId`. `RetentionPolicyRef`
  has no `ref` field, so generated clients rejected the fixtures and the
  goldens silently recorded an empty `defaultRetention`. They now set
  `defaultRetention.retentionPolicyId`. A regression test fails CI when any
  fixture value is dropped as an unknown key (#88).

### Dependency and packaging changes

- `Geospatial.Grpc` raises its minimum runtime dependencies:
  `Google.Protobuf` 3.35.1 to 3.36.2 and `Grpc.Core.Api` 2.80.0 to 2.84.0. The
  private build-time `Grpc.Tools` compiler moves from 2.81.1 to 2.84.0.
- The `Geospatial.Grpc` package now includes the `LICENSE` file.
- The Python package builds with `setuptools` 83.0.0 and `wheel` 0.46.2, and
  declares its license as `license = { text = "Apache-2.0" }`.
- Install examples in the package READMEs, the root README and
  `docs/getting-started.md` reference 1.0.1.

## v1.0.0

**First stable release.** This release promotes the `geospatial.v1` schema
settled in `v0.2.0-alpha.1` to the permanent v1 compatibility contract in
[VERSIONING.md](VERSIONING.md). There are no wire-surface changes from that
alpha baseline.

### Distribution contract

- `Geospatial.Grpc 1.0.0` is built once, smoke-tested from the packed artifact,
  and published with its `.snupkg` to nuget.org from the same `v1.0.0` tag.
- Generated `geospatial-grpc==1.0.0` Python and
  `@honua/geospatial-grpc@1.0.0` TypeScript clients are built once from that
  tag, smoke-tested locally, and published through independent fail-closed
  PyPI/npm workflows with anonymous public-consumption proof.
- `buf.build/honua-io/geospatial-grpc:v1.0.0` resolves to an immutable BSR
  commit. The public archive is compared byte-for-byte with the canonical local
  README, license, and proto files before the release is declared complete.
- `conformance-fixtures-1.0.0.tar.gz`, the `.nupkg`, `.snupkg`, registry
  receipt, and checksums are attached to the `v1.0.0` GitHub release.
- Release publication fails closed when either registry credential is absent,
  a version is already occupied by different content, a public restore fails,
  or the BSR/NuGet verification receipt cannot be produced.

The pre-1.0 exception is now closed. Breaking changes require a new protocol
package (`geospatial.v2`) and the governance process in VERSIONING.md.

## v0.2.0-alpha.1

**Acknowledged breaking baseline (pre-1.0).** Implements
[issue #48](https://github.com/honua-io/geospatial-grpc/issues/48) Option A:
promotes shared job-lifecycle control-plane messages into `execution_types.proto`
and converges `SpecService` onto the shared execution surface. This is the
pre-v1 window identified in issue #48 and authorised under the
[historical pre-1.0 exception](VERSIONING.md#historical-pre-10-exception-closed)
in VERSIONING.md.

The `buf breaking --against '.git#branch=trunk'` gate will flag this PR as
expected — it is a sanctioned break. After this PR merges to trunk, cut tag
`v0.2.0-alpha.1` immediately so the push-time gate (`buf breaking --against
'.git#tag=v0.2.0-alpha.1'`) has a clean baseline for all subsequent additive
changes.

### Shared control-plane messages (Commit 1)

Eight control-plane messages that were copy-pasted identically across all five
operator services are promoted into `execution_types.proto` and all five services
now use the shared types:

| New shared message | Replaces (per-service duplicates) |
|--------------------|-----------------------------------|
| `ValidateResponse` | `ValidatePlanResponse`, `ValidatePipelineResponse`, `ValidateRenderResponse`, `ValidateBuildResponse`, `ValidateDeploymentResponse` |
| `DryRunResponse` | `DryRunPlanResponse`, `DryRunPipelineResponse`, `DryRunRenderResponse`, `DryRunBuildResponse`, `DryRunDeploymentResponse` |
| `SubmitJobResponse` | `SubmitJobResponse` (Process, moved), `SubmitPipelineJobResponse`, `SubmitRenderJobResponse`, `SubmitBuildJobResponse`, `SubmitDeploymentJobResponse` |
| `GetJobRequest` | `GetJobRequest` (Process, moved), `GetPipelineJobRequest`, `GetRenderJobRequest`, `GetBuildJobRequest`, `GetDeploymentJobRequest` |
| `GetJobResponse` | `GetJobResponse` (Process, moved), `GetPipelineJobResponse`, `GetRenderJobResponse`, `GetBuildJobResponse`, `GetDeploymentJobResponse` |
| `GetJobResultRequest` | `GetJobResultRequest` (Process, moved), `GetPipelineJobResultRequest`, `GetRenderJobResultRequest`, `GetBuildJobResultRequest`, `GetDeploymentJobResultRequest` |
| `CancelJobRequest` | `CancelJobRequest` (Process, moved), `CancelPipelineJobRequest`, `CancelRenderJobRequest`, `CancelBuildJobRequest`, `CancelDeploymentJobRequest` |
| `CancelJobResponse` | `CancelJobResponse` (Process, moved), `CancelPipelineJobResponse`, `CancelRenderJobResponse`, `CancelBuildJobResponse`, `CancelDeploymentJobResponse` |

**RPC signature changes** (wire-breaking per WIRE_JSON ruleset):

- All five services: `Validate*` RPCs now return `ValidateResponse` instead of
  `Validate*Response`.
- All five services: `DryRun*` RPCs now return `DryRunResponse` instead of
  `DryRun*Response`.
- PipelineService, RenderService, BuilderService, DeploymentService:
  `Submit*Job` RPCs now return `SubmitJobResponse`.
- PipelineService, RenderService, BuilderService, DeploymentService:
  `Get*Job` RPCs now take `GetJobRequest` and return `GetJobResponse`.
- PipelineService, RenderService, BuilderService, DeploymentService:
  `Get*JobResult` RPCs now take `GetJobResultRequest`.
- PipelineService, RenderService, BuilderService, DeploymentService:
  `Cancel*Job` RPCs now take `CancelJobRequest` and return `CancelJobResponse`.

**Drift reconciliations** (no structural drift was found, only naming drift):

- All five Validate* responses had identical fields `(bool valid, repeated
  PlanValidationIssue issues)` with no numbering or naming discrepancy.
  Reconciled to `ValidateResponse`.
- All five DryRun* responses had identical fields `(bool valid, repeated
  PlanValidationIssue issues, DryRunResult result)` with no drift.
  Reconciled to `DryRunResponse`.
- All five Submit*Job responses had identical fields `(string job_id,
  JobState state)`. No drift.
- All five Get*Job request/response pairs were structurally identical.
  No drift.
- All five Cancel*Job pairs were structurally identical. No drift.
- DeploymentService intentionally carries `DeploymentOperationMode
  operation_mode` in its validate/dryrun/execute/submit _requests_ (not
  in responses). This is a legitimate semantic difference that is **not**
  reconciled — the operation mode is DeploymentService-specific and the
  per-service request messages remain service-specific by design.
- ProcessService's existing `SubmitJobResponse`, `GetJobRequest`,
  `GetJobResponse`, `GetJobResultRequest`, `CancelJobRequest`, and
  `CancelJobResponse` already had the target names; they are moved to
  `execution_types.proto` without name change (not a breaking name change,
  just a file relocation within the same proto package).

**Per-service result messages** (`GetJobResultResponse` family and `Execute*Response`
/ `*Event` streaming messages) remain service-specific because they carry
per-service result types in a `oneof outcome` discriminator.

**`ErrorDetail` extension** (additive, non-breaking):

- `Severity severity = 9` — diagnostic severity for surfaces that classify
  errors by severity (e.g., SpecService warnings). Execution-phase terminal
  errors implicitly have ERROR severity; callers may leave this unset.
- `string remedy = 10` — optional remediation hint, used by SpecService
  diagnostics.

**`DryRunResult` extension** (additive, non-breaking):

- `int64 estimated_rows = 5`, `int64 estimated_bytes = 6`,
  `double estimated_duration_ms = 7` — per-node estimation fields for
  dependency-DAG workflows (SpecService).
- `int64 actual_rows = 8`, `int64 actual_bytes = 9`,
  `double actual_duration_ms = 10` — per-node actual execution metrics for
  streaming apply events (SpecService).

### SpecService convergence (Commit 2)

- **`string maps → ParameterValue`** (`CanonicalSpecNode.inputs` and
  `.parameters`). These were `map<string, string>` carrying canonicalized spec
  fragments; they are now `map<string, ParameterValue>`. String fragments are
  carried as `string_value` branches. `source_pins` remains `map<string, string>`
  (content-hash values, not typed parameters).
- **`SpecCostEstimate` retired → `DryRunResult`** (`SpecPlanNode.cost`).
  Per-node estimates now populate the `estimated_rows/bytes/duration_ms` fields
  (5-7) of `DryRunResult`.
- **`SpecCostActual` retired → `DryRunResult`** (`ApplySpecEvent.actual_cost`).
  Per-node actuals now populate the `actual_rows/bytes/duration_ms` fields (8-10)
  of `DryRunResult`.
- **`SpecDiagnostic` retired → `ErrorDetail`** (`SpecPlanNode.warnings`,
  `SpecPlan.warnings`, `ApplySpecEvent.diagnostic`). The `severity` and `remedy`
  fields that `SpecDiagnostic` previously added around `ErrorDetail` are now
  carried directly in `ErrorDetail` fields 9 and 10.
- **`apply_token` → `job_id`** (`ApplySpecEvent`). Field 3 (`apply_token`) is
  reserved; `string job_id = 10` is the new identifier. Clients use `job_id`
  in `CancelJobRequest` to cancel an in-flight apply.
- **`CancelApply` uses shared types**. The RPC signature changes from
  `CancelApply(CancelApplyRequest) returns (CancelApplyResponse)` to
  `CancelApply(CancelJobRequest) returns (CancelJobResponse)`. The former
  `bool cancelled = 1` field in `CancelApplyResponse` is replaced by
  `JobState state = 2` in `CancelJobResponse`; `JOB_STATE_CANCELLED` conveys
  the same information.
- `spec_service.proto` no longer imports `common.proto` directly (Severity is
  transitively available through `execution_types.proto` → `common.proto`).

### Migration checklist for consumers

**honua-server** (proto-generating services):

- Rename response types for all `Validate*` and `DryRun*` handler methods
  to `ValidateResponse` / `DryRunResponse`.
- Rename per-service control-plane request/response types:
  `Get*JobRequest → GetJobRequest`, `Get*JobResponse → GetJobResponse`,
  `Get*JobResultRequest → GetJobResultRequest`,
  `Cancel*JobRequest → CancelJobRequest`, `Cancel*JobResponse → CancelJobResponse`,
  `Submit*JobResponse → SubmitJobResponse`.
- Remove any local shim that mapped per-service types to identical structures.
- Update SpecService: `CancelApply` handler now takes `CancelJobRequest`
  (read `job_id` instead of `apply_token`), returns `CancelJobResponse`
  (emit `job_id` + `JOB_STATE_CANCELLED` instead of `bool cancelled`).
- Update SpecService: emit `job_id` in `ApplySpecEvent.job_id` (field 10);
  do not populate the removed `apply_token` field.
- Update SpecService: populate `CanonicalSpecNode.inputs` / `.parameters`
  with `ParameterValue` entries (wrap string fragments in `string_value`).
- Update SpecService: populate `SpecPlanNode.cost` as `DryRunResult` with
  per-node fields; populate `SpecPlanNode.warnings` and `SpecPlan.warnings`
  as `repeated ErrorDetail` with `severity` set.
- Update SpecService: populate `ApplySpecEvent.actual_cost` as `DryRunResult`
  with `actual_rows/bytes/duration_ms` fields.
- Update SpecService: populate `ApplySpecEvent.diagnostic` as `ErrorDetail`
  with `severity` and optional `remedy` fields.

**honua-sdk-dotnet** and **geospatial-mcp**:

- Regenerate from `v0.2.0-alpha.1`. The generated C# / TypeScript stubs will
  pick up renamed types automatically. Update any hand-written code that
  referenced the now-removed per-service control-plane message names.

### Notes

- `.NET` package `<Version>` and `conformance/VERSION` bumped to
  `0.2.0-alpha.1` (kept in lock-step; enforced by
  `conformance/check-version.sh`).

---

## v0.1.0-alpha.3

**Acknowledged breaking baseline (pre-1.0).** This release establishes the
finalized pre-v1 wire contract as the new `buf breaking` baseline. The proto
changes themselves landed earlier on `trunk` in
[#55](https://github.com/honua-io/geospatial-grpc/pull/55) ("finalize pre-v1
wire contract") and [#58](https://github.com/honua-io/geospatial-grpc/pull/58);
`v0.1.0-alpha.2` was tagged before those merged, so the push-time breaking gate
was comparing `trunk` against a stale baseline. This release re-baselines the
gate on the intended contract. These are deliberate, one-time pre-v1 breaks; no
`geospatial/v2` is created.

### Breaking (wire + JSON) vs `v0.1.0-alpha.2`

- **Canonical error model (`ErrorDetail`, `execution_types.proto`).**
  `ErrorDetail` is now the single application-error type. Its canonical core is
  `int32 code = 1; string message = 2; map<string,string> details = 3;`
  followed by the execution-context fields (`ErrorCategory category = 4`,
  `string phase = 5`, `string node_id = 6`, `Retryability retryability = 7`,
  `string suggested_action = 8`). Field 1 changed from `string error_code` to
  `int32 code` (numeric codes aligned with GeoServices/Esri REST semantics), and
  fields 2–8 were reordered/retyped to place the canonical core first. The
  string-code variants are removed.
- **`FeatureService` error unification (`feature_service.proto`).** The former
  `EditError` message is retired; `ApplyEditsResponse.error` and
  `EditResult.error` now carry `ErrorDetail`.
- **`SpecService` (`spec_service.proto`).** `SpecDiagnostic` embeds
  `ErrorDetail` (numeric code) instead of a string code.
- **Single `Severity` enum (`common.proto`).** One ascending `Severity`
  (`SEVERITY_UNSPECIFIED=0, INFO=1, WARNING=2, ERROR=3`) replaces
  `IssueSeverity`, `ValidationSeverity`, and `SpecDiagnosticSeverity`; the
  previously inverted `INFO`/`ERROR` orderings are fixed. Affected fields:
  `PlanValidationIssue.severity`, `ValidationRule.severity`,
  `ValidationIssue.severity`, `QualityRule.severity`, `QualityIssue.severity`.
- **Token-based pagination.** `page_size` (int32) + `page_token` (string) with
  `next_page_token` on responses is standardized across list RPCs. The
  `int32 result_offset` / `result_record_count` pattern is removed from
  `StyleService` and `SceneService` (`scene_service.proto`); `GetFormMetadata`
  gains pagination.

### Notes

- `.NET` package `<Version>` and `conformance/VERSION` bumped to `0.1.0-alpha.3`
  (kept in lock-step; enforced by `conformance/check-version.sh`).
- Downstream consumers (`honua-server`, `honua-sdk-dotnet`, `honua-mobile`, …)
  must regenerate/re-pin against `v0.1.0-alpha.3`; see
  [docs/release-checklist.md](docs/release-checklist.md).

## v0.1.0-alpha.2 and earlier

See the git history and release tags. `v0.1.0-alpha.2` and `v0.1.0-alpha.1`
were the pre-finalization alpha wire snapshots.
