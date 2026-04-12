# JavaScript/TypeScript Example

This example demonstrates using the Geospatial gRPC protocols from JavaScript and TypeScript.

## Prerequisites

- Node.js 18+ with npm or yarn
- TypeScript (for development)

## Setup and Running

```bash
# Install dependencies
npm install

# Generate TypeScript client from proto files
npm run generate

# Run in development mode (TypeScript)
npm run dev

# Or build and run (JavaScript)
npm run build
npm start
```

## What This Example Shows

1. **Feature Queries**: Query geospatial features with filters
2. **Form Handling**: Retrieve and submit mobile forms
3. **Type Safety**: Full TypeScript type safety with generated clients
4. **Error Handling**: Proper async/await error handling
5. **Modern JavaScript**: ES modules and latest language features

## Key Technologies

- **@connectrpc/connect**: Modern gRPC-Web client for browsers and Node.js
- **TypeScript**: Type-safe development experience
- **ES Modules**: Modern JavaScript module system
- **Protocol Buffers**: Binary serialization with type safety

## Generated Client Usage

### Feature Queries

```typescript
import { FeatureService } from './gen/geospatial/v1/feature_service_pb.js';
import { createClient } from '@connectrpc/connect';

const client = createClient(FeatureService, transport);

const response = await client.queryFeatures({
  serviceId: 'parks',
  layerId: 0,
  where: 'AREA > 1000',
  returnGeometry: true,
  outSr: { wkid: 4326 }
});
```

### Form Handling

```typescript
import { FormService } from './gen/geospatial/v1/form_service_pb.js';

const client = createClient(FormService, transport);

const form = await client.getFormDefinition({
  formId: 'inspection-form',
  mobileCapabilities: {
    hasCamera: true,
    hasGps: true,
    platform: 'javascript'
  }
});
```

## Project Structure

```
javascript/
├── src/
│   ├── index.ts              # Main example code
│   └── gen/                  # Generated TypeScript clients
├── package.json              # Dependencies and scripts
├── tsconfig.json             # TypeScript configuration
└── README.md                 # This file
```

## Browser Usage

This example can be adapted for browser use:

```typescript
// For browsers, use createGrpcWebTransport instead
import { createGrpcWebTransport } from '@connectrpc/connect-web';

const transport = createGrpcWebTransport({
  baseUrl: 'https://api.example.com'
});
```

## React Integration

Example React hook for feature queries:

```typescript
import { useEffect, useState } from 'react';
import { FeatureService } from '../gen/geospatial/v1/feature_service_pb.js';

export function useFeatureQuery(serviceId: string, layerId: number, where: string) {
  const [features, setFeatures] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const client = createClient(FeatureService, transport);

    client.queryFeatures({
      serviceId,
      layerId,
      where,
      returnGeometry: true
    }).then(response => {
      setFeatures(response.features);
      setLoading(false);
    });
  }, [serviceId, layerId, where]);

  return { features, loading };
}
```

## Next Steps

- **Process Execution**: Use `ProcessService` to validate, dry-run, and execute analysis plans — see the [Getting Started guide](../../docs/getting-started.md#step-10-process-execution-and-pipelines)
- **Data Publishing**: Use `PipelineService` to run data ingestion and publishing pipelines
- **Web Application**: Build a full mapping web app with Leaflet/Mapbox
- **React Native**: Adapt for mobile app development
- **Streaming**: Implement server-sent events for real-time updates
- **Offline Support**: Add IndexedDB caching for offline capabilities
- **Authentication**: Add JWT or API key authentication