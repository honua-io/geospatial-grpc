---
type: index
title: "Protocol surfaces"
description: "What geospatial.v1 defines and what it deliberately does not: the implemented service surfaces, and the line between a typed contract and a server that implements it."
resource: "https://buf.build/honua-io/geospatial-grpc"
tags: [protocol, grpc, surfaces]
---
# Geospatial gRPC Feature Map

Start at [Getting started](../getting-started.md) to generate a client, or read the
[protocol specification](../specification.md) for the wire contract. Ownership and
downstream-sync rules are in [protocol ownership](../proto-ownership.md).

This repository owns deterministic, typed protocol contracts. It does not own server implementations.

## Implemented Protocol Surfaces

- Feature data access through `FeatureService`: describe, query, and stream feature records; query related records across a layer relationship (`QueryRelatedRecords`); edit one layer (`ApplyEdits`) or several layers of a service in one call (`ApplyServiceEdits`); and [native attachments](attachments.md). Per-row versus whole-call edit failures are defined in [ApplyEdits batch semantics](../specification.md#applyedits-batch-semantics) and, across layers, [service-wide edit batches](../specification.md#service-wide-edit-batches).
- Mobile data collection through `FormService`: form definitions, controls, validation, and collaboration-oriented payloads.
- Workspace and artifact lifecycle services with typed refs, retention policy refs, materialization state, promotion stages, and lifecycle enums.
- Execution-plane services for processes, data publishing pipelines, rendering, app building, deployment, and spec plan/apply workflows.
- Shared packaging contracts: `MapPackage`, `AppPackage`, and `DeploymentSpec`.
- Shared execution contracts: plans, steps, jobs, artifacts, provenance, structured errors, and streaming execution responses.
- Multi-language generation configs for C#, Go, Java, Python, and TypeScript/JavaScript through Buf.
- A .NET protocol package project for downstream consumers that should reference a package instead of copying `.proto` files.

## Boundary

The standard defines contract shape and language generation. Runtime behavior, auth, persistence, and UI workflows belong in `honua-server`, SDKs, admin UI, and operator repositories.
