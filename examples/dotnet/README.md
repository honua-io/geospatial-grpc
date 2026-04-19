# .NET Example

This example demonstrates using the Geospatial gRPC protocols from C# / .NET.

## Prerequisites

- .NET 8.0 or later
- Visual Studio, Visual Studio Code, or any .NET-compatible IDE

## Running the Example

```bash
# Restore packages
dotnet restore

# Run the example
dotnet run
```

## What This Example Shows

1. **Feature Queries**: Query geospatial features with spatial and attribute filters
2. **Form Definitions**: Retrieve mobile form definitions from server
3. **Form Submission**: Submit completed form data as new features
4. **Error Handling**: Proper gRPC error handling and status codes
5. **Mobile Optimizations**: Device capability-aware form rendering

## Key Concepts

### gRPC Channel Configuration

```csharp
var channel = GrpcChannel.ForAddress("https://api.example.com", new GrpcChannelOptions
{
    MaxReceiveMessageSize = 16 * 1024 * 1024, // 16MB for large responses
    Credentials = ChannelCredentials.Create(new SslCredentials(), credentials)
});
```

### Feature Queries

```csharp
var request = new QueryFeaturesRequest
{
    ServiceId = "parks",
    LayerId = 0,
    Where = "AREA > 1000",
    ReturnGeometry = true,
    OutSr = new SpatialReference { Wkid = 4326 }
};

var response = await client.QueryFeaturesAsync(request);
```

### Form Handling

```csharp
var formRequest = new GetFormDefinitionRequest
{
    FormId = "inspection-form",
    MobileCapabilities = new MobileCapabilities
    {
        HasCamera = true,
        HasGps = true,
        Platform = "dotnet"
    }
};

var form = await client.GetFormDefinitionAsync(formRequest);
```

## Project Structure

```
dotnet/
├── GeospatialExample.csproj  # Project file with gRPC dependencies
├── Program.cs                # Main example code
└── README.md                 # This file
```

## Dependencies

The example uses these NuGet packages:

- `Grpc.Net.Client` - gRPC client library for .NET
- `Google.Protobuf` - Protocol Buffers runtime
- `Grpc.Tools` - Protocol Buffers compiler integration

## Next Steps

- **Execution Workflows**: Use `ProcessService`, `PipelineService`, `RenderService`, `BuilderService`, or `DeploymentService` — they share a `Validate*` / `DryRun*` / `Execute*` / `Execute*Stream` / `Submit*Job` / `Get*Job` / `Get*JobResult` / `Cancel*Job` RPC surface. See the [Getting Started guide](../../docs/getting-started.md#step-10-process-pipeline-render-build-and-deployment-workflows).
- **Canonical Packaging**: Consume `MapPackage`, `AppPackage`, and `DeploymentSpec` from `packaging_types.proto` directly rather than wrapping them in bespoke shapes
- **Explore Streaming**: Modify the example to use `QueryFeaturesStream` for large datasets
- **Add Authentication**: Implement API key or OAuth authentication
- **Error Retry**: Add retry logic with exponential backoff; use `ErrorDetail.Retryability` for execution errors
- **Offline Support**: Cache responses for offline scenarios
- **Real-time Updates**: Use bidirectional streaming for live collaboration