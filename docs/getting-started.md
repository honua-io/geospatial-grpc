---
type: guide
title: "Generate a client and make your first call"
description: "Install buf, generate bindings for C#, TypeScript or Python from the shared protos, and run a first QueryFeatures call. Needs a server that speaks the protocol; this repository does not ship one."
resource: "https://www.nuget.org/packages/Geospatial.Grpc"
tags: [quickstart, codegen, csharp, typescript, python]
---
# Getting Started with Geospatial gRPC

This guide will help you quickly get up and running with the Geospatial gRPC protocols.

## Prerequisites

> **This repository ships the protocol, not a server.** There is no reference
> implementation, container image, or compose file here, and every example below targets a
> placeholder host (`api.example.com`). To run any of them end to end you need a server that
> speaks this protocol — see the
> [Honua Server quickstart](https://github.com/honua-io/honua-server/blob/trunk/docs/get-started/quickstart.md),
> and note that its gRPC listener is h2c on port **8081**, separate from the HTTP port.

- **Buf CLI**: [Install Buf](https://buf.build/docs/installation) for protocol buffer management
- **Development Environment**: Your preferred language with gRPC support
- **Basic gRPC Knowledge**: Understanding of Protocol Buffers and gRPC concepts

## Step 1: Install Tools

### Install Buf CLI

```bash
# macOS
brew install bufbuild/buf/buf

# Linux/WSL
curl -sSL https://github.com/bufbuild/buf/releases/latest/download/buf-Linux-x86_64.tar.gz | tar -xzf - -C /usr/local buf/bin/buf

# Windows
# Download from: https://github.com/bufbuild/buf/releases
```

### Verify Installation

```bash
buf --version
```

## Step 2: Clone the Repository

```bash
git clone https://github.com/honua-io/geospatial-grpc.git
cd geospatial-grpc
```

The stable schema is also public on the BSR. To generate from its immutable
release coordinate while using this checkout's generation template:

```bash
buf generate buf.build/honua-io/geospatial-grpc:v1.0.0
```

## Step 3: Generate Client Libraries

### Generate for All Languages

```bash
buf generate
```

This creates client libraries in the `gen/` directory:

```
gen/
├── csharp/     # C# / .NET
├── go/         # Go
├── java/       # Java
├── python/     # Python
├── rust/       # Rust
├── swift/      # Swift
└── typescript/ # TypeScript/JavaScript
```

### Generate for Specific Language

Pair `--output` with a **single-language template**. This is what this repository's own CI
does:

```bash
# Only C# (messages *and* service stubs)
buf generate --template buf.gen.csharp.yaml --output generated/csharp

# Only JavaScript (protoc-gen-es target=js, no .d.ts)
buf generate --template buf.gen.javascript.yaml --output generated/javascript

# Also available: buf.gen.go.yaml, buf.gen.java.yaml, buf.gen.python.yaml
```

Run these from the repository root. Each writes a flat tree under the directory you name.

**TypeScript is the exception.** `buf.gen.javascript.yaml` is `target=js` and emits `*_pb.js`
with no `.d.ts`, so a TypeScript project gets no types from it. For TypeScript use the
all-language template, whose `connectrpc/es` plugin is `target=ts`, and take the
`gen/typescript/` tree it writes:

```bash
buf generate --template buf.gen.yaml --path geospatial/v1
# -> gen/typescript/geospatial/v1/*_pb.ts
```

> **Do not pass `--output` to `buf.gen.yaml`.** `--output` sets the base directory that each
> plugin's `out:` resolves against; it does not replace it. `buf.gen.yaml` declares `out:
> gen/csharp`, `out: gen/go` and five more, so
> `buf generate --template buf.gen.yaml --output gen/csharp` writes
> `gen/csharp/gen/csharp/`, `gen/csharp/gen/go/`, `gen/csharp/gen/java/` and one directory per
> remaining language — every language, nested one level deeper than you asked for. The
> single-language templates use `out: .`, which is why `--output` behaves there.

`buf.gen.csharp.yaml` also runs `buf.build/grpc/csharp`, so it emits the `*Grpc.cs` service
stubs. The all-language `buf.gen.yaml` runs only `buf.build/protocolbuffers/csharp`, which
gives you messages and **no client** — worth knowing if you ran plain `buf generate` and
cannot find `FeatureServiceClient`.

## Step 4: Set Up Your Development Environment

### .NET / C#

1. **Create a new project**:
```bash
dotnet new console -n GeospatialGrpcExample
cd GeospatialGrpcExample
```

2. **Add gRPC packages**:
```bash
dotnet add package Grpc.Net.Client
dotnet add package Geospatial.Grpc --version 1.0.0
```

This restore uses nuget.org; no GitHub Packages credential or source checkout is
required.

### TypeScript / JavaScript

1. **Create a new Node.js project**:
```bash
mkdir geospatial-grpc-example && cd geospatial-grpc-example
npm init -y
npm pkg set type=module
npm install @bufbuild/protobuf @connectrpc/connect @connectrpc/connect-node
npm install --save-dev typescript tsx
```

`npm pkg set type=module` is required. The generated code is ESM and the examples below use
top-level `await`; neither works under the CommonJS default that `npm init -y` writes.

2. **Copy generated files**:
```bash
# from geospatial-grpc-example/, with the repo checked out alongside it
mkdir -p gen
cp -r ../geospatial-grpc/gen/typescript/geospatial ./gen/
```

The `connectrpc/es` plugin writes `gen/typescript/geospatial/v1/*_pb.ts` — there is no
`src/` directory to copy.

### Python

1. **Set up virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
```

2. **Install gRPC packages**:
```bash
pip install grpcio grpcio-tools
```

3. **Copy generated files**:
```bash
# from the venv directory, with the repo checked out alongside it
cp -r ../geospatial-grpc/generated/python/* .
```

## Step 5: Your First Query

### .NET Example

```csharp
using Geospatial.V1;
using Grpc.Net.Client;

// Create gRPC channel
using var channel = GrpcChannel.ForAddress("https://api.example.com");
var client = new FeatureService.FeatureServiceClient(channel);

// Build query request
var request = new QueryFeaturesRequest
{
    ServiceId = "parks",
    LayerId = 0,
    Where = "AREA > 1000",
    ReturnGeometry = true,
    ResultRecordCountLong = 100
};

// Execute query
var response = await client.QueryFeaturesAsync(request);

// Process results
Console.WriteLine($"Found {response.Features.Count} features");
foreach (var feature in response.Features)
{
    Console.WriteLine($"Feature ID: {feature.Id}");
    if (feature.Geometry?.Point != null)
    {
        var point = feature.Geometry.Point;
        Console.WriteLine($"Location: {point.X}, {point.Y}");
    }
}
```

### TypeScript Example

```typescript
import { FeatureService } from './gen/geospatial/v1/feature_service_pb.js';
import { createClient } from '@connectrpc/connect';
import { createGrpcTransport } from '@connectrpc/connect-node';

// Create transport and client
const transport = createGrpcTransport({
  baseUrl: 'https://api.example.com'
});

const client = createClient(FeatureService, transport);

// Build and execute query
const response = await client.queryFeatures({
  serviceId: 'parks',
  layerId: 0,
  where: 'AREA > 1000',
  returnGeometry: true,
  resultRecordCountLong: 100n
});

// Process results
console.log(`Found ${response.features.length} features`);
response.features.forEach(feature => {
  console.log(`Feature ID: ${feature.id}`);
  // `shape` is a proto3 oneof. protobuf-es v2 renders it as a tagged union
  // ({ case, value }), not as sibling properties - `geometry.point` is always
  // undefined.
  const shape = feature.geometry?.shape;
  if (shape?.case === 'point') {
    const { x, y } = shape.value;
    console.log(`Location: ${x}, ${y}`);
  }
});
```

### Python Example

```python
import grpc
from geospatial.v1 import feature_service_pb2
from geospatial.v1 import feature_service_pb2_grpc

# Create gRPC channel and client
channel = grpc.insecure_channel('api.example.com:443')
client = feature_service_pb2_grpc.FeatureServiceStub(channel)

# Build query request
request = feature_service_pb2.QueryFeaturesRequest(
    service_id='parks',
    layer_id=0,
    where='AREA > 1000',
    return_geometry=True,
    result_record_count_long=100
)

# Execute query
response = client.QueryFeatures(request)

# Process results
print(f'Found {len(response.features)} features')
for feature in response.features:
    print(f'Feature ID: {feature.id}')
    if feature.geometry.HasField('point'):
        point = feature.geometry.point
        print(f'Location: {point.x}, {point.y}')
```

## Step 6: Working with Forms

### Get Form Definition

```csharp
using Geospatial.V1;

var formClient = new FormService.FormServiceClient(channel);

var formRequest = new GetFormDefinitionRequest
{
    FormId = "park-inspection",
    ServiceId = "parks",
    LayerId = 0,
    MobileCapabilities = new MobileCapabilities
    {
        HasCamera = true,
        HasGps = true,
        Platform = "ios",
        DeviceType = "phone",
        NetworkType = NetworkType.Wifi
    }
};

var formResponse = await formClient.GetFormDefinitionAsync(formRequest);
var form = formResponse.Form;

Console.WriteLine($"Form: {form.Title}");
foreach (var control in form.Controls)
{
    Console.WriteLine($"  Field: {control.Label}");
}
```

### Submit Form Data

```csharp
var submission = new SubmitFormDataRequest
{
    FormId = "park-inspection",
    FormVersion = "1.0",
    Instance = new FormInstance
    {
        InstanceId = Guid.NewGuid().ToString(),
        FormId = "park-inspection",
        CreatedBy = "user123",
        Status = InstanceStatus.Complete
    }
};

// Add field values
submission.Instance.FieldValues["inspector_name"] = new AttributeValue
{
    StringValue = "John Doe"
};

submission.Instance.FieldValues["inspection_date"] = new AttributeValue
{
    DatetimeValue = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
};

submission.Instance.FieldValues["location"] = new AttributeValue
{
    StringValue = "POINT(-122.4194 37.7749)" // San Francisco
};

var submitResponse = await formClient.SubmitFormDataAsync(submission);
if (submitResponse.Result.Success)
{
    Console.WriteLine($"Created feature ID: {submitResponse.CreatedFeatureId}");
}
```

## Step 7: Streaming Large Datasets

For large queries, use streaming to avoid memory issues:

```csharp
var streamRequest = new QueryFeaturesRequest
{
    ServiceId = "parcels",
    LayerId = 0,
    Where = "1=1", // All features
    ReturnGeometry = false, // Attributes only for performance
    ResultRecordCountLong = 1000 // Page size
};

using var streamCall = client.QueryFeaturesStream(streamRequest);

var totalCount = 0;
await foreach (var page in streamCall.ResponseStream.ReadAllAsync())
{
    totalCount += page.Features.Count;
    Console.WriteLine($"Processed {page.Features.Count} features (total: {totalCount})");

    // Process features in this page
    foreach (var feature in page.Features)
    {
        // Process individual feature
        Console.WriteLine($"Feature {feature.Id}");
    }

    if (page.IsLastPage)
    {
        break;
    }
}

Console.WriteLine($"Total features processed: {totalCount}");
```

## Step 8: Error Handling

Always implement proper error handling:

```csharp
try
{
    var response = await client.QueryFeaturesAsync(request);
    // Process response
}
catch (RpcException ex)
{
    switch (ex.StatusCode)
    {
        case StatusCode.NotFound:
            Console.WriteLine("Service or layer not found");
            break;
        case StatusCode.InvalidArgument:
            Console.WriteLine($"Invalid request: {ex.Status.Detail}");
            break;
        case StatusCode.PermissionDenied:
            Console.WriteLine("Access denied");
            break;
        default:
            Console.WriteLine($"gRPC error: {ex.Status}");
            break;
    }
}
```

## Step 9: Configuration for Production

### Connection Configuration

```csharp
using Grpc.Core;                        // StatusCode, CallCredentials
using Grpc.Net.Client;                  // GrpcChannel, GrpcChannelOptions
using Grpc.Net.Client.Configuration;    // ServiceConfig, MethodConfig, MethodName, RetryPolicy

var channel = GrpcChannel.ForAddress("https://api.production.com", new GrpcChannelOptions
{
    // Connection settings
    MaxReceiveMessageSize = 16 * 1024 * 1024, // 16MB
    MaxSendMessageSize = 4 * 1024 * 1024,     // 4MB

    // Retry configuration
    //
    // IMPORTANT: read-only (idempotent) methods are always safe to retry.
    // Mutating RPCs are only safe to retry when the request carries a stable
    // idempotency_key: the server MUST treat a retry that reuses the same key
    // within its dedup window as the same operation and return the original
    // result, so a retry after a lost response cannot SILENTLY DUPLICATE the
    // write. The protocol defines this idempotency_key field on the mutating
    // RPCs — FeatureService.ApplyEdits, FormService.SubmitFormData, and the
    // operator Submit*/Execute*/RollbackDeployment requests. Set a stable key
    // (e.g. a UUID per logical attempt) before adding those methods to a retry
    // policy. Do NOT use MethodName.Default to blanket-retry every method,
    // because that would also retry mutations on calls where you did not set an
    // idempotency_key, which can duplicate the write. Instead, scope the policy
    // to specific read-only methods (below) plus any mutating method for which
    // you always send an idempotency_key.
    ServiceConfig = new ServiceConfig
    {
        MethodConfigs =
        {
            new MethodConfig
            {
                Names =
                {
                    new MethodName { Service = "geospatial.v1.FeatureService", Method = "QueryFeatures" },
                    new MethodName { Service = "geospatial.v1.FeatureService", Method = "QueryFeaturesStream" },
                    new MethodName { Service = "geospatial.v1.FormService", Method = "GetFormDefinition" },
                    new MethodName { Service = "geospatial.v1.FormService", Method = "GetFormMetadata" },
                    new MethodName { Service = "geospatial.v1.FormService", Method = "ValidateFormData" },
                },
                RetryPolicy = new RetryPolicy
                {
                    MaxAttempts = 3,
                    InitialBackoff = TimeSpan.FromSeconds(1),
                    MaxBackoff = TimeSpan.FromSeconds(5),
                    BackoffMultiplier = 1.5,
                    RetryableStatusCodes = { StatusCode.Unavailable }
                }
            }
        }
    }
});
```

### Authentication

```csharp
// API Key authentication
var credentials = CallCredentials.FromInterceptor((context, metadata) =>
{
    metadata.Add("Authorization", "Bearer your-api-key-here");
    return Task.CompletedTask;
});

