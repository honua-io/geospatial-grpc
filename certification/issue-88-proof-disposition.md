# Issue #88 proof disposition

Observed 2026-09-06 UTC (2026-09-05 Honolulu). Issue #88 remains blocked.
This does not change its must-fix-before-cut classification or the supported
gRPC promise in the 2026.1 quality contract and September 4 decision 4.

## Delivered producer repairs

- Executed failures remain attributable by language and operation even when
  incomplete facets require an evidence-free federation skip. They make both
  the installed .NET runner and fragment CLI fail after writing reports.
- Release/nightly mode rejects non-passing required cells, floating images,
  source/image disagreement, stale evidence, reversed/future timestamps, and
  execution reports from a different target, fixture, image, or run interval.
- A narrowing-comment URL no longer turns incomplete certification green.
- The retained six live PR calls are supplemented by a bounded independent
  wire oracle. No existing tests or live calls have been removed or skipped.

Local validation: 37 release/fragment unit tests passed; the installed .NET
runner built under the PATH lane shim with zero warnings/errors; three
transport tests passed (one matching response, six independently injected
value/geometry/null/metadata defects, and one RPC exception). Against the old
runner from PR head `12b28922693349106af4d5f2acd01d29334a7a31`, the seven
failure cases fail their exit-status assertions because that runner returns 0.
The matching-response case passes against both versions.

## Remaining pre-cut blockers

1. **The previous green run executed zero successful operations.** Its
   [governed artifact](https://github.com/honua-io/geospatial-grpc/actions/runs/33955693908)
   contains six failed .NET outcomes: QueryFeatures/ApplyEdits cannot find
   `sf-parks`; GetFormDefinition/SubmitFormData are unimplemented; ExecutePlan
   rejects synchronous execution; CreateWorkspace fails fixture parsing with
   `Unknown field: ref`. These are actual installed-client results against the
   pinned image, not inferred from an absent artifact. The restored failure
   signal must remain red until these execution prerequisites are repaired.
2. **The claimed multi-client matrix cannot execute from published artifacts.**
   Public registry probes on the observation date return HTTP 404 for both
   `https://pypi.org/pypi/geospatial-grpc/1.0.0/json` and
   `https://registry.npmjs.org/@honua%2fgeospatial-grpc/1.0.0`. The catalog has
   80 operations for each of three clients, but only six .NET positive calls
   exist and none has the full required facets. The .NET GitHub Packages
   publication workflow in this PR does not publish the other client packages.
3. **Federation does not currently accept this producer's package identities.**
   Running honua-evidence's aggregator at
   `808d659404d895cc5672ac7b19c7b451fb89112d` against honua-release requirements
   at `ffc92bc348e155fbd80b6ac6d44721fb9e632561` and the prior CI fragment fails
   with `observations do not resolve to requirements`. The first rejected cell
   is `ArtifactService/GetArtifact`, `.NET`, version `1.0.0`. All 240 governed
   gRPC requirements still pin `source@73fc882b1ae00d0a4a348aeadfba9f48b1a0317c`
   and the old `0.2.0-alpha.1` fixture, while this producer records installed
   package 1.0.0. The pinned aggregator also accepts receipt schema v1 only,
   while the release requirements specify `receipt_schema_min: v2` and this
   producer emits v2. Aligning the governed contracts must precede an acceptance
   claim; syntactic generation of 240 skips is insufficient.

## Acceptance criteria

| Criterion | Disposition |
|---|---|
| Named/versioned requirements for every supported operation | 240 catalog cells exist; package identities still differ from the release denominator as described above. |
| Fixture version and schema revision recorded | Present in each observation and digest-bound receipt. |
| Failures independently attributable by client and operation | Repaired and challenged by the CLI and installed-client transport regressions. |
| Release rejects floating/mismatched/stale/missing evidence | Repaired and covered by precise regression tests. |
| Fragment accepted by honua-evidence and enforced by release gate | Blocked by the pinned cross-repository contract mismatch and missing execution. |
| Bounded PR CI | Retains six live requests, adds bounded producer tests, and does not execute the full 240-cell matrix. Full nightly execution remains incomplete. |

Only execution and receipt federation **against the exact future candidate** is
released until the candidate is cut: there is no frozen candidate digest/cut to
bind those receipts to yet. None of the pre-cut blockers above is released for
that reason, and this PR must not close #88.
