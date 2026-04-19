# Geospatial gRPC Protocol Specification

## Overview

This specification defines standardized gRPC protocols for geospatial data access, mobile field data collection, process execution, data publishing pipelines, map rendering, application building, and deployment. The protocols provide type-safe, high-performance service contracts for spatial feature CRUD, mobile forms, analysis workflow execution, dataset publishing, packaged map composition, application bundle synthesis, and deployment promotion.

## Design Principles

### 1. Type Safety
- Strong typing prevents integration errors
- Clear data contracts between client and server
- Compile-time validation of protocol usage

### 2. Mobile First
- Optimized for battery life and limited bandwidth
- Device capability awareness (GPS, camera, network)
- Offline-first design with synchronization

### 3. Streaming Support
- Efficient handling of large datasets via streaming
- Real-time collaborative editing
- Progressive loading for improved UX

### 4. Cross-Platform
- Language-agnostic protocol definitions
- Native mobile, web, and desktop support
- Consistent behavior across implementations

## Core Services

### FeatureService

The `FeatureService` provides CRUD operations for geospatial features. It supports:

- **Query Operations**: Spatial and attribute-based filtering
- **Streaming**: Large result sets via server streaming
- **Editing**: Add, update, delete operations with transaction support

#### Key Methods

```protobuf
service FeatureService {
  rpc QueryFeatures(QueryFeaturesRequest) returns (QueryFeaturesResponse);
  rpc QueryFeaturesStream(QueryFeaturesRequest) returns (stream FeaturePage);
  rpc ApplyEdits(ApplyEditsRequest) returns (ApplyEditsResponse);
}
```

#### Spatial Reference Handling

All geometry coordinates are assumed to be in the spatial reference specified by the layer's metadata. Clients can request output in a different spatial reference using the `out_sr` parameter.

#### Geometry Encoding

Geometries are encoded using structured Protocol Buffer messages rather than WKT or WKB for better type safety and performance:

- `PointGeometry`: Single point with optional Z/M values
- `PolylineGeometry`: One or more paths (LineString/MultiLineString)
- `PolygonGeometry`: Exterior ring plus optional holes
- `MultiPolygonGeometry`: Collection of polygons

### FormService

The `FormService` provides mobile data collection capabilities as a modern alternative to OpenRosa XML forms:

- **Dynamic Forms**: Server-defined form schemas
- **Rich Controls**: Location, media, validation, conditional logic
- **Mobile Optimization**: Device-aware form rendering
- **Real-time Collaboration**: Multi-user form editing

#### Key Methods

```protobuf
service FormService {
  rpc GetFormDefinition(GetFormDefinitionRequest) returns (GetFormDefinitionResponse);
  rpc SubmitFormData(SubmitFormDataRequest) returns (SubmitFormDataResponse);
  rpc StreamFormUpdates(stream FormUpdateRequest) returns (stream FormUpdateResponse);
  rpc ValidateFormData(ValidateFormDataRequest) returns (ValidateFormDataResponse);
  rpc GetFormMetadata(GetFormMetadataRequest) returns (GetFormMetadataResponse);
}
```

### ProcessService

The `ProcessService` provides typed RPC access to geospatial process execution for analysis workflows. It supports the full execution lifecycle:

- **Plan Validation**: Check a plan for structural and capability issues before execution
- **Dry-Run Estimation**: Estimate cost, duration, artifacts, and side effects without executing
- **Synchronous Execution**: Run a plan and receive the complete result
- **Streaming Execution**: Run a plan and receive progress events as they occur
- **Asynchronous Jobs**: Submit long-running plans as jobs with polling and cancellation

#### Key Methods

```protobuf
service ProcessService {
  rpc ValidatePlan(ValidatePlanRequest) returns (ValidatePlanResponse);
  rpc DryRunPlan(DryRunPlanRequest) returns (DryRunPlanResponse);
  rpc ExecutePlan(ExecutePlanRequest) returns (ExecutePlanResponse);
  rpc ExecutePlanStream(ExecutePlanRequest) returns (stream ExecutionEvent);
  rpc SubmitJob(SubmitJobRequest) returns (SubmitJobResponse);
  rpc GetJob(GetJobRequest) returns (GetJobResponse);
  rpc GetJobResult(GetJobResultRequest) returns (GetJobResultResponse);
  rpc CancelJob(CancelJobRequest) returns (CancelJobResponse);
}
```

#### Execution Plans