var channel = GrpcChannel.ForAddress("https://api.production.com", new GrpcChannelOptions
{
    Credentials = ChannelCredentials.Create(new SslCredentials(), credentials)
});
```

## Step 10: Workspace, Artifact, Process, Pipeline, Render, Build, and Deployment Workflows

> **`ExecutionContext` is ambiguous in C#.** `dotnet new console` enables implicit usings,
> which bring in `System.Threading.ExecutionContext`, so the generated
> `Geospatial.V1.ExecutionContext` used throughout this step fails to compile with `CS0104`.
> Add an alias beside your other usings:
>
> ```csharp
> using ExecutionContext = Geospatial.V1.ExecutionContext;
> ```

The protocol includes seven services for server-side workflows:

- **`WorkspaceService`** — create, open, get, list, update, promote, retain, and release workspaces; inspect quota. Owns the canonical `WorkspaceRef` handle used by every operator service.
- **`ArtifactService`** — publish (client-stream), read (server-stream), get, inspect, list, retain, and release artifacts; resolve retention policies. Owns the canonical `ArtifactRef` handle and the `Artifact` resource.
- **`ProcessService`** — validate, dry-run, and execute geospatial analysis plans (synchronous, streaming, or async job)
- **`PipelineService`** — validate, dry-run, and execute data publishing pipelines with stage-by-stage progress
- **`RenderService`** — compose maps and produce a canonical `MapPackage` with streaming progress
- **`BuilderService`** — synthesize an `AppPackage` from templates, intent, and data bindings
- **`DeploymentService`** — promote `AppPackage`/`MapPackage`/`ArtifactRef` to live targets with rollback and health telemetry

The operator execution services (`ProcessService`, `PipelineService`, `RenderService`, `BuilderService`, and `DeploymentService`) share execution infrastructure defined in `execution_types.proto` (job lifecycle states, structured errors with retryability guidance, artifact references, provenance records) and follow the same `Validate*` / `DryRun*` / `Execute*` / `Execute*Stream` / `Submit*Job` / `Get*Job` / `Get*JobResult` / `Cancel*Job` RPC surface. `WorkspaceService` and `ArtifactService` are lifecycle services with their own RPC shape — `WorkspaceService` exposes create/open/get/list/update/promote/retain/release/quota RPCs and `ArtifactService` exposes publish/read/get/inspect/list/retain/release plus retention-policy reads. Workspace and artifact lifecycle contracts live in `workspace_artifact_types.proto`, `workspace_service.proto`, and `artifact_service.proto`. Canonical packaging shapes (`MapPackage`, `AppPackage`, `DeploymentSpec`) live in `packaging_types.proto`. The sections below start with workspace and artifact lifecycle flows, then use `ProcessService` to illustrate the shared execution pattern; render, build, and deploy follow the same execution shape with their own spec types (`RenderSpec`, `BuildSpec`, `DeploymentSpec`).

### Create and Open a Workspace

```csharp
var workspaceClient = new WorkspaceService.WorkspaceServiceClient(channel);

