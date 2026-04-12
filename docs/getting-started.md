# Getting Started with Geospatial gRPC

This guide will help you quickly get up and running with the Geospatial gRPC protocols.

## Prerequisites

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
git clone https://github.com/mikemcdougall/geospatial-grpc.git
cd geospatial-grpc
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

```bash
# Only C#
buf generate --template buf.gen.yaml --include-imports --path geospatial/v1 --output gen/csharp

# Only TypeScript
buf generate --template buf.gen.yaml --include-imports --path geospatial/v1 --output gen/typescript
```

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
dotnet add package Google.Protobuf
dotnet add package Grpc.Tools
```

3. **Copy generated files**:
```bash
cp -r ../gen/csharp/* .
```

### TypeScript / JavaScript

1. **Create a new Node.js project**:
```bash
npm init -y
npm install @connectrpc/connect @connectrpc/connect-node
```

2. **Copy generated files**:
```bash
cp -r ../gen/typescript/src .
```

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
cp -r ../gen/python/* .
```

## Step 5: Your First Query

### .NET Example

```csharp
using GeospatialGrpc.V1;
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
    ResultRecordCount = 100
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
import { FeatureService } from './gen/geospatial/v1/feature_service_pb';
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
  resultRecordCount: 100
});

// Process results
console.log(`Found ${response.features.length} features`);
response.features.forEach(feature => {
  console.log(`Feature ID: ${feature.id}`);
  if (feature.geometry?.point) {
    const { x, y } = feature.geometry.point;
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
    result_record_count=100
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
using GeospatialGrpc.V1;

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
    ResultRecordCount = 1000 // Page size
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
var channel = GrpcChannel.ForAddress("https://api.production.com", new GrpcChannelOptions
{
    // Connection settings
    MaxReceiveMessageSize = 16 * 1024 * 1024, // 16MB
    MaxSendMessageSize = 4 * 1024 * 1024,     // 4MB

    // Retry configuration
    ServiceConfig = new ServiceConfig
    {
        MethodConfigs =
        {
            new MethodConfig
            {
                Names = { MethodName.Default },
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

## Step 10: Process Execution and Pipelines

The protocol includes two services for server-side execution workflows:

- **`ProcessService`** — validate, dry-run, and execute geospatial analysis plans (synchronous, streaming, or async job)
- **`PipelineService`** — validate, dry-run, and execute data publishing pipelines with stage-by-stage progress

Both services share execution infrastructure defined in `execution_types.proto`: job lifecycle states, structured errors with retryability guidance, artifact references, and provenance records.

See the [Protocol Specification](specification.md) for the full RPC surface, message definitions, and execution semantics.

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