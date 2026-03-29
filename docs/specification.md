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