var created = await workspaceClient.CreateWorkspaceAsync(
    new CreateWorkspaceRequest
    {
        Desired = new Workspace
        {
            Quota = new QuotaSpec
            {
                MaxBytes = 10L * 1024 * 1024 * 1024,
                MaxArtifacts = 5000
            },
            DefaultRetention = new RetentionPolicyRef { RetentionPolicyId = "retain-30d" },
            Labels = { ["team"] = "analytics" },
            Metadata = { ["purpose"] = "render-build-deploy" }
        },
        Context = new ExecutionContext
        {
            Metadata = { ["caller"] = "getting-started" }
        }
    });

var workspaceRef = created.Workspace.Ref;

var opened = await workspaceClient.OpenWorkspaceAsync(
    new OpenWorkspaceRequest
    {
        Ref = workspaceRef,
        Context = new ExecutionContext
        {
            Metadata = { ["caller"] = "getting-started" }
        }
    });

Console.WriteLine(
    $"Workspace {opened.Workspace.Ref.WorkspaceId} @ {opened.Workspace.Ref.WorkspaceRevision}");
```

`WorkspaceRef` is the canonical handle. When a request already carries `Ref`, that handle is authoritative; populate `ExecutionContext.Workspace` only when you need it elsewhere and keep it identical. `CreateWorkspace` may seed `quota`, `default_retention`, `labels`, and `metadata`; `UpdateWorkspace` rewrites `quota`, `labels`, and `metadata` only. Promotion, retention, release, and observed expiry stay on the lifecycle RPCs.

### Publish, Inspect, and List Artifacts

```csharp
using Google.Protobuf;

