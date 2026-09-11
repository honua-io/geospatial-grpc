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

- Feature data access through `FeatureService`: query, stream, and edit feature records.
- Mobile data collection through `FormService`: form definitions, controls, validation, and collaboration-oriented payloads.
- Workspace and artifact lifecycle services with typed refs, retention policy refs, materialization state, promotion stages, and lifecycle enums.
- Execution-plane services for processes, data publishing pipelines, rendering, app building, deployment, and spec plan/apply workflows.
- Shared packaging contracts: `MapPackage`, `AppPackage`, and `DeploymentSpec`.
- Shared execution contracts: plans, steps, jobs, artifacts, provenance, structured errors, and streaming execution responses.
- Multi-language generation configs for C#, Go, Java, Python, and TypeScript/JavaScript through Buf.
- A .NET protocol package project for downstream consumers that should reference a package instead of copying `.proto` files.

## Source Evidence

- Service definitions: `geospatial/v1/*_service.proto`
- Shared domain types: `geospatial/v1/common.proto`, `spatial_types.proto`, `execution_types.proto`, `packaging_types.proto`, `workspace_artifact_types.proto`
- Generation configs: `buf.yaml`, `buf.gen.*.yaml`
- Examples: `examples/dotnet/`, `examples/javascript/`, `examples/python/`

## Boundary

The standard defines contract shape and language generation. Runtime behavior, auth, persistence, and UI workflows belong in `honua-server`, SDKs, admin UI, and operator repositories.
