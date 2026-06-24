#!/usr/bin/env python3
"""
Geospatial gRPC Python Example

This example demonstrates using the Geospatial gRPC protocols from Python.
It shows feature queries, form handling, and proper error handling.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

import grpc
from grpc import aio

# Import generated protobuf modules
# These would be generated from the .proto files
from geospatial.v1 import feature_service_pb2
from geospatial.v1 import feature_service_pb2_grpc
from geospatial.v1 import form_service_pb2
from geospatial.v1 import form_service_pb2_grpc
from geospatial.v1 import common_pb2
from geospatial.v1 import spatial_types_pb2

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GeospatialGrpcExample:
    """Example client for Geospatial gRPC services."""

    def __init__(self, server_url: str = "demo.geospatial-grpc.org:443"):
        self.server_url = server_url
        self.channel: Optional[aio.Channel] = None

    async def __aenter__(self):
        """Async context manager entry."""
        # Create secure gRPC channel
        credentials = grpc.ssl_channel_credentials()
        self.channel = aio.secure_channel(self.server_url, credentials)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.channel:
            await self.channel.close()

    async def run_feature_service_example(self):
        """Demonstrate FeatureService usage."""
        print("📍 Feature Service Example")
        print("-" * 26)

        if not self.channel:
            raise RuntimeError("Channel not initialized")

        stub = feature_service_pb2_grpc.FeatureServiceStub(self.channel)

        try:
            # Query parks in San Francisco with area > 1000 sq ft
            request = feature_service_pb2.QueryFeaturesRequest(
                service_id="sf-parks",
                layer_id=0,
                where="AREA > 1000",
                return_geometry=True,
                out_sr=common_pb2.SpatialReference(wkid=4326),  # WGS84
                result_record_count_long=10
            )

            response = await stub.QueryFeatures(request)

            print(f"Found {len(response.features)} parks:")
            for feature in response.features:
                # Get park name from attributes
                name_attr = feature.attributes.get("NAME")
                name = name_attr.string_value if name_attr else "Unknown"

                print(f"  • {name} (ID: {feature.id})")

                # Display location if point geometry
                if feature.geometry.HasField("point"):
                    point = feature.geometry.point
                    print(f"    Location: {point.x:.6f}, {point.y:.6f}")

        except grpc.RpcError as e:
            print(f"❌ Error: {e.code()} - {e.details()}")

        print()

    async def run_form_service_example(self):
        """Demonstrate FormService usage."""
        print("📋 Form Service Example")
        print("-" * 22)

        if not self.channel:
            raise RuntimeError("Channel not initialized")

        stub = form_service_pb2_grpc.FormServiceStub(self.channel)

        try:
            # Get park inspection form definition
            form_request = form_service_pb2.GetFormDefinitionRequest(
                form_id="park-inspection",
                service_id="sf-parks",
                layer_id=0,
                mobile_capabilities=form_service_pb2.MobileCapabilities(
                    has_camera=True,
                    has_gps=True,
                    platform="python",
                    device_type="desktop",
                    network_type=form_service_pb2.NetworkType.NETWORK_TYPE_WIFI,
                    battery_level=form_service_pb2.BatteryLevel.BATTERY_LEVEL_HIGH
                )
            )

            form_response = await stub.GetFormDefinition(form_request)
            form = form_response.form

            print(f"Form: {form.title}")
            print(f"Description: {form.description}")
            print(f"Version: {form.version}")
            print(f"Controls ({len(form.controls)}):")

            # Sort controls by display order
            sorted_controls = sorted(form.controls, key=lambda c: c.display_order)

            for control in sorted_controls:
                control_type = self._get_control_type_name(control)
                required = "*" if control.required else " "

                print(f"  {required} {control.label} ({control_type})")

                if control.hint:
                    print(f"      Hint: {control.hint}")

            # Demonstrate form submission
            await self._demonstrate_form_submission(stub, form)

        except grpc.RpcError as e:
            print(f"❌ Error: {e.code()} - {e.details()}")

        print()

    async def _demonstrate_form_submission(self, stub, form):
        """Demonstrate submitting form data."""
        print("\n📤 Submitting sample form data...")

        # Create form instance with sample data
        instance_id = str(uuid.uuid4())
        now_ms = int(datetime.utcnow().timestamp() * 1000)

        instance = form_service_pb2.FormInstance(
            instance_id=instance_id,
            form_id=form.form_id,
            created_by="demo-user",
            status=form_service_pb2.InstanceStatus.INSTANCE_STATUS_COMPLETE,
            created_at=now_ms,
            modified_at=now_ms
        )

        # Add sample field values based on control types
        for control in form.controls:
            value = self._create_sample_value(control)
            instance.field_values[control.control_id].CopyFrom(value)

        # Create submission request
        submission = form_service_pb2.SubmitFormDataRequest(
            form_id=form.form_id,
            form_version=form.version,
            instance=instance,
            metadata=form_service_pb2.SubmissionMetadata(
                device_id="python-example",
                platform="python-example",
                app_version="1.0.0",
                latitude=37.7749,  # San Francisco
                longitude=-122.4194,
                submission_time=now_ms
            )
        )

        try:
            submit_response = await stub.SubmitFormData(submission)

            if submit_response.result.success:
                print("✅ Form submitted successfully!")
                print(f"   Created feature ID: {submit_response.created_feature_id}")
                timestamp = datetime.fromtimestamp(submit_response.result.server_timestamp / 1000)
                print(f"   Server timestamp: {timestamp}")
            else:
                print(f"❌ Form submission failed: {submit_response.result.message}")
                for issue in submit_response.validation_issues:
                    print(f"   • {issue.field_id}: {issue.message}")

        except grpc.RpcError as e:
            print(f"❌ Error submitting form: {e.code()} - {e.details()}")

    def _get_control_type_name(self, control) -> str:
        """Get human-readable control type name."""
        if control.HasField("text_input"):
            return "Text Input"
        elif control.HasField("numeric_input"):
            return "Numeric Input"
        elif control.HasField("select_control"):
            return "Select"
        elif control.HasField("datetime_control"):
            return "Date/Time"
        elif control.HasField("location_control"):
            return "Location"
        elif control.HasField("media_control"):
            return "Media"
        elif control.HasField("boolean_control"):
            return "Boolean"
        else:
            return "Other"

    def _create_sample_value(self, control) -> common_pb2.AttributeValue:
        """Create sample attribute value based on control type."""
        if control.HasField("text_input"):
            return common_pb2.AttributeValue(string_value="Sample text value")
        elif control.HasField("numeric_input"):
            return common_pb2.AttributeValue(int32_value=42)
        elif control.HasField("boolean_control"):
            return common_pb2.AttributeValue(bool_value=True)
        elif control.HasField("datetime_control"):
            return common_pb2.AttributeValue(
                datetime_value=int(datetime.utcnow().timestamp() * 1000)
            )
        elif control.HasField("location_control"):
            return common_pb2.AttributeValue(string_value="POINT(-122.4194 37.7749)")
        else:
            return common_pb2.AttributeValue(string_value="Default value")


async def main():
    """Main function."""
    print("🌍 Geospatial gRPC Python Example")
    print("=" * 34)
    print()

    # Use async context manager for proper cleanup
    async with GeospatialGrpcExample() as example:
        await example.run_feature_service_example()
        await example.run_form_service_example()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())