var artifactClient = new ArtifactService.ArtifactServiceClient(channel);
using var publish = artifactClient.PublishArtifact();

await publish.RequestStream.WriteAsync(new PublishArtifactRequest
{
    Header = new ArtifactHeader
    {
        Workspace = workspaceRef,
        ArtifactClass = ArtifactClass.File,
        ContentType = "application/json",
        Retention = new RetentionPolicyRef { RetentionPolicyId = "retain-30d" },
        ProducerRef = "render-job-42"
    }
});

var payload = ByteString.CopyFromUtf8("{\"status\":\"ready\"}");
await publish.RequestStream.WriteAsync(new PublishArtifactRequest
{
    Chunk = new ArtifactChunk
    {
        Data = payload,
        Offset = 0,
        Last = true
    }
});
await publish.RequestStream.CompleteAsync();

var published = await publish.ResponseAsync;
if (published.OutcomeCase != PublishArtifactResponse.OutcomeOneofCase.Result)
{
    Console.WriteLine($"Publish failed: {published.Error.Message}");
    return;
}

var artifact = published.Result;
var inspection = await artifactClient.InspectArtifactAsync(
    new InspectArtifactRequest { Ref = artifact.Ref });

var page = await artifactClient.ListArtifactsAsync(
    new ListArtifactsRequest
    {
        Workspace = artifact.Ref.Workspace,
        ClassFilter = artifact.Ref.ArtifactClass
    });