An `ExecutionPlan` contains a sequence of typed steps. Each `PlanStep` has a `kind` (e.g., `query_features`, `geoprocess`, `aggregate`, `render_map`, `export`), typed inputs as `map<string, ParameterValue>`, and dependency references to other steps. Steps form a DAG that the platform resolves and executes in order. `ParameterValue` supports scalar, list, and struct branches for generic parameters, plus typed branches for canonical geospatial messages (`SpatialFilter`, `SpatialReference`, `Geometry`, `Extent`, `StatisticDefinition`). Typed branches let standard step kinds reference existing protocol-owned types directly instead of requiring ad-hoc struct encoding.

Standard step kind parameter conventions:

| Step Kind | Parameter Key | Typed Branch |
|-----------|--------------|--------------|
| `query_features` | `spatial_filter` | `spatial_filter_value` (`SpatialFilter`) |
| `query_features` | `out_sr` | `spatial_reference_value` (`SpatialReference`) |
| `query_features` | `out_statistics` | `list_value` of `statistic_value` (`StatisticDefinition`) |
| `query_features` | `object_ids` | `list_value` of `int64_value` |
| `query_features` | `out_fields` | `list_value` of `string_value` |
| `geoprocess` | `input_geometry` | `geometry_value` (`Geometry`) |
| `geoprocess` | `clip_extent` | `extent_value` (`Extent`) |

Pipeline stage kinds follow the same convention. For example, `normalize_crs` uses `spatial_reference_value` for its `target_sr` parameter.

#### Validation Semantics

`ValidatePlan` and `DryRunPlan` are advisory — they let clients check a plan before committing to execution, but they do not produce a server-side validation token. Servers re-validate the plan on `ExecutePlan`, `ExecutePlanStream`, and `SubmitJob` and return `INVALID_ARGUMENT` if the plan is structurally invalid. Clients are encouraged to call `ValidatePlan` or `DryRunPlan` first but are not required to.

#### Dry-Run Semantics

`DryRunPlan` validates the plan and returns a `DryRunResult` with estimated duration, expected artifact sizes, identified side effects (such as external publication), and cost estimates. The response includes the same `valid` and `issues` fields as `ValidatePlan`, so a single call provides both validation and estimation. Dry-run execution must not modify any persistent state. Clients should call `DryRunPlan` before `ExecutePlan` for expensive or destructive operations.

#### Job Lifecycle

Jobs transition through these states: `DRAFT` → `VALIDATED` → `RUNNING` → `COMPLETED` or `FAILED`. Additional states include `AWAITING_CLARIFICATION`, `AWAITING_APPROVAL`, and `CANCELLED`. The `GetJob` RPC returns the current state and `JobProgress` with percentage, current node identifier, and timestamps.

#### Process Results

`ExecutionResult` contains the output of a completed process execution: a `result_id`, the terminal `status` (`JobState`), a human-readable `summary`, any `assumptions` recorded during execution, produced `artifacts` (`ArtifactRef` list), per-step `stage_results`, and a `ProvenanceRecord` with source dataset references and timing.

#### Error Model

Execution errors are returned as `ErrorDetail` messages with:

