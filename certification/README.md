# Protocol certification producer

This producer snapshots the 240-cell gRPC denominator frozen by
`honua-release` (80 RPCs for each generated-client lane). The workflow installs
`Geospatial.Grpc` 0.2.0-alpha.1 from NuGet and executes the six requests from
the checksum-verified `conformance-fixtures-0.2.0-alpha.1` release artifact.
The remaining .NET cells,
and all Python and TypeScript cells for which no promoted package exists, are
materialized as `skip` with a concrete reason.

`scripts/build_protocol_certification_fragment.py` emits the registered
`protocol-certification-fragment.json`. Its unit tests require no live server:

```bash
python3 -m unittest tests/test_protocol_certification_fragment.py -v
```

The scheduled and dispatched workflow owns exact-image verification, fixture
seeding, and the live generated-client execution.