Console.WriteLine(
    $"{inspection.MaterializationState}: {page.Artifacts.Count} matching artifact(s)");
```

`PublishArtifact` requires an `ArtifactHeader` as the first stream message; every later message is an `ArtifactChunk`. `ArtifactHeader.Workspace` is the authoritative workspace selector for upload. Prefer `InspectArtifact` when you need materialization state, observed size, or hash without paying to stream bytes, and use `ReadArtifact` with `offset_bytes` / `max_bytes` only when you need the body. `ListArtifactsRequest.Workspace` is optional: unset lists artifacts across every workspace visible to the caller; when set it is authoritative over `ExecutionContext.Workspace`. `RetainArtifact` and `ReleaseArtifact` stay unary but return the same in-band `Artifact | ErrorDetail` outcome shape used by `PublishArtifact`.

### Validate and Dry-Run a Plan

#### .NET

```csharp
using Geospatial.V1;

var processClient = new ProcessService.ProcessServiceClient(channel);

// Build a plan with typed steps
var plan = new ExecutionPlan
{
    PlanId = "buffer-analysis-1",
    SpecVersion = "1",
    WorkflowFamily = WorkflowFamily.Analyze
};

plan.Steps.Add(new PlanStep
{
    StepId = "query",
    Kind = "query_features",
    Inputs =
    {
        ["service_id"] = new ParameterValue { StringValue = "parcels" },
        ["where"] = new ParameterValue { StringValue = "ZONE = 'R1'" },
        ["spatial_filter"] = new ParameterValue
        {
            SpatialFilterValue = new SpatialFilter
            {
                Geometry = new Geometry
                {
                    Polygon = new PolygonGeometry
                    {
                        Rings = { /* ring coordinates */ }
                    }
                },
                SpatialRelationship = SpatialRelationship.Intersects
            }
        }
    }
});

