# Contributing

Thank you for your interest in the Geospatial gRPC protocol. This guide covers how to validate and submit proto changes.

## Prerequisites

- [Buf CLI](https://buf.build/docs/installation) — version should match the CI workflow (see `.github/workflows/ci.yml`).
- A proto-aware editor is recommended but not required.

## Local Validation

Run these before pushing:

```bash
# Lint proto definitions
buf lint

# Check formatting
buf format --diff --exit-code

# Check for breaking changes against main
buf breaking --against '.git#branch=main'
```

All three checks run in CI and must pass for a PR to merge.

## Proto Change Workflow

1. Create a feature branch from `main`.
2. Make proto changes in `geospatial/v1/`.
3. Run the local validation commands above.
4. Open a PR against `main`.

## PR Requirements

- **Conventional commits** — use prefixes like `feat:`, `fix:`, `docs:`, `chore:`.
- **Field number documentation** — when adding fields, note the next available field number in your PR description if the numbering gap is non-obvious.
- **Additive-with-care changes** — if you add a field to a `oneof` or add a new proto file, note the impact on generated `switch`/`match` statements in the PR description.

## What Not to Change Within v1

The following changes are **breaking** and require the full governance process described in [VERSIONING.md](VERSIONING.md):

- Removing or renaming a field, enum value, or RPC.
- Changing a field's type or number.
- Moving a field into or out of a `oneof`.
- Changing an RPC's streaming direction, request type, or response type.
- Reusing a reserved field number or name.

## C# / .NET AOT Considerations

The primary consumer of this protocol uses .NET NativeAOT compilation. To preserve compatibility:

- **Use typed messages** — avoid `google.protobuf.Any` and `google.protobuf.Struct`, which require runtime reflection.
- **Preserve the `oneof` pattern** — the existing proto surface uses concrete typed `oneof` discriminators. New messages should follow the same pattern.
- **Test with trimming in mind** — avoid patterns that rely on reflection-based serialization.

## Versioning Policy

For the full versioning, deprecation, and breaking-change governance policy, see [VERSIONING.md](VERSIONING.md).
