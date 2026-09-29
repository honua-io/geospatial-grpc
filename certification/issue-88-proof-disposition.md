# Issue #88 proof disposition

> **Scope update (2026-09-29).** The 240-cell / 80-RPC figures below record the
> denominator as it stood on 2026-09-06. The 2026.1 scope ruling
> ([comment](https://github.com/honua-io/geospatial-grpc/issues/88#issuecomment-5896448868))
> narrows the governed denominator to 42 cells (14 RPCs × 3 lanes). The other 66
> RPCs are reported as `excluded_operations`; see `README.md`.

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

## Federation status after rebinding to the governed denominator

Promoted packages now exist (`Geospatial.Grpc` 1.0.0, `geospatial-grpc` 1.0.0,
`@honua/geospatial-grpc` 1.0.0). They are not the governed client version.
Observations again use the honua-release identity
`source@73fc882b1ae00d0a4a348aeadfba9f48b1a0317c` with contract
`geospatial-grpc@73fc882b1ae00d0a4a348aeadfba9f48b1a0317c` and fixture
`geospatial-grpc-conformance@0.2.0-alpha.1+73fc882b1ae00d0a4a348aeadfba9f48b1a0317c`.
An installed 1.0.0 failure stays in `execution_failures`, attributed by lane
and operation, and the required cell remains an evidence-free skip.

`tests/test_protocol_certification_fragment.py` loads the sibling
honua-evidence aggregator and honua-release protocol gate. The 240 skip
observations join. The release-tier gate fails closed because those cells are
not passes. honua-evidence trunk still accepts receipt schema v1 only, so a
future passing v2 receipt remains owned by issue #99 and is not emitted for
these unexecuted cells.

## Remaining pre-cut blockers

1. **The previous green run executed zero successful operations.** Its
   [governed artifact](https://github.com/honua-io/geospatial-grpc/actions/runs/33955693908)
   contains six failed .NET outcomes: QueryFeatures/ApplyEdits cannot find
   `sf-parks`; GetFormDefinition/SubmitFormData are unimplemented; ExecutePlan
   rejects synchronous execution; CreateWorkspace fails fixture parsing with
   `Unknown field: ref`. These are actual installed-client results against the
   pinned image, not inferred from an absent artifact. The restored failure
   signal must remain red until these execution prerequisites are repaired.
   Those 1.0.0 results still do not satisfy the governed `source@73fc882` cell.
2. **Python and TypeScript lanes execute, but not the governed pin.** The
   workflow now installs promoted `geospatial-grpc` 1.0.0 (PyPI) and
   `@honua/geospatial-grpc` 1.0.0 (npm) and runs the same six fixtures through
   each, independently of the .NET lane. Their failures are attributed in
   `execution_failures` by lane and operation. Because 1.0.0 is not
   `source@73fc882…`, the governed cells stay evidence-free skips until the
   denominator's client version and the executed package agree.
3. **Passing cells still cannot be ingested until receipt v2 lands in
   honua-evidence.** The release gate requires
   `honua.certification-evidence-receipt/v2`. The current evidence aggregator
   accepts v1 only. Issue #99 tracks that producer/consumer mismatch. Skip
   fragments do not carry receipts and are the fragments this producer emits
   for unexecuted cells.

## Acceptance criteria

| Criterion | Disposition |
|---|---|
| Named/versioned requirements for every supported operation | 240 observations use the honua-release generated-client version, contract, and fixture pin. |
| Fixture version and schema revision recorded | Present on every observation. Receipts are emitted only when every governed facet is executed. |
| Failures independently attributable by client and operation | Installed-client failures remain in `execution_failures` by lane and operation, including when the package version is not the governed pin. |
| Release rejects floating/mismatched/stale/missing evidence | Repaired and covered by precise regression tests. |
| Fragment accepted by honua-evidence and enforced by release gate | Skip fragments join the current denominator. The release-tier gate fails closed on the non-passing cells. Passing v2 receipts remain issue #99. |
| Bounded PR CI | Retains six live .NET requests and does not execute the full 240-cell matrix. |

Only execution and receipt federation **against the exact future candidate** is
released until the candidate is cut: there is no frozen candidate digest/cut to
bind those receipts to yet. None of the pre-cut blockers above is released for
that reason, and this PR must not close #88.