plan.Steps.Add(new PlanStep
{
    StepId = "buffer",
    Kind = "geoprocess",
    Inputs =
    {
        ["operation"] = new ParameterValue { StringValue = "buffer" },
        ["distance"] = new ParameterValue { DoubleValue = 100.0 }
    },
    Dependencies = { "query" }
});

// Validate the plan
var validation = await processClient.ValidatePlanAsync(
    new ValidatePlanRequest { Plan = plan });

if (!validation.Valid)
{
    foreach (var issue in validation.Issues)
        Console.WriteLine($"[{issue.Severity}] {issue.NodeId}: {issue.Message}");
    return;
}

// Estimate cost before executing
var dryRun = await processClient.DryRunPlanAsync(
    new DryRunPlanRequest { Plan = plan });

Console.WriteLine($"Estimated duration: {dryRun.Result.EstimatedDurationSeconds}s");
foreach (var artifact in dryRun.Result.EstimatedArtifacts)
    Console.WriteLine($"  {artifact.ArtifactClass}: ~{artifact.EstimatedSizeBytes} bytes");
```

#### TypeScript

```typescript
import { ProcessService } from './gen/geospatial/v1/process_service_pb.js';
import { createClient } from '@connectrpc/connect';

const processClient = createClient(ProcessService, transport);

const plan = {
  planId: 'buffer-analysis-1',
  specVersion: '1',
  workflowFamily: 1, // WORKFLOW_FAMILY_ANALYZE
  steps: [
    {
      stepId: 'query',
      kind: 'query_features',
      inputs: {
        service_id: { kind: { case: 'stringValue', value: 'parcels' } },
        where: { kind: { case: 'stringValue', value: "ZONE = 'R1'" } }
      }
    },
    {
      stepId: 'buffer',
      kind: 'geoprocess',
      inputs: {
        operation: { kind: { case: 'stringValue', value: 'buffer' } },
        distance: { kind: { case: 'doubleValue', value: 100.0 } }
      },
      dependencies: ['query']
    }
  ]
};

const validation = await processClient.validatePlan({ plan });

