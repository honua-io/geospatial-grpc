# Protocol certification producer

This producer snapshots the 240-cell gRPC denominator frozen by
`honua-release` (80 RPCs for each generated-client lane). The workflow installs
`Geospatial.Grpc` 1.0.0 anonymously from nuget.org and executes six requests
using fixtures checked out by immutable release commit. The schema and fixtures
are bound to the public BSR `v1.0.0` label at commit
`0f701ecc6b0c41a5ea43e2dff3c46ce654312576`.
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
