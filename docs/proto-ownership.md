# Protocol Ownership and Downstream Sync

This repository is the canonical home for shared geospatial gRPC protocol
definitions. Honua servers, SDKs, mobile apps, and admin tools may generate,
package, or pin client code from these definitions, but local copies in those
repositories are not the source of truth.

## Canonical Layout

- Protocol definitions live under `geospatial/v1/`.
- The protocol package is `geospatial.v1` for the current major version.
- Shared geometry, field, and attribute contracts belong in this repository
  when they are used by more than one Honua runtime.
- Service contracts that are Honua-specific but shared across repos should be
  proposed here first, then consumed downstream after review.
- Repo-specific implementation types, adapters, persistence models, and UI
  models should stay in their owning application repository.

## Change Rules

Protocol changes must start in this repository before downstream repositories
update generated clients or compatibility adapters.

1. Open or update a tracking issue that explains the downstream consumers.
2. Update the `.proto` files under `geospatial/v1/`.
3. Run `buf format --diff --exit-code`, `buf lint`, and `buf breaking`.
4. Update protocol docs and examples when behavior changes.
5. Publish or pin the generated artifacts used by downstream consumers.
6. Update downstream repos to consume the reviewed protocol revision.

Breaking changes require a new package/version path, such as `geospatial/v2`,
unless every affected consumer has an explicit migration plan.

For the full owner workflow — release, tag, publish, and per-SDK regeneration
coordination — follow [docs/release-checklist.md](release-checklist.md).

## Compatibility Rules

- Prefer additive fields, messages, methods, and enum values.
- Do not reuse field numbers.
- Reserve field numbers and names when removing fields.
- Do not rename fields, messages, services, or enum values in `geospatial.v1`.
- Keep default values meaningful for older clients.
- Document server feature flags or optional behavior in the service comments and
  generated docs.

## Honua Consumer Contract

| Repo | Role | Protocol rule |
| --- | --- | --- |
| `honua-server` | Implements gRPC services | Must implement the canonical schemas from this repository. Server-local protos are temporary migration inputs only. |
| `honua-sdk-dotnet` | Publishes .NET SDK clients and domain abstractions | Must consume generated protocol clients through package references or generated artifacts derived from this repository. It should not own independent `.proto` definitions. |
| `honua-mobile` | Uses SDK capabilities in mobile workflows | Should consume protocol behavior through the .NET SDK packages instead of duplicating transport clients. |
| `honua-server-admin` | Uses admin/server APIs | Should consume SDK packages for shared admin clients and generated protocol contracts where applicable. |

## Current Honua Reconciliation Items

| Contract | Current status | Next action |
| --- | --- | --- |
| `feature_service.proto` | Exists here and in downstream copies with package/layout drift. | Sync downstream consumers to the canonical `geospatial/v1` contract. |
| `form_service.proto` | Canonical contract now includes downstream workflow/action and access-control fields. | Sync downstream consumers to this file and remove editable local copies. |
| `process_service.proto` | Canonical contract now lives here. | Sync `honua-server` generated bindings from this repository. |
| `spec_service.proto` | Canonical contract now lives here. | Sync `honua-server` and SDK/admin spec clients from this repository. |

Tracking issue: <https://github.com/honua-io/geospatial-grpc/issues/12>

## Downstream Sync Checklist

Use this checklist when updating a downstream repo after protocol changes land
here.

- Record the geospatial-grpc commit, Buf module digest, package version, or
  generated artifact version being consumed.
- Remove or mark any repo-local `.proto` snapshots as generated/pinned copies,
  not editable source files.
- Update generated clients or SDK package references. .NET consumers should use
  the `Geospatial.Grpc` NuGet package when they need generated protocol
  bindings.
- Run downstream compile, analyzer, and protocol integration tests.
- Link the downstream PR or issue back to the source protocol issue.