if (!validation.valid) {
  validation.issues.forEach(issue =>
    console.log(`[${issue.severity}] ${issue.nodeId}: ${issue.message}`)
  );
} else {
  const dryRun = await processClient.dryRunPlan({ plan });
  console.log(`Estimated duration: ${dryRun.result?.estimatedDurationSeconds}s`);
}
```

#### Python

```python
from geospatial.v1 import process_service_pb2
from geospatial.v1 import process_service_pb2_grpc
from geospatial.v1 import execution_types_pb2

process_stub = process_service_pb2_grpc.ProcessServiceStub(channel)

plan = execution_types_pb2.ExecutionPlan(
    plan_id='buffer-analysis-1',
    spec_version='1',
    workflow_family=execution_types_pb2.WORKFLOW_FAMILY_ANALYZE,
    steps=[
        execution_types_pb2.PlanStep(
            step_id='query',
            kind='query_features',
            inputs={
                'service_id': execution_types_pb2.ParameterValue(string_value='parcels'),
                'where': execution_types_pb2.ParameterValue(string_value="ZONE = 'R1'"),
            }
        ),
        execution_types_pb2.PlanStep(
            step_id='buffer',
            kind='geoprocess',
            inputs={
                'operation': execution_types_pb2.ParameterValue(string_value='buffer'),
                'distance': execution_types_pb2.ParameterValue(double_value=100.0),
            },
            dependencies=['query']
        ),
    ]
)

validation = process_stub.ValidatePlan(
    process_service_pb2.ValidatePlanRequest(plan=plan))

if not validation.valid:
    for issue in validation.issues:
        print(f'[{issue.severity}] {issue.node_id}: {issue.message}')
else:
    dry_run = process_stub.DryRunPlan(
        process_service_pb2.DryRunPlanRequest(plan=plan))
    print(f'Estimated duration: {dry_run.result.estimated_duration_seconds}s')
```

### Execute Synchronously

```csharp
var response = await processClient.ExecutePlanAsync(
    new ExecutePlanRequest
    {
        Plan = plan,
        Context = new ExecutionContext
        {
            Workspace = new WorkspaceRef { WorkspaceId = "ws-1" }
        }
    });

switch (response.OutcomeCase)
{
    case ExecutePlanResponse.OutcomeOneofCase.Result:
        Console.WriteLine($"Completed: {response.Result.Summary}");
        foreach (var artifact in response.Result.Artifacts)
            Console.WriteLine($"  Artifact: {artifact.ArtifactId} ({artifact.ArtifactClass})");
        break;
    case ExecutePlanResponse.OutcomeOneofCase.Error:
        Console.WriteLine($"Failed [{response.Error.Category}]: {response.Error.Message}");
        Console.WriteLine($"  Retryability: {response.Error.Retryability}");
        break;
}
```

See the [Protocol Specification](specification.md) for the full RPC surface, streaming execution, async job management, pipeline definitions, and the render/build/deployment contracts (including `MapPackage`, `AppPackage`, `DeploymentSpec`, rollback, and deployment health telemetry).

## Next Steps

- **Explore Examples**: Check the `examples/` directory for complete projects
- **Read the Specification**: Understand the protocol details in `docs/specification.md`
- **Join the Community**: Ask questions in GitHub Discussions
- **Build Something Cool**: Use the protocols in your own projects!

## Common Issues and Solutions

### Buf Generate Fails

```bash
# Clear module cache and regenerate
buf mod clear-cache
buf generate
```

### Import Errors

Make sure you've correctly installed the generated files in your project and imported the required gRPC packages.

### Connection Issues

Verify the server endpoint and ensure your client can reach it:

```bash
# Test basic connectivity
curl -v https://api.example.com/health
```

### SSL/TLS Issues

For development, you may need to disable SSL verification:

```csharp
var channel = GrpcChannel.ForAddress("http://localhost:5000", new GrpcChannelOptions
{
    Credentials = ChannelCredentials.Insecure
});
```

## Support

- **GitHub Issues**: Report bugs and request features
- **Discussions**: Ask questions and share ideas
- **Email**: geospatial-grpc@honua.io
- **Documentation**: Full protocol specification available
