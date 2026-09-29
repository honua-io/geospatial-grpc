# Protocol certification producer

This producer snapshots the 240-cell gRPC denominator frozen by
`honua-release` (80 RPCs for each generated-client lane). Every observation
uses that denominator's governed identity: client version
`source@73fc882b1ae00d0a4a348aeadfba9f48b1a0317c`, contract
`geospatial-grpc@73fc882b1ae00d0a4a348aeadfba9f48b1a0317c`, and fixture
`geospatial-grpc-conformance@0.2.0-alpha.1+73fc882b1ae00d0a4a348aeadfba9f48b1a0317c`.
Promoted `Geospatial.Grpc`, `geospatial-grpc`, and `@honua/geospatial-grpc`
1.0.0 packages are not that pin. The workflow still installs and executes the
.NET package against six fixtures, but those results stay attributable
execution failures or skips and do not satisfy the governed cell.
Python and TypeScript lanes stay unexecuted skips for the same reason.
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

```bash
python3 -m pip install grpcio==1.81.1
dotnet build certification/dotnet/GrpcCertificationRunner.csproj --configuration Release
python3 -m unittest discover -s certification/tests -v
```

See [the issue #88 proof disposition](issue-88-proof-disposition.md) for the
remaining pre-cut blockers and the exact-candidate criterion released until cut.
