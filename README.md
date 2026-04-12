# Geospatial gRPC Protocol Standard

> Open source gRPC protocol definitions for geospatial data access and mobile field data collection

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Buf Registry](https://img.shields.io/badge/buf-registry-blue)](https://buf.build/geospatial/standard)

## 🌍 Vision

The **Geospatial gRPC Standard** aims to democratize geospatial development by providing open, standardized gRPC protocols for:

- **Feature data access**: Query, stream, and edit geospatial features
- **Mobile data collection**: Modern alternative to OpenRosa XML forms
- **Real-time collaboration**: Multi-user editing and synchronization
- **Cross-platform compatibility**: Native mobile, web, and desktop apps

### Why gRPC for Geospatial?

- **Type Safety**: Strongly typed schemas prevent integration errors
- **Performance**: Binary serialization and HTTP/2 streaming
- **Mobile Optimized**: Efficient network usage and battery life
- **Language Agnostic**: Generate client libraries for 10+ languages
- **Streaming Support**: Real-time updates and large dataset pagination

## 📋 Protocol Overview

### Core Services

| Service | Purpose | Key Features |
|---------|---------|--------------|
| `FeatureService` | Geospatial CRUD operations | Query, stream, edit features |
| `FormService` | Mobile data collection | Dynamic forms, validation, collaboration |
| `ProcessService` | Geospatial process execution | Plan validation, dry-run, sync/streaming/async execution |
| `PipelineService` | Data publishing pipelines | Pipeline validation, dry-run, stage-by-stage execution |

### Key Message Types

- **Spatial Types**: Point, Polygon, MultiPolygon geometries with Z/M support
- **Feature**: Attributes + geometry with flexible typing
- **Form Controls**: Rich input types (location, media, validation)
- **Execution Types**: Plans, steps, jobs, artifacts, provenance, and structured errors
- **Mobile Optimizations**: Battery, network, and device-aware

## 🚀 Quick Start

### 1. Browse the Protocols

```bash
# View proto definitions
ls geospatial/v1/
# ├── common.proto            # Shared types
# ├── spatial_types.proto     # Geometry definitions
# ├── feature_service.proto   # Feature CRUD
# ├── form_service.proto      # Mobile forms
# ├── execution_types.proto   # Shared execution infrastructure
# ├── process_service.proto   # Process execution
# └── pipeline_service.proto  # Data publishing pipelines
```

### 2. Generate Client Libraries

```bash
# Install buf CLI
npm install -g @bufbuild/buf

# Generate for your language
buf generate

# Generated libraries are in gen/
ls gen/
# ├── csharp/     # C# / .NET
# ├── go/         # Go
# ├── java/       # Java
# ├── python/     # Python
# ├── typescript/ # TypeScript/JavaScript
# └── ...
```

### 3. Use in Your Project

#### .NET Example
```csharp
using GeospatialGrpc.V1;
using Grpc.Net.Client;

var channel = GrpcChannel.ForAddress("https://api.example.com");
var client = new FeatureService.FeatureServiceClient(channel);

var request = new QueryFeaturesRequest
{
    ServiceId = "parcels",
    LayerId = 0,
    Where = "AREA > 1000",
    ReturnGeometry = true
};

var response = await client.QueryFeaturesAsync(request);
foreach (var feature in response.Features)
{
    Console.WriteLine($"Feature {feature.Id}: {feature.Attributes}");
}
```

#### TypeScript Example
```typescript
import { FeatureService } from './gen/typescript/geospatial/v1/feature_service_pb';
import { createClient } from '@connectrpc/connect';

const client = createClient(FeatureService, {
  baseUrl: 'https://api.example.com'
});

const response = await client.queryFeatures({
  serviceId: 'parcels',
  layerId: 0,
  where: 'AREA > 1000',
  returnGeometry: true
});

response.features.forEach(feature => {
  console.log(`Feature ${feature.id}:`, feature.attributes);
});
```

#### Python Example
```python
import grpc
from geospatial.v1 import feature_service_pb2
from geospatial.v1 import feature_service_pb2_grpc

channel = grpc.insecure_channel('api.example.com:443')
client = feature_service_pb2_grpc.FeatureServiceStub(channel)

request = feature_service_pb2.QueryFeaturesRequest(
    service_id='parcels',
    layer_id=0,
    where='AREA > 1000',
    return_geometry=True
)

response = client.QueryFeatures(request)
for feature in response.features:
    print(f'Feature {feature.id}: {feature.attributes}')
```

## 📚 Documentation

- **[Protocol Specification](docs/specification.md)** - Detailed protocol documentation
- **[Getting Started Guide](docs/getting-started.md)** - Developer quick start
- **[Versioning Policy](VERSIONING.md)** - Compatibility guarantees and change governance
- **[Examples](examples/)** - Code samples for multiple languages

## 🏗️ Repository Structure

```
geospatial-grpc/
├── geospatial/v1/              # Protocol definitions
│   ├── common.proto            # Shared types and enums
│   ├── spatial_types.proto     # Geometry types
│   ├── feature_service.proto   # Feature CRUD operations
│   ├── form_service.proto      # Mobile data collection
│   ├── execution_types.proto   # Shared execution infrastructure
│   ├── process_service.proto   # Geospatial process execution
│   └── pipeline_service.proto  # Data publishing pipelines
├── docs/                       # Protocol documentation
├── examples/                   # Language-specific examples
├── gen/                        # Generated client libraries
├── buf.yaml                    # Buf configuration
├── buf.gen.yaml                # Code generation config
├── CONTRIBUTING.md             # Contribution guidelines
├── VERSIONING.md               # Versioning and compatibility policy
└── README.md
```

## 🛠️ Building and Contributing

### Prerequisites
- [Buf CLI](https://buf.build/docs/installation)
- Protocol Buffers knowledge
- Git

### Development Workflow

```bash
# Clone the repository
git clone https://github.com/mikemcdougall/geospatial-grpc.git
cd geospatial-grpc

# Validate protocols
buf lint
buf breaking --against '.git#branch=main'

# Generate client libraries
buf generate

# Run examples
cd examples/typescript && npm install && npm start
```

### Adding New Features

1. **Modify proto files** in `geospatial/v1/`
2. **Validate changes** with `buf lint` and `buf breaking`
3. **Update documentation** in `docs/`
4. **Add examples** in appropriate language directories
5. **Submit PR** with clear description of changes

## 🎯 Use Cases

### Enterprise GIS
- **Asset Management**: Track infrastructure, utilities, facilities
- **Fleet Operations**: Vehicle tracking and route optimization
- **Emergency Response**: Real-time incident mapping and coordination

### Mobile Field Collection
- **Environmental Monitoring**: Water quality, air quality, wildlife surveys
- **Construction Management**: Progress tracking, defect reporting
- **Public Works**: Road maintenance, park inspections, permit processing

### Smart Cities
- **Urban Planning**: Development tracking, zoning management
- **Transportation**: Traffic monitoring, public transit optimization
- **Citizen Services**: 311 reporting, service request management

### Research & Science
- **Climate Monitoring**: Weather stations, environmental sensors
- **Archaeology**: Site documentation, artifact tracking
- **Agriculture**: Precision farming, crop monitoring, yield analysis

## 🌐 Ecosystem

### Compatible Servers
- **[Honua Server](https://github.com/honua-io/honua-server)** - Reference implementation (ELv2)
- **Your Server Here** - Add your implementation!

### Client Libraries
- **[Honua .NET SDK](https://github.com/honua-io/honua-sdk-dotnet)** - .NET MAUI mobile SDK
- **[Honua JS SDK](https://github.com/honua-io/honua-sdk-js)** - Web and React Native SDK
- **Community Libraries** - Coming soon!

## 🤝 Contributing

We welcome contributions from the geospatial community! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Code of Conduct
This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

### License
This project is licensed under the [Apache License 2.0](LICENSE) - see the LICENSE file for details.

## 📞 Community

- **GitHub Discussions**: Ask questions, share ideas
- **Issues**: Report bugs, request features
- **Email**: [geospatial-grpc@honua.io](mailto:geospatial-grpc@honua.io)

---

**Democratizing geospatial development, one protocol at a time.** 🗺️

*Built with ❤️ by the [Honua](https://honua.io) team and the open source community.*
