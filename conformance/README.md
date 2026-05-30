# Conformance fixtures and regression harness

This directory holds **canonical request/response fixtures** for the core
`geospatial.v1` workflows and a **contract-level regression harness** that
catches schema drift before it reaches downstream generated SDKs
(`honua-server`, `honua-sdk-dotnet`, and the other generated clients).

The harness is language-agnostic: it validates fixtures directly against the
`.proto` source of truth using `buf` (already pinned by CI), so it needs no
per-language code generation or runtime.

## Layout

```
conformance/
  fixtures/                 # Canonical workflow payloads (protobuf JSON mapping)
    manifest.txt            #   fixture file -> fully-qualified message type
    *_request.json          #   canonical request payloads
    *_response.json         #   canonical response payloads
  golden/                   # Canonical round-trip output, regenerated from the schema
  run.sh                    # Regression harness
  README.md
```

## What is covered

Canonical fixtures exist for the core workflows of the primary services:

| Service            | Workflow                          | Fixtures                                              |
| ------------------ | --------------------------------- | ----------------------------------------------------- |
| `FeatureService`   | Query features                    | `feature_query_{request,response}.json`               |
| `FeatureService`   | Apply edits (add/update/delete)   | `feature_apply_edits_{request,response}.json`         |
| `FormService`      | Get form definition               | `form_get_definition_{request,response}.json`         |
| `FormService`      | Submit form data                  | `form_submit_{request,response}.json`                 |
| `ProcessService`   | Execute plan (synchronous)        | `process_execute_plan_{request,response}.json`        |
| `WorkspaceService` | Create workspace                  | `workspace_create_{request,response}.json`            |

Fixtures use the canonical [protobuf JSON
mapping](https://protobuf.dev/programming-guides/proto3/#json) (camelCase field
names, enum value names as strings, `int64` as strings). They double as
copy-paste reference payloads for the language examples and for downstream SDK
integration tests.

## How the harness works

For each entry in `fixtures/manifest.txt`, `run.sh`:

1. confirms the declared message type still exists in the schema;
2. round-trips the fixture JSON through the live schema
   (`JSON -> binary -> canonical JSON`) with `buf convert`, interpreting it
   against the current `.proto` definitions; and
3. compares the canonical JSON to the committed golden in `golden/`.

Because step 2 is interpreted against the current schema, any **contract drift**
that changes the wire/JSON shape of a canonical message — a removed or renamed
field, a changed field type, a dropped enum value — either fails the conversion
or changes the canonical output, so the golden comparison fails. This
complements `buf breaking` (which compares the schema to its own history) by
asserting that *concrete, real-world payloads for the canonical workflows* still
behave as committed.

## Running locally

```bash
# Verify all fixtures against their goldens.
conformance/run.sh

# Regenerate goldens after an intentional, reviewed schema change.
conformance/run.sh --update
```

The only requirement is `buf` on `PATH` (CI pins `1.66.0`).

## Adding a fixture

1. Write the payload as protobuf JSON under `fixtures/` (use an existing fixture
   as a template).
2. Add a `fixture-file  fully.qualified.MessageType` line to
   `fixtures/manifest.txt`.
3. Run `conformance/run.sh --update` to generate the golden, then
   `conformance/run.sh` to confirm it passes.
4. Commit the fixture, the manifest entry, and the golden together.

## Reacting to a failure

A failing harness means a canonical payload no longer round-trips the same way.
Inspect the printed diff:

- **Unintended drift** (an accidental breaking change): fix the `.proto`.
- **Intentional change** (reviewed and deliberate): run
  `conformance/run.sh --update`, review the golden diff, and commit it alongside
  the schema change so reviewers can see the contract impact.
