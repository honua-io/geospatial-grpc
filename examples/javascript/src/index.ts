// protoc-gen-es emits one *_pb module per .proto and does not re-export symbols
// across files, so each type must be imported from the module generated for the
// .proto that defines it: services and their request types live with their
// service, shared messages (SpatialReference, AttributeValue) live in common.
import { create } from '@bufbuild/protobuf';
import { FeatureService } from './gen/geospatial/v1/feature_service_pb.js';
import {
  FormService,
  SubmitFormDataRequestSchema,
  NetworkType,
  BatteryLevel,
  InstanceStatus,
} from './gen/geospatial/v1/form_service_pb.js';
import { AttributeValueSchema } from './gen/geospatial/v1/common_pb.js';
import type { FormDefinition } from './gen/geospatial/v1/form_service_pb.js';
import { createClient, type Client } from '@connectrpc/connect';
import { createGrpcTransport } from '@connectrpc/connect-node';

// Configure transport
const transport = createGrpcTransport({
  baseUrl: 'https://demo.geospatial-grpc.org',
});

async function main() {
  console.log('🌍 Geospatial gRPC JavaScript Example');
  console.log('====================================\n');

  await runFeatureServiceExample();
  await runFormServiceExample();
}

async function runFeatureServiceExample() {
  console.log('📍 Feature Service Example');
  console.log('--------------------------');

  const client = createClient(FeatureService, transport);

  try {
    // Query parks in San Francisco with area > 1000 sq ft. Connect's client
    // methods accept a plain message-init object; nested messages (outSr) and
    // int64 fields (bigint) are written inline.
    const response = await client.queryFeatures({
      serviceId: 'sf-parks',
      layerId: 0,
      where: 'AREA > 1000',
      returnGeometry: true,
      outSr: { wkid: 4326 }, // WGS84
      resultRecordCountLong: 10n,
    });

    console.log(`Found ${response.features.length} parks:`);
    for (const feature of response.features) {
      const nameAttr = feature.attributes['NAME'];
      const name =
        nameAttr?.value.case === 'stringValue' ? nameAttr.value.value : 'Unknown';

      console.log(`  • ${name} (ID: ${feature.id})`);

      // Geometry is a oneof; the populated shape is reported via `shape.case`.
      if (feature.geometry?.shape.case === 'point') {
        const { x, y } = feature.geometry.shape.value;
        console.log(`    Location: ${x.toFixed(6)}, ${y.toFixed(6)}`);
      }
    }
  } catch (error) {
    console.error('❌ Error querying features:', error);
  }

  console.log();
}

async function runFormServiceExample() {
  console.log('📋 Form Service Example');
  console.log('----------------------');

  const client = createClient(FormService, transport);

  try {
    // Get park inspection form definition
    const formResponse = await client.getFormDefinition({
      formId: 'park-inspection',
      serviceId: 'sf-parks',
      layerId: 0,
      mobileCapabilities: {
        hasCamera: true,
        hasGps: true,
        platform: 'javascript',
        deviceType: 'desktop',
        networkType: NetworkType.WIFI,
        batteryLevel: BatteryLevel.HIGH,
      },
    });

    const form = formResponse.form;
    if (!form) {
      console.log('No form definition returned.');
      return;
    }

    console.log(`Form: ${form.title}`);
    console.log(`Description: ${form.description}`);
    console.log(`Version: ${form.version}`);
    console.log(`Controls (${form.controls.length}):`);

    const sortedControls = [...form.controls].sort((a, b) => a.displayOrder - b.displayOrder);

    for (const control of sortedControls) {
      const controlType = getControlTypeName(control.controlType.case);
      const required = control.required ? '*' : ' ';

      console.log(`  ${required} ${control.label} (${controlType})`);

      if (control.hint) {
        console.log(`      Hint: ${control.hint}`);
      }
    }

    // Demonstrate form submission
    await demonstrateFormSubmission(client, form);
  } catch (error) {
    console.error('❌ Error with form service:', error);
  }

  console.log();
}

async function demonstrateFormSubmission(
  client: Client<typeof FormService>,
  form: FormDefinition,
) {
  console.log('\n📤 Submitting sample form data...');

  const instanceId = crypto.randomUUID();
  const now = BigInt(Date.now()); // int64 timestamp fields are bigint

  // Build the request as a typed message so field values can be populated from
  // the form's controls below.
  const submission = create(SubmitFormDataRequestSchema, {
    formId: form.formId,
    formVersion: form.version,
    instance: {
      instanceId,
      formId: form.formId,
      createdBy: 'demo-user',
      status: InstanceStatus.COMPLETE,
      createdAt: now,
      modifiedAt: now,
    },
    metadata: {
      deviceId: 'javascript-example',
      platform: 'javascript-example',
      appVersion: '1.0.0',
      latitude: 37.7749, // San Francisco
      longitude: -122.4194,
      submissionTime: now,
    },
  });

  // Add sample field values based on form controls. AttributeValue is a oneof,
  // so the value is set via { case, value }.
  for (const control of form.controls) {
    switch (control.controlType.case) {
      case 'numericInput':
        submission.instance!.fieldValues[control.controlId] = create(AttributeValueSchema, {
          value: { case: 'int32Value', value: 42 },
        });
        break;
      case 'booleanControl':
        submission.instance!.fieldValues[control.controlId] = create(AttributeValueSchema, {
          value: { case: 'boolValue', value: true },
        });
        break;
      case 'datetimeControl':
        submission.instance!.fieldValues[control.controlId] = create(AttributeValueSchema, {
          value: { case: 'datetimeValue', value: now },
        });
        break;
      case 'locationControl':
        submission.instance!.fieldValues[control.controlId] = create(AttributeValueSchema, {
          value: { case: 'stringValue', value: 'POINT(-122.4194 37.7749)' },
        });
        break;
      case 'textInput':
        submission.instance!.fieldValues[control.controlId] = create(AttributeValueSchema, {
          value: { case: 'stringValue', value: 'Sample text value' },
        });
        break;
      default:
        submission.instance!.fieldValues[control.controlId] = create(AttributeValueSchema, {
          value: { case: 'stringValue', value: 'Default value' },
        });
    }
  }

  try {
    const submitResponse = await client.submitFormData(submission);

    if (submitResponse.result?.success) {
      console.log('✅ Form submitted successfully!');
      console.log(`   Created feature ID: ${submitResponse.createdFeatureId}`);
      console.log(
        `   Server timestamp: ${new Date(Number(submitResponse.result.serverTimestamp))}`,
      );
    } else {
      console.log(`❌ Form submission failed: ${submitResponse.result?.message}`);
      for (const issue of submitResponse.validationIssues) {
        console.log(`   • ${issue.fieldId}: ${issue.message}`);
      }
    }
  } catch (error) {
    console.error('❌ Error submitting form:', error);
  }
}

function getControlTypeName(controlType: string | undefined): string {
  switch (controlType) {
    case 'textInput': return 'Text Input';
    case 'numericInput': return 'Numeric Input';
    case 'selectControl': return 'Select';
    case 'datetimeControl': return 'Date/Time';
    case 'locationControl': return 'Location';
    case 'mediaControl': return 'Media';
    case 'booleanControl': return 'Boolean';
    default: return 'Other';
  }
}

// Run the example
main().catch(console.error);