- `error_code`: Machine-parseable error code
- `category`: Domain classification (validation, authorization, policy, execution, artifact, packaging, deployment)
- `message`: Human-readable error description
- `phase`: Execution phase where the error occurred (e.g., validation, planning, execution)
- `node_id`: Identifies the plan step that produced the error (correlates to `PlanStep.step_id`; see [Node Identifier Convention](#node-identifier-convention))
- `retryability`: How to recover (fix plan, fix data, retry transient error, permanent failure)
- `suggested_action`: Human-readable recovery guidance
- `details`: Optional key-value map for additional machine-readable context

### PipelineService

The `PipelineService` provides typed RPC access to data publishing pipeline execution. It supports:

- **Pipeline Validation**: Check a pipeline definition for structural and capability issues
- **Dry-Run Estimation**: Estimate the impact of running a pipeline without side effects
- **Synchronous Execution**: Run a pipeline and receive the complete result
- **Streaming Execution**: Run a pipeline and receive stage-by-stage progress events
- **Asynchronous Jobs**: Submit long-running pipelines as jobs with polling and cancellation

#### Key Methods

```protobuf
service PipelineService {
  rpc ValidatePipeline(ValidatePipelineRequest) returns (ValidatePipelineResponse);
  rpc DryRunPipeline(DryRunPipelineRequest) returns (DryRunPipelineResponse);
  rpc ExecutePipeline(ExecutePipelineRequest) returns (ExecutePipelineResponse);
  rpc ExecutePipelineStream(ExecutePipelineRequest) returns (stream PipelineEvent);
  rpc SubmitPipelineJob(SubmitPipelineJobRequest) returns (SubmitPipelineJobResponse);
  rpc GetPipelineJob(GetPipelineJobRequest) returns (GetPipelineJobResponse);
  rpc GetPipelineJobResult(GetPipelineJobResultRequest) returns (GetPipelineJobResultResponse);
  rpc CancelPipelineJob(CancelPipelineJobRequest) returns (CancelPipelineJobResponse);
}
```

#### Pipeline Validation Semantics

`ValidatePipeline` and `DryRunPipeline` are advisory. Servers re-validate the pipeline definition on `ExecutePipeline`, `ExecutePipelineStream`, and `SubmitPipelineJob` and return `INVALID_ARGUMENT` if invalid. Clients are encouraged to validate first but are not required to. `DryRunPipeline` returns the same `valid` and `issues` fields alongside the `DryRunResult`, so a single call provides both validation and estimation.

#### Pipeline Definitions

A `PipelineDefinition` describes a data publishing workflow with a source, transformation stages, target, schema mappings, and quality rules. Standard stage kinds include: `inspect_source`, `infer_schema`, `map_schema`, `normalize_crs`, `clean_records`, `dedupe`, `enrich`, `quality_check`, `publish_service`.

#### Publishing Results

`PipelineResult` contains the output of a completed pipeline execution: a `result_id`, the terminal `status` (`JobState`), a human-readable `summary`, source lineage (source reference, record count, inferred schema, spatial reference, and extent), a quality report (total, valid, invalid, cleaned, and deduplicated record counts with per-rule issues), published service information, produced `artifacts`, per-stage `stage_results`, and a `ProvenanceRecord`.

### RenderService

The `RenderService` provides typed RPC access to map composition and packaging. It produces a `MapPackage` — a deterministic, MapLibre-compatible map composition — that downstream runtimes can hydrate without interpretation drift. It supports:

- **Render Validation**: Check a render spec for structural and capability issues
- **Dry-Run Estimation**: Estimate the cost and artifact footprint of a render without side effects
- **Synchronous Execution**: Run a render and receive the complete `MapPackage`
- **Streaming Execution**: Receive progress and stage events as rendering proceeds
- **Asynchronous Jobs**: Submit long-running renders as jobs with polling and cancellation

#### Key Methods

```protobuf
service RenderService {
  rpc ValidateRender(ValidateRenderRequest) returns (ValidateRenderResponse);
  rpc DryRunRender(DryRunRenderRequest) returns (DryRunRenderResponse);
  rpc ExecuteRender(ExecuteRenderRequest) returns (ExecuteRenderResponse);
  rpc ExecuteRenderStream(ExecuteRenderRequest) returns (stream RenderEvent);
  rpc SubmitRenderJob(SubmitRenderJobRequest) returns (SubmitRenderJobResponse);
  rpc GetRenderJob(GetRenderJobRequest) returns (GetRenderJobResponse);
  rpc GetRenderJobResult(GetRenderJobResultRequest) returns (GetRenderJobResultResponse);
  rpc CancelRenderJob(CancelRenderJobRequest) returns (CancelRenderJobResponse);
}
```

#### Render Specs

A `RenderSpec` describes a map composition: `style_spec` (MapLibre style hints as a typed `ParameterMap`), one or more `LayerBinding` entries (typed source kind, `source_ref`, typed `filter`, typed `style_overrides`), a `target_spatial_reference`, an optional `target_extent`, and a `preview_only` flag. The typed `ParameterValue` branches (`spatial_filter_value`, `spatial_reference_value`, `geometry_value`, `extent_value`) apply here the same way they do to `PlanStep` inputs.

#### Render Validation and Dry-Run Semantics

`ValidateRender` and `DryRunRender` are advisory, matching `ValidatePlan` and `DryRunPlan`. Servers re-validate the render spec on `ExecuteRender`, `ExecuteRenderStream`, and `SubmitRenderJob`. `DryRunRender` returns the validation outcome alongside a `DryRunResult`.

#### Render Results

`RenderResult` contains: `result_id`, terminal `status`, human-readable `summary`, any `assumptions` recorded during execution, the produced `map_package` (a canonical `MapPackage`), produced `artifacts`, per-stage `stage_results`, and a `ProvenanceRecord`. When `RenderSpec.preview_only` is true, `map_package` may be unset and the preview artifact is carried on `MapPackage.preview_artifact` instead of the packaged outputs.

#### MapPackage Contract

`MapPackage` is the canonical map composition object shared across services and consumer SDKs:

- `package_id`, `spec_version` — stable identifier and MapPackage contract version (independent of the proto package version)
- `map_artifact`, `style_artifact`, `preview_artifact` — `ArtifactRef` handles for the packaged map bundle, the MapLibre style JSON, and an optional preview
- `spatial_reference`, `extent` — canonical CRS and envelope
- `source_refs` — upstream dataset references for provenance lookups
- `metadata` — free-form display metadata (title, description, attribution)
- `workspace_ref` — workspace handle consistent with `ArtifactRef.workspace_ref`

MapLibre style JSON is carried as opaque bytes inside `style_artifact`, not typed proto fields, so MapPackage evolution is decoupled from upstream MapLibre releases.

#### Consumer Expectations

- `honua-server-731` packages `MapPackage` outputs without redefining its shape.
- `honua-sdk-js-21` hydrates a MapLibre runtime directly from a `MapPackage`, keying compatibility on `MapPackage.spec_version`.
- MCP extensions and the operator orchestration host call `ExecuteRender` / `ExecuteRenderStream` without wrapping them in bespoke render shapes.

### BuilderService

The `BuilderService` provides typed RPC access to application bundle synthesis. It produces an `AppPackage` — a deterministic bundle — suitable for direct deployment or for embedding `MapPackage` references. It supports:

- **Build Validation**: Check a build spec for structural and capability issues
- **Dry-Run Estimation**: Estimate the cost and artifact footprint of a build without side effects
- **Synchronous Execution**: Run a build and receive the complete `AppPackage`
- **Streaming Execution**: Receive progress and stage events as the build proceeds
- **Asynchronous Jobs**: Submit long-running builds as jobs with polling and cancellation

#### Key Methods

```protobuf
service BuilderService {
  rpc ValidateBuild(ValidateBuildRequest) returns (ValidateBuildResponse);
  rpc DryRunBuild(DryRunBuildRequest) returns (DryRunBuildResponse);
  rpc ExecuteBuild(ExecuteBuildRequest) returns (ExecuteBuildResponse);
  rpc ExecuteBuildStream(ExecuteBuildRequest) returns (stream BuildEvent);
  rpc SubmitBuildJob(SubmitBuildJobRequest) returns (SubmitBuildJobResponse);
  rpc GetBuildJob(GetBuildJobRequest) returns (GetBuildJobResponse);
  rpc GetBuildJobResult(GetBuildJobResultRequest) returns (GetBuildJobResultResponse);
  rpc CancelBuildJob(CancelBuildJobRequest) returns (CancelBuildJobResponse);
}
```

#### Build Specs

A `BuildSpec` describes an application synthesis request: `template_ref` (app template registry reference), `intent` (typed `ParameterMap` — title, summary, audience, capability flags), one or more `DataBinding` entries (typed source kind, `source_ref`, typed `selection`, role), `map_package_refs` for embedded maps, and `target_platforms` (e.g., `"web"`, `"mobile"`).

#### Build Validation and Dry-Run Semantics

`ValidateBuild` and `DryRunBuild` are advisory. Servers re-validate the build spec on `ExecuteBuild`, `ExecuteBuildStream`, and `SubmitBuildJob`. `DryRunBuild` returns the validation outcome alongside a `DryRunResult`.

#### Build Results

`BuildResult` contains: `result_id`, terminal `status`, human-readable `summary`, `assumptions`, the produced `app_package` (a canonical `AppPackage`), produced `artifacts`, per-stage `stage_results`, and a `ProvenanceRecord`.

#### AppPackage Contract

`AppPackage` is the canonical application bundle object shared across services and consumer SDKs:

- `package_id`, `spec_version` — stable identifier and AppPackage contract version
- `bundle_artifact`, `manifest_artifact` — `ArtifactRef` handles for the built static bundle and the typed manifest (routes, entry points, capabilities)
- `map_package_refs` — identifiers of `MapPackage` instances embedded in the app
- `runtime_config` — typed `ParameterMap` of runtime configuration (feature flags, env bindings)
- `metadata` — free-form display metadata (title, description, icons)
- `workspace_ref` — workspace handle consistent with `ArtifactRef.workspace_ref`

#### Consumer Expectations

- `honua-server-731` promotes a `BuildResult.app_package` into a packaged artifact set for deployment.
- `honua-sdk-js-21` can discover embedded `map_package_refs` directly from the `AppPackage` and hydrate each runtime.
- MCP extensions and the operator orchestration host call `ExecuteBuild` / `ExecuteBuildStream` without wrapping them in bespoke build shapes.

### DeploymentService

The `DeploymentService` provides typed RPC access to deployment promotion and lifecycle management. A deployment promotes an `AppPackage`, `MapPackage`, or other deployable `ArtifactRef` to a live target. It supports:

- **Deployment Validation**: Check a deployment spec for structural and capability issues
- **Dry-Run Estimation**: Estimate the cost and impact of a deployment without applying it
- **Synchronous Execution**: Run a deployment and receive the complete result
- **Streaming Execution**: Receive progress and stage events as the deployment proceeds
- **Asynchronous Jobs**: Submit long-running deployments as jobs with polling and cancellation
- **Rollback**: Revert to a prior deployment revision
- **Health Telemetry**: Point-in-time snapshots and continuous streaming

#### Key Methods

```protobuf
service DeploymentService {
  rpc ValidateDeployment(ValidateDeploymentRequest) returns (ValidateDeploymentResponse);
  rpc DryRunDeployment(DryRunDeploymentRequest) returns (DryRunDeploymentResponse);
  rpc ExecuteDeployment(ExecuteDeploymentRequest) returns (ExecuteDeploymentResponse);
  rpc ExecuteDeploymentStream(ExecuteDeploymentRequest) returns (stream DeploymentEvent);
  rpc SubmitDeploymentJob(SubmitDeploymentJobRequest) returns (SubmitDeploymentJobResponse);
  rpc GetDeploymentJob(GetDeploymentJobRequest) returns (GetDeploymentJobResponse);
  rpc GetDeploymentJobResult(GetDeploymentJobResultRequest) returns (GetDeploymentJobResultResponse);
  rpc CancelDeploymentJob(CancelDeploymentJobRequest) returns (CancelDeploymentJobResponse);
  rpc RollbackDeployment(RollbackDeploymentRequest) returns (RollbackDeploymentResponse);
  rpc GetDeploymentHealth(GetDeploymentHealthRequest) returns (GetDeploymentHealthResponse);
  rpc StreamDeploymentHealth(StreamDeploymentHealthRequest) returns (stream DeploymentHealthEvent);
}
```

#### Deployment Specs

A `DeploymentSpec` captures the desired state of a running deployment: `deployment_id`, `spec_version`, a `package_ref` oneof (`AppPackage`, `MapPackage`, or `ArtifactRef` — which handles `SERVICE_DEFINITION` and other deployable artifact classes), a `DeploymentTarget` (logical target with `environment` and `region`; cloud backend specifics are intentionally out of scope), a `DeploymentStrategy` (`IMMEDIATE`, `BLUE_GREEN`, `CANARY`, `ROLLING`), one or more `HealthCheck` probes, and a `RollbackPolicy`.

Every deployment request also carries a `DeploymentOperationMode` (`CREATE`, `UPDATE`, `REDEPLOY`) so the server can decide whether the spec represents a fresh deployment or an update.

#### Deployment Validation and Dry-Run Semantics

`ValidateDeployment` and `DryRunDeployment` are advisory. Servers re-validate the deployment spec on `ExecuteDeployment`, `ExecuteDeploymentStream`, `SubmitDeploymentJob`, and `RollbackDeployment`. `DryRunDeployment` returns the validation outcome alongside a `DryRunResult`.

#### Deployment Results

`DeploymentResult` contains: `result_id`, terminal `status`, human-readable `summary`, `assumptions`, `deployment_id`, a server-assigned `revision` tag, one or more `DeploymentEndpoint` entries, the committed `spec`, produced `artifacts` (service descriptors, manifests), per-stage `stage_results`, and a `ProvenanceRecord`.

#### Rollback

`RollbackDeployment` reverts a deployment to a prior revision. When `target_revision` is empty, the server selects the immediately prior successful revision. The response follows the same `outcome` oneof pattern as `ExecuteDeployment`: gRPC status is `OK` and the response carries either a `DeploymentResult` or an `ErrorDetail`.

#### Health Telemetry

- `GetDeploymentHealth` returns a point-in-time health snapshot: overall `DeploymentHealthStatus` (`HEALTHY`, `DEGRADED`, `UNHEALTHY`, `UNKNOWN`), `HealthCheckResult` entries, and an `observed_at` timestamp.
- `StreamDeploymentHealth` streams `DeploymentHealthEvent` messages continuously. Servers MAY terminate the stream with `DEADLINE_EXCEEDED` after a documented idle window; clients reconnect to resume telemetry, matching the expectations for `ExecuteRenderStream` / `ExecutePlanStream`.

#### Consumer Expectations

- `honua-server-732` runs `DeploymentJob` workflows against this contract without redefining deployment or health shapes.
- `honua-sdk-js-21` surfaces deployment state and health using `DeploymentResult`, `DeploymentEndpoint`, and `DeploymentHealthEvent` directly.
- MCP extensions (`honua-server-728`, `honua-server-738`) and the operator orchestration host compose multi-service promotion flows — render → build → deploy — without redefining intermediate shapes.

#### Shared Execution Infrastructure

`ProcessService`, `PipelineService`, `RenderService`, `BuilderService`, and `DeploymentService` share types defined in `execution_types.proto`:

- **Job lifecycle**: `JobState`, `StageState` enums and `JobProgress` messages
- **Error model**: `ErrorDetail` with `ErrorCategory` and `Retryability` classifications
- **Artifacts**: `ArtifactRef` with class, version, and workspace/producer references
- **Dry-run**: `DryRunResult` with estimated artifacts, side effects, and cost
- **Provenance**: `ProvenanceRecord` with source datasets, assumptions, and timing
- **Parameters**: `ParameterValue` (scalar/list/struct/typed geospatial) for step inputs and stage config

#### Canonical Packaging Types

`MapPackage`, `AppPackage`, and `DeploymentSpec` are shared across services and are defined in `packaging_types.proto`. They are shape contracts only — artifact materialization rules (where bytes live, retention, immutability guarantees) live in a separate workspace/artifact contract. Deployment health surface types (`DeploymentTarget`, `DeploymentStrategy`, `HealthCheck`, `HealthCheckResult`, `RollbackPolicy`, `DeploymentEndpoint`, `DeploymentHealthStatus`) also live in `packaging_types.proto` so they can be reused without importing service definitions.

#### Execution Context

`ExecutePlanRequest`, `ExecutePipelineRequest`, `ExecuteRenderRequest`, `ExecuteBuildRequest`, and `ExecuteDeploymentRequest` each accept an optional `ExecutionContext`:

- `workspace_id`: Scopes artifacts and job state to a workspace.
- `timeout_seconds`: Server-enforced execution deadline. If the timeout is reached, the server reports it as an execution-phase error via `ErrorDetail` (see [Execution Errors](#execution-errors)).
- `metadata`: Arbitrary key-value pairs forwarded to the execution environment (e.g., correlation IDs, caller tags).

#### Node Identifier Convention

Shared messages (`StageResult`, `PlanValidationIssue`, `ErrorDetail`) use a `node_id` field and `JobProgress` uses a `current_node_id` field to identify the plan node where an event, result, or issue originated. For `ProcessService`, the value correlates to `PlanStep.step_id`. For `PipelineService`, it correlates to `PipelineStage.stage_id`. For `RenderService`, `BuilderService`, and `DeploymentService`, the value correlates to an internal stage identifier chosen by the server (e.g., render stage, build phase, deployment step). Implementations must populate these fields with the identifier from the corresponding service-specific definition.

## Data Types

### Common Types

#### AttributeValue

Represents typed attribute values with explicit null handling:

```protobuf
message AttributeValue {
  oneof value {
    string string_value = 1;
    int32 int32_value = 2;
    int64 int64_value = 3;
    double double_value = 4;
    float float_value = 5;
    bool bool_value = 6;
    int64 datetime_value = 7; // UTC milliseconds since epoch
    bytes bytes_value = 8;
    NullValue null_value = 9;
  }
}
```

#### SpatialReference

Identifies coordinate systems using multiple formats:

```protobuf
message SpatialReference {
  int32 wkid = 1;           // Well-known ID (EPSG code)
  int32 latest_wkid = 2;    // Latest EPSG code for this CRS
  string wkt = 3;           // Well-Known Text definition
}
```

### Spatial Types

All spatial types support optional Z (elevation) and M (measure) coordinates for 3D and linear referencing use cases.

#### Coordinate Systems

The protocol supports arbitrary coordinate systems via EPSG codes and WKT definitions. Common systems include:

- **WGS 84 Geographic** (EPSG:4326) - GPS coordinates
- **Web Mercator** (EPSG:3857) - Web mapping
- **State Plane** (EPSG:26xx) - US surveying
- **UTM Zones** (EPSG:32xxx) - Global metric

### Form Types

#### Control Types

The form system supports rich control types optimized for mobile data collection:

- **TextInputControl**: Single/multi-line text with validation
- **NumericInputControl**: Numbers with type constraints
- **SelectControl**: Single/multi-select with custom styling
- **DateTimeControl**: Date, time, or datetime selection
- **LocationControl**: GPS coordinate capture with accuracy requirements
- **MediaControl**: Photo, video, audio, file attachments
- **BooleanControl**: Yes/no, true/false input
- **GroupControl**: Logical grouping of related fields

#### Mobile Optimizations

Forms adapt to device capabilities and conditions:

- **Network Awareness**: Compress media on cellular connections
- **Battery Optimization**: Reduce GPS accuracy and animations on low battery
- **Device Integration**: Use native controls and input methods
- **Offline Support**: Cache forms and queue submissions

## Error Handling

### gRPC Status Codes

Standard gRPC status codes are used for request-phase failures — errors detected before execution begins. The server returns a non-OK gRPC status with no response body:

- `NOT_FOUND`: Resource does not exist
- `INVALID_ARGUMENT`: Invalid request parameters
- `PERMISSION_DENIED`: Access denied
- `RESOURCE_EXHAUSTED`: Rate limiting or quota exceeded
- `FAILED_PRECONDITION`: Required state not met (e.g., job not in expected state)
- `INTERNAL`: Server error

`DEADLINE_EXCEEDED` and `CANCELLED` may arrive as gRPC-level status codes from client deadlines or transport-layer cancellation. Server-detected execution timeouts and server-initiated cancellations are reported via `ErrorDetail` (see [Execution Errors](#execution-errors)).

### Application Errors

Application-specific errors are returned in response messages:

```protobuf
message EditError {
  int32 code = 1;           // Application error code
  string message = 2;       // Human-readable error message
}
```

### Validation Errors

Form validation errors include severity levels:

```protobuf
enum ValidationSeverity {
  VALIDATION_SEVERITY_ERROR = 1;   // Prevents submission
  VALIDATION_SEVERITY_WARNING = 2; // Shows warning but allows submission
  VALIDATION_SEVERITY_INFO = 3;    // Informational only
}
```

### Execution Errors

Process, pipeline, render, build, and deployment execution errors use a structured `ErrorDetail` model with machine-parseable codes, domain categories, and retryability classification. Execution-phase failures — errors that occur after the server begins executing a plan, pipeline, render, build, or deployment — are always reported through `ErrorDetail` rather than gRPC status codes, so the structured error model is available to the client. The error surface is consistent across execution modes:

- **Streaming** (`ExecutePlanStream` / `ExecutePipelineStream` / `ExecuteRenderStream` / `ExecuteBuildStream` / `ExecuteDeploymentStream`): A terminal `error` event carries the `ErrorDetail`.
- **Unary** (`ExecutePlan` / `ExecutePipeline` / `ExecuteRender` / `ExecuteBuild` / `ExecuteDeployment` / `RollbackDeployment`): The gRPC status is `OK` and the response `outcome` oneof carries either `result` or `error`. The `oneof` guarantees mutual exclusion (at most one branch is set on the wire); servers MUST populate exactly one.
- **Async results** (`GetJobResult` / `GetPipelineJobResult` / `GetRenderJobResult` / `GetBuildJobResult` / `GetDeploymentJobResult`): The gRPC status is `OK` and the response `outcome` oneof carries `result` or `error` for completed/failed jobs.

| Category | Description |
|----------|-------------|
| `validation` | Plan or pipeline definition is structurally invalid |
| `authorization` | Caller lacks required permissions |
| `policy` | Operation violates platform policy |
| `execution` | Runtime failure during step execution |
| `artifact` | Artifact production or storage failure |
| `packaging` | Build or packaging failure |
| `deployment` | Deployment or publication failure |

Each error includes a `retryability` field to guide client recovery:

| Retryability | Client Action |
|-------------|---------------|
| `fix_plan_and_retry` | Revise the plan and resubmit |
| `fix_data_and_retry` | Address source data issues |
| `insufficient_quota` | Request quota increase or reduce scope |
| `transient_backend_error` | Retry the same request |
| `permanent_failure` | Operation cannot succeed as specified |

## Security Considerations

### Authentication

The protocol does not prescribe authentication mechanisms. Implementations may use:

- **API Keys**: Simple token-based authentication
- **OAuth 2.0**: Industry standard for web/mobile apps
- **JWT**: Self-contained tokens with claims
- **mTLS**: Mutual TLS for service-to-service

### Authorization

Access control is service-specific. Consider:

- **Service-level**: Can user access this feature service?
- **Layer-level**: Can user read/write this layer?
- **Feature-level**: Can user edit this specific feature?
- **Field-level**: Can user see/modify this attribute?

### Data Privacy

Sensitive data handling:

- **Location Privacy**: GPS coordinates may be sensitive
- **Media Privacy**: Photos may contain PII
- **Audit Logs**: Track data access for compliance
- **Encryption**: Protect data in transit and at rest

## Performance Considerations

### Streaming

Use streaming for:

- **Large Result Sets**: > 1000 features
- **Real-time Updates**: Live collaboration
- **Progressive Loading**: Improve perceived performance

### Caching

Consider caching strategies for:

- **Form Definitions**: Cache on device for offline use
- **Layer Metadata**: Reduce repeated metadata requests
- **Spatial Reference**: Cache CRS definitions
- **Media Thumbnails**: Cache preview images

### Pagination

For non-streaming queries, use offset-based pagination:

```protobuf
message QueryFeaturesRequest {
  int32 result_offset = 8;
  int32 result_record_count = 9;
}
```

## Versioning

The protocol is versioned by its proto package (`geospatial.v1`).
Within a major version, all releases maintain **wire and JSON compatibility**:
existing serialized messages remain deserializable, and JSON field names do not change.

| Change Type | Examples | Compatibility |
|-------------|----------|:-------------:|
| Additive | New optional field, new enum value, new RPC | Safe within major version |
| Documentation | Comment or spec updates | Safe within major version |
| Breaking | Remove/rename field, change type/number | Requires new major version |

For the full versioning policy, deprecation rules, and breaking-change governance process,
see [`VERSIONING.md`](../VERSIONING.md).

## Implementation Guidelines

### Server Implementation

- **Spatial Indexing**: Use spatial indexes for query performance
- **Transaction Support**: Implement rollback for failed edits
- **Connection Pooling**: Manage database connections efficiently
- **Rate Limiting**: Protect against abuse
- **Dry-Run Isolation**: `DryRunPlan`, `DryRunPipeline`, `DryRunRender`, `DryRunBuild`, and `DryRunDeployment` must not modify persistent state or produce side effects
- **Job Cancellation**: `CancelJob` / `CancelPipelineJob` / `CancelRenderJob` / `CancelBuildJob` / `CancelDeploymentJob` is best-effort; the server should transition the job to `CANCELLED` as soon as practical but may complete the current stage first
- **Health Stream Lifetime**: `StreamDeploymentHealth` servers may terminate a long-lived health stream with `DEADLINE_EXCEEDED` after a documented idle window; clients are expected to reconnect
- **Node ID Population**: Populate `node_id` in `StageResult`, `PlanValidationIssue`, and `ErrorDetail` — and `current_node_id` in `JobProgress` — with the step or stage identifier from the originating service

### Client Implementation

- **Connection Management**: Reuse gRPC channels
- **Error Handling**: Implement retry logic with backoff; use the `retryability` field in `ErrorDetail` to decide whether to retry, revise, or abort
- **Offline Support**: Cache data and queue operations
- **Progress Reporting**: Show progress for long operations
- **Streaming Consumption**: Consume `ExecutePlanStream` / `ExecutePipelineStream` / `ExecuteRenderStream` / `ExecuteBuildStream` / `ExecuteDeploymentStream` events incrementally; expect interleaved `progress`, `stage_result`, and a terminal `result` or `error` event. For `StreamDeploymentHealth`, expect continuous `DeploymentHealthEvent` messages and be prepared to reconnect after `DEADLINE_EXCEEDED`.

## Compliance and Standards

### OGC Compatibility

While gRPC-native, the protocol aligns with OGC standards:

- **Simple Features**: Geometry model based on OGC SF
- **Filter Encoding**: Where clauses follow SQL patterns
- **CRS**: Coordinate reference systems per OGC standards

### OpenRosa Compatibility

Form definitions provide equivalent functionality to OpenRosa:

- **XForm Elements**: All XForm capabilities represented
- **Validation Rules**: Constraint and relevance expressions
- **Media Handling**: Photo, video, audio attachments

## Future Considerations

### Planned Enhancements

- **Vector Tiles**: Streaming tile-based data access
- **Temporal Support**: Time-aware queries and features
- **Raster Data**: Support for imagery and grids
- **3D Geometries**: Enhanced 3D spatial operations

### Standards Submission

This protocol may be submitted to relevant standards bodies:

- **OGC**: Open Geospatial Consortium for geospatial standards
- **IETF**: Internet Engineering Task Force for protocol standards
- **ISO**: International Organization for Standardization