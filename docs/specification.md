# Geospatial gRPC Protocol Specification

## Overview

This specification defines standardized gRPC protocols for geospatial data access and mobile field data collection. The protocols are designed to provide type-safe, high-performance alternatives to traditional REST APIs and XML-based form systems.

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

An `ExecutionPlan` contains a sequence of typed steps. Each `PlanStep` has a `kind` (e.g., `query_features`, `geoprocess`, `aggregate`, `render_map`, `export`), typed inputs, and dependency references to other steps. Steps form a DAG that the platform resolves and executes in order.

#### Dry-Run Semantics

`DryRunPlan` validates the plan and returns a `DryRunResult` with estimated duration, expected artifact sizes, identified side effects (such as external publication), and cost estimates. Dry-run execution must not modify any persistent state. Clients should call `DryRunPlan` before `ExecutePlan` for expensive or destructive operations.

#### Job Lifecycle

Jobs transition through these states: `DRAFT` → `VALIDATED` → `RUNNING` → `COMPLETED` or `FAILED`. Additional states include `AWAITING_CLARIFICATION`, `AWAITING_APPROVAL`, and `CANCELLED`. The `GetJob` RPC returns the current state and `JobProgress` with percentage, current node identifier, and timestamps.

#### Error Model

Execution errors are returned as `ErrorDetail` messages with:

- `error_code`: Machine-parseable error code
- `category`: Domain classification (validation, authorization, policy, execution, artifact)
- `retryability`: How to recover (fix plan, fix data, retry transient error, permanent failure)
- `suggested_action`: Human-readable recovery guidance

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

#### Pipeline Definitions

A `PipelineDefinition` describes a data publishing workflow with a source, transformation stages, target, schema mappings, and quality rules. Standard stage kinds include: `inspect_source`, `infer_schema`, `map_schema`, `normalize_crs`, `clean_records`, `dedupe`, `enrich`, `quality_check`, `publish_service`.

#### Publishing Results

`PipelineResult` includes source lineage (original schema, record count, extent), a quality report (valid/invalid/cleaned/deduplicated counts with per-rule issues), published service information, produced artifacts, and a provenance record.

#### Shared Execution Infrastructure

Both services share types defined in `execution_types.proto`:

- **Job lifecycle**: `JobState`, `StageState` enums and `JobProgress` messages
- **Error model**: `ErrorDetail` with `ErrorCategory` and `Retryability` classifications
- **Artifacts**: `ArtifactRef` with class, version, and workspace/producer references
- **Dry-run**: `DryRunResult` with estimated artifacts, side effects, and cost
- **Provenance**: `ProvenanceRecord` with source datasets, assumptions, and timing

#### Node Identifier Convention

Shared messages (`JobProgress`, `StageResult`, `PlanValidationIssue`, `ErrorDetail`) use a neutral `node_id` field to identify the plan node where an event, result, or issue originated. For `ProcessService`, `node_id` correlates to `PlanStep.step_id`. For `PipelineService`, `node_id` correlates to `PipelineStage.stage_id`. Implementations must populate `node_id` with the identifier from the corresponding service-specific definition.

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

Standard gRPC status codes are used for error conditions:

- `NOT_FOUND`: Resource does not exist
- `INVALID_ARGUMENT`: Invalid request parameters
- `PERMISSION_DENIED`: Access denied
- `RESOURCE_EXHAUSTED`: Rate limiting or quota exceeded
- `DEADLINE_EXCEEDED`: Execution timeout
- `FAILED_PRECONDITION`: Required state not met (e.g., plan not validated)
- `CANCELLED`: Client-initiated cancellation
- `INTERNAL`: Server error

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

Process and pipeline execution errors use a structured `ErrorDetail` model with machine-parseable codes, domain categories, and retryability classification:

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
| `transient_backend_error` | Retry the same request |
| `insufficient_quota` | Request quota increase or reduce scope |
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

### Client Implementation

- **Connection Management**: Reuse gRPC channels
- **Error Handling**: Implement retry logic with backoff
- **Offline Support**: Cache data and queue operations
- **Progress Reporting**: Show progress for long operations

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