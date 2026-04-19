# Python Example

This example demonstrates using the Geospatial gRPC protocols from Python with async/await.

## Prerequisites

- Python 3.8 or later
- pip (Python package manager)

## Setup and Running

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Generate Python client from proto files
python -m grpc_tools.protoc \
  --proto_path=../../ \
  --python_out=. \
  --grpc_python_out=. \
  geospatial/v1/*.proto

# Run the example
python main.py
```

## What This Example Shows

1. **Async gRPC**: Using async/await with gRPC for better performance
2. **Feature Queries**: Spatial and attribute-based feature queries
3. **Form Handling**: Dynamic form definitions and submissions
4. **Error Handling**: Proper gRPC error handling with status codes
5. **Type Safety**: Using generated Python stubs for type checking

## Key Features

### Async Context Manager

```python
async with GeospatialGrpcExample() as example:
    await example.run_feature_service_example()
    await example.run_form_service_example()
```

### Feature Queries

```python
request = feature_service_pb2.QueryFeaturesRequest(
    service_id="parks",
    layer_id=0,
    where="AREA > 1000",
    return_geometry=True,
    out_sr=common_pb2.SpatialReference(wkid=4326)
)

response = await stub.QueryFeatures(request)
```

### Form Submission

```python
instance = form_service_pb2.FormInstance(
    instance_id=str(uuid.uuid4()),
    form_id=form.form_id,
    created_by="user-123",
    status=form_service_pb2.InstanceStatus.INSTANCE_STATUS_COMPLETE
)

# Add field values
for control in form.controls:
    value = create_sample_value(control)
    instance.field_values[control.control_id].CopyFrom(value)
```

## Project Structure

```
python/
├── main.py                   # Main example code
├── requirements.txt          # Python dependencies
├── README.md                 # This file
└── geospatial/               # Generated Python modules (after generation)
    └── v1/
        ├── common_pb2.py
        ├── spatial_types_pb2.py
        ├── feature_service_pb2.py
        ├── feature_service_pb2_grpc.py
        ├── form_service_pb2.py
        ├── form_service_pb2_grpc.py
        ├── workspace_artifact_types_pb2.py
        ├── execution_types_pb2.py
        ├── packaging_types_pb2.py
        ├── workspace_service_pb2.py
        ├── workspace_service_pb2_grpc.py
        ├── artifact_service_pb2.py
        ├── artifact_service_pb2_grpc.py
        ├── process_service_pb2.py
        ├── process_service_pb2_grpc.py
        ├── pipeline_service_pb2.py
        ├── pipeline_service_pb2_grpc.py
        ├── render_service_pb2.py
        ├── render_service_pb2_grpc.py
        ├── builder_service_pb2.py
        ├── builder_service_pb2_grpc.py
        ├── deployment_service_pb2.py
        └── deployment_service_pb2_grpc.py
```

## Dependencies

- **grpcio**: Core gRPC library for Python
- **grpcio-tools**: Protocol Buffers compiler and tools
- **protobuf**: Protocol Buffers runtime library

## Advanced Usage

### Streaming Queries

```python
# For large datasets, use streaming
request = feature_service_pb2.QueryFeaturesRequest(
    service_id="big-dataset",
    layer_id=0,
    return_geometry=True
)

async for page in stub.QueryFeaturesStream(request):
    print(f"Processing {len(page.features)} features...")
    for feature in page.features:
        # Process individual feature
        pass

    if page.is_last_page:
        break
```

### Authentication

```python
# API Key authentication
def auth_interceptor(metadata, context):
    metadata.append(('authorization', 'Bearer your-api-key'))

# Create channel with interceptor
interceptors = [grpc.aio.unary_unary_interceptor(auth_interceptor)]
channel = aio.secure_channel('api.example.com:443', credentials, interceptors=interceptors)
```

### Error Handling

```python
try:
    response = await stub.QueryFeatures(request)
except grpc.RpcError as e:
    if e.code() == grpc.StatusCode.NOT_FOUND:
        print("Service or layer not found")
    elif e.code() == grpc.StatusCode.INVALID_ARGUMENT:
        print(f"Invalid request: {e.details()}")
    elif e.code() == grpc.StatusCode.PERMISSION_DENIED:
        print("Access denied")
    else:
        print(f"gRPC error: {e.code()} - {e.details()}")
```

## Integration Examples

### FastAPI Integration

```python
from fastapi import FastAPI
import grpc.aio

app = FastAPI()

@app.on_event("startup")
async def startup():
    app.grpc_channel = grpc.aio.secure_channel("api.example.com:443", credentials)
    app.feature_client = feature_service_pb2_grpc.FeatureServiceStub(app.grpc_channel)

@app.get("/features/{service_id}")
async def get_features(service_id: str, where: str = "1=1"):
    request = feature_service_pb2.QueryFeaturesRequest(
        service_id=service_id,
        layer_id=0,
        where=where,
        return_geometry=True
    )
    response = await app.feature_client.QueryFeatures(request)
    return {"features": [feature_to_dict(f) for f in response.features]}
```

### Django Integration

```python
# settings.py
GRPC_CHANNEL_OPTIONS = {
    'grpc.max_receive_message_length': 16 * 1024 * 1024,  # 16MB
    'grpc.max_send_message_length': 4 * 1024 * 1024,      # 4MB
}

# views.py
from django.http import JsonResponse
import grpc.aio

async def feature_view(request, service_id):
    channel = grpc.aio.secure_channel("api.example.com:443", credentials)
    stub = feature_service_pb2_grpc.FeatureServiceStub(channel)

    # Query features
    grpc_request = feature_service_pb2.QueryFeaturesRequest(
        service_id=service_id,
        where=request.GET.get('where', '1=1')
    )

    response = await stub.QueryFeatures(grpc_request)
    await channel.close()

    return JsonResponse({"features": response.features})
```

## Testing

```python
import pytest
import grpc.aio
from grpc import StatusCode

@pytest.mark.asyncio
async def test_feature_query():
    """Test feature query functionality."""
    async with GeospatialGrpcExample() as example:
        # This would normally use a test server
        pass

@pytest.mark.asyncio
async def test_error_handling():
    """Test proper error handling."""
    # Test with invalid service ID
    with pytest.raises(grpc.RpcError) as exc_info:
        # Make invalid request
        pass

    assert exc_info.value.code() == StatusCode.NOT_FOUND
```

## Next Steps

- **Workspace & Artifact Lifecycle**: Use `WorkspaceService` and `ArtifactService` to create workspaces, publish/read artifacts (client- and server-streaming), and bind retention policies through the canonical `WorkspaceRef` / `ArtifactRef` / `RetentionPolicyRef` handles
- **Execution Workflows**: Use `ProcessService`, `PipelineService`, `RenderService`, `BuilderService`, or `DeploymentService` — they share a `Validate*` / `DryRun*` / `Execute*` / `Execute*Stream` / `Submit*Job` / `Get*Job` / `Get*JobResult` / `Cancel*Job` RPC surface. See the [Getting Started guide](../../docs/getting-started.md#step-10-workspace-artifact-process-pipeline-render-build-and-deployment-workflows).
- **Canonical Packaging**: Consume `MapPackage`, `AppPackage`, and `DeploymentSpec` from `packaging_types.proto` directly rather than wrapping them in bespoke shapes
- **Web Framework**: Integrate with FastAPI, Django, or Flask
- **Data Processing**: Use with pandas, geopandas for analysis
- **Machine Learning**: Feed geospatial data to ML models
- **Real-time Processing**: Build streaming data pipelines
- **Microservices**: Create geospatial microservice architecture