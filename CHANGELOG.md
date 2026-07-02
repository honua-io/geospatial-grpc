# Changelog

All notable changes to the `geospatial.v1` proto surface and the
`Geospatial.Grpc` package are recorded here. Versions correspond to the git
release tags (`v<version>`, and the .NET publish tag
`geospatial-grpc-v<version>`) and the `conformance/VERSION` fixture set.

The project is **pre-1.0 (alpha)**. Per the note in
[VERSIONING.md](VERSIONING.md), the strong within-major compatibility
guarantees apply between tagged `v1` releases once the surface stabilizes;
while still in the alpha phase the wire contract is being deliberately settled,
so an alpha release MAY intentionally break wire/JSON compatibility with the
previous alpha. Such breaks are acknowledged here and by cutting a new baseline
tag that the `buf breaking` push-time gate compares against.

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
