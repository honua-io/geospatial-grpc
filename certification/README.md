# Protocol certification producer

This producer snapshots the 42-cell gRPC denominator frozen by
`honua-release` (revision `2026-09-29-complete.15`: 14 RPCs for each
generated-client lane). The 2026.1 scope ruling
([#88](https://github.com/honua-io/geospatial-grpc/issues/88#issuecomment-5896448868),
honua-release#376) keeps only the RPCs honua-server implements. The other 66 of
the 80 inventoried RPCs are listed in the catalog's `excluded_operations` with
maturity, rationale, owner issue and target release. Runners still execute the
fixtures for excluded operations. The fragment reports those results under
`excluded_operations` (`counts_toward_ga: false`, and each lane result carries
its report provenance and `identity_verified`). An excluded result never
becomes an observation, a receipt or an `execution_failure`, and never fails a
lane's exit status. Every observation uses that denominator's governed identity: the published
`Geospatial.Grpc` (nuget.org), `geospatial-grpc` (PyPI) and
`@honua/geospatial-grpc` (npm) **1.0.3** packages, contract
`geospatial-grpc@00fca4de` (tag v1.0.3) and fixtures
`geospatial-grpc-conformance@1.0.5+18e609cf` (tag v1.0.5). The workflow installs
exactly those bytes. The pip requirement hash, the npm lockfile integrity and
the NuGet lockfile content hash are pinned to the catalog's `package_digest` /
`package_lock_hash`, and `tests/test_certification_client_pins.py` enforces it.
Each lane runs independently, so one failing lane never hides another lane's
results. A report from any other package version is rejected, not relabeled.
`client_rollup` stays red until every governed cell passes. A
narrowing-decision URL alone cannot waive cells; any adopted change must be
reflected in the governed denominator.

`scripts/build_protocol_certification_fragment.py` emits the registered
`protocol-certification-fragment.json`. Its unit tests require no live server:

```bash
python3 -m unittest tests/test_protocol_certification_fragment.py -v
```

The scheduled and dispatched workflow owns exact-image verification, fixture
seeding, and the live generated-client execution.

The workflow provisions the PostGIS extensions and starts the candidate image,
which runs its own migrations. Once the server is ready, it applies the candidate's
own `tests/seed/base-schema.sql` (fetched at the exact server source SHA) and then
`seed/sf-parks.sql`. This is the order honua-server's `setup-honua-server` action
uses. Current servers refuse migration-owned tables created before their
migrations run. That seed registers the `sf-parks` service with layer 0, the
target of the FeatureService fixtures, through the same catalog tables and
`honua.seed_metadata_v2_compat_snapshot()` path that base-schema.sql uses.
Honua layer ids are global, so the seed rebinds layer 0 from base-schema's
`test_service` to `sf-parks`. `seed/sf-parks-reset.sql` runs before every client
lane and restores features 7 and 42, leaves 8 absent, and pins the next object
id to 101. Without it, one lane's ApplyEdits would change what the next lane
reads.

All three runners execute the scenarios declared in `scenarios.v1.json`:
unary and server-streaming calls, captured ids bound into later requests and
expected responses, setup calls, polling for terminal job states
(`HONUA_CERTIFICATION_POLL_TIMEOUT_SECONDS` overrides the bound), and the
negative case of every governed scenario. The fixtures cover all 14 governed
RPCs. For each scenario with a negative case a runner reports `facet_results`
for `positive`, `negative` and `media-schema` (the response decodes as the
installed generated type with no unknown fields, at any depth). The fragment
builder emits a receipt only when every facet passes against the governed
client version.

Response comparison is exact except for the values listed in
`server-assigned-fields.v1.json`, which a server assigns and a fixture cannot
predict (created ids, timestamps, job and result ids). Each runner replaces
those values in both documents with a placeholder before comparing, so the
value must be present but is not compared. `optional_operations` values, which
may validly be the proto3 default, are removed from both documents instead.
ApplyEdits also runs the negative `feature_apply_edits_missing_target` batch
first. It must fail as a whole with the recorded gRPC status. The runner then
reads the batch's targets back and requires them unchanged
(`feature_apply_edits_missing_target_verify_*`) before running the positive
batch.

Executed failures are also retained in `execution_failures`, attributed by lane
and operation. Both the .NET runner and fragment CLI return nonzero on an
executed failure, including a failure in a cell with incomplete scenario facets.
The workflow still uploads its reports after a failure. Nightly and release
mode additionally reject every missing/non-passing required cell. PR execution
remains bounded to the existing six live requests and producer regressions.

`--tier release` requires digest/source agreement, timezone-aware execution
timestamps on or after the candidate cut, and evidence no older than 24 hours.
The same freshness checks apply nightly. Executed lane reports must bind their
own timestamps, channel target, image, source SHA, and fixture revision to the
current run, preventing old reports from being relabeled with fresh CLI times.

The installed-client transport regression uses a Python loopback gRPC oracle
with manually encoded protobuf responses. Its expected JSON is authored
independently of generated bindings and of runner output. It verifies feature
ID, X/Y axis order, optional zero Z, M, null attribute semantics, and CRS, and
injects one defect at a time. It also injects an RPC exception. Each defect must
fail the process while retaining all six operation results. This tests the
producer; it is not evidence that a Honua Server candidate passed.

The same oracle suite runs against every installed-client runner (.NET,
Python and TypeScript):

```bash
python3 -m pip install --require-hashes --only-binary=:all: \
  --requirement .github/requirements/protocol-certification.txt
dotnet build certification/dotnet/GrpcCertificationRunner.csproj --configuration Release
npm ci --ignore-scripts --prefix certification/typescript
python3 -m unittest discover -s certification/tests -v
```

See [the issue #88 proof disposition](issue-88-proof-disposition.md) for the
remaining pre-cut blockers and the exact-candidate criterion released until cut.
