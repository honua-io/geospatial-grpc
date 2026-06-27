using Geospatial.V1;
using Grpc.Core;
using Grpc.Net.Client;

namespace GeospatialExample;

class Program
{
    static async Task Main(string[] args)
    {
        // Configure gRPC channel
        using var channel = GrpcChannel.ForAddress("https://demo.geospatial-grpc.org", new GrpcChannelOptions
        {
            MaxReceiveMessageSize = 16 * 1024 * 1024 // 16MB for large responses
        });

        Console.WriteLine("🌍 Geospatial gRPC Example");
        Console.WriteLine("========================\n");

        await RunFeatureServiceExample(channel);
        await RunFormServiceExample(channel);
    }

    static async Task RunFeatureServiceExample(GrpcChannel channel)
    {
        Console.WriteLine("📍 Feature Service Example");
        Console.WriteLine("--------------------------");

        var client = new FeatureService.FeatureServiceClient(channel);

        try
        {
            // Query parks in San Francisco with area > 1000 sq ft
            var request = new QueryFeaturesRequest
            {
                ServiceId = "sf-parks",
                LayerId = 0,
                Where = "AREA > 1000",
                ReturnGeometry = true,
                OutSr = new SpatialReference { Wkid = 4326 }, // WGS84
                ResultRecordCountLong = 10
            };

            var response = await client.QueryFeaturesAsync(request);

            Console.WriteLine($"Found {response.Features.Count} parks:");
            foreach (var feature in response.Features)
            {
                var nameAttr = feature.Attributes.GetValueOrDefault("NAME");
                var name = nameAttr?.StringValue ?? "Unknown";

                Console.WriteLine($"  • {name} (ID: {feature.Id})");

                if (feature.Geometry?.Point != null)
                {
                    var point = feature.Geometry.Point;
                    Console.WriteLine($"    Location: {point.X:F6}, {point.Y:F6}");
                }
            }
        }
        catch (RpcException ex)
        {
            Console.WriteLine($"❌ Error: {ex.Status.StatusCode} - {ex.Status.Detail}");
        }

        Console.WriteLine();
    }

    static async Task RunFormServiceExample(GrpcChannel channel)
    {
        Console.WriteLine("📋 Form Service Example");
        Console.WriteLine("----------------------");

        var client = new FormService.FormServiceClient(channel);

        try
        {
            // Get park inspection form definition
            var formRequest = new GetFormDefinitionRequest
            {
                FormId = "park-inspection",
                ServiceId = "sf-parks",
                LayerId = 0,
                MobileCapabilities = new MobileCapabilities
                {
                    HasCamera = true,
                    HasGps = true,
                    Platform = "dotnet",
                    DeviceType = "desktop",
                    NetworkType = NetworkType.Wifi,
                    BatteryLevel = BatteryLevel.High
                }
            };

            var formResponse = await client.GetFormDefinitionAsync(formRequest);
            var form = formResponse.Form;

            Console.WriteLine($"Form: {form.Title}");
            Console.WriteLine($"Description: {form.Description}");
            Console.WriteLine($"Version: {form.Version}");
            Console.WriteLine($"Controls ({form.Controls.Count}):");

            foreach (var control in form.Controls.OrderBy(c => c.DisplayOrder))
            {
                var controlType = control.ControlTypeCase switch
                {
                    FormControl.ControlTypeOneofCase.TextInput => "Text Input",
                    FormControl.ControlTypeOneofCase.NumericInput => "Numeric Input",
                    FormControl.ControlTypeOneofCase.SelectControl => "Select",
                    FormControl.ControlTypeOneofCase.DatetimeControl => "Date/Time",
                    FormControl.ControlTypeOneofCase.LocationControl => "Location",
                    FormControl.ControlTypeOneofCase.MediaControl => "Media",
                    FormControl.ControlTypeOneofCase.BooleanControl => "Boolean",
                    _ => "Other"
                };

                var required = control.Required ? "*" : " ";
                Console.WriteLine($"  {required} {control.Label} ({controlType})");

                if (!string.IsNullOrEmpty(control.Hint))
                {
                    Console.WriteLine($"      Hint: {control.Hint}");
                }
            }

            // Demonstrate form submission
            await DemonstrateFormSubmission(client, form);
        }
        catch (RpcException ex)
        {
            Console.WriteLine($"❌ Error: {ex.Status.StatusCode} - {ex.Status.Detail}");
        }

        Console.WriteLine();
    }

    static async Task DemonstrateFormSubmission(FormService.FormServiceClient client, FormDefinition form)
    {
        Console.WriteLine("\n📤 Submitting sample form data...");

        var submission = new SubmitFormDataRequest
        {
            FormId = form.FormId,
            FormVersion = form.Version,
            Instance = new FormInstance
            {
                InstanceId = Guid.NewGuid().ToString(),
                FormId = form.FormId,
                CreatedBy = "demo-user",
                Status = InstanceStatus.Complete,
                CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                ModifiedAt = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            },
            Metadata = new SubmissionMetadata
            {
                DeviceId = Environment.MachineName,
                Platform = "dotnet-example",
                AppVersion = "1.0.0",
                Latitude = 37.7749, // San Francisco
                Longitude = -122.4194,
                SubmissionTime = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            }
        };

        // Add sample field values based on form controls
        foreach (var control in form.Controls)
        {
            var value = control.ControlTypeCase switch
            {
                FormControl.ControlTypeOneofCase.TextInput => new AttributeValue { StringValue = "Sample text value" },
                FormControl.ControlTypeOneofCase.NumericInput => new AttributeValue { Int32Value = 42 },
                FormControl.ControlTypeOneofCase.BooleanControl => new AttributeValue { BoolValue = true },
                FormControl.ControlTypeOneofCase.DatetimeControl => new AttributeValue { DatetimeValue = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() },
                FormControl.ControlTypeOneofCase.LocationControl => new AttributeValue { StringValue = "POINT(-122.4194 37.7749)" },
                _ => new AttributeValue { StringValue = "Default value" }
            };

            submission.Instance.FieldValues[control.ControlId] = value;
        }

        try
        {
            var submitResponse = await client.SubmitFormDataAsync(submission);

            if (submitResponse.Result.Success)
            {
                Console.WriteLine($"✅ Form submitted successfully!");
                Console.WriteLine($"   Created feature ID: {submitResponse.CreatedFeatureId}");
                Console.WriteLine($"   Server timestamp: {DateTimeOffset.FromUnixTimeMilliseconds(submitResponse.Result.ServerTimestamp)}");
            }
            else
            {
                Console.WriteLine($"❌ Form submission failed: {submitResponse.Result.Message}");
                foreach (var issue in submitResponse.ValidationIssues)
                {
                    Console.WriteLine($"   • {issue.FieldId}: {issue.Message}");
                }
            }
        }
        catch (RpcException ex)
        {
            Console.WriteLine($"❌ Error submitting form: {ex.Status.StatusCode} - {ex.Status.Detail}");
        }
    }
}