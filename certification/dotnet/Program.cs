using System.Text.Json;
using Google.Protobuf;
using Grpc.Core;
using Grpc.Net.Client;
using Geospatial.V1;

if (args.Length != 3)
{
    Console.Error.WriteLine("usage: runner <absolute-channel-target> <fixture-directory> <report-path>");
    return 2;
}

var target = new Uri(args[0], UriKind.Absolute);
var fixtureDirectory = Path.GetFullPath(args[1]);
var reportPath = Path.GetFullPath(args[2]);
var apiKey = Environment.GetEnvironmentVariable("HONUA_PROTOCOL_API_KEY")
    ?? throw new InvalidOperationException("HONUA_PROTOCOL_API_KEY is required");
var headers = new Metadata { { "x-api-key", apiKey } };
using var channel = GrpcChannel.ForAddress(target);
var outcomes = new Dictionary<string, object>();

async Task Execute<TRequest, TResponse>(
    string operation,
    string requestFixture,
    string responseFixture,
    Func<TRequest, Metadata, AsyncUnaryCall<TResponse>> invoke)
    where TRequest : IMessage<TRequest>, new()
    where TResponse : IMessage<TResponse>, new()
{
    try
    {
        var requestJson = await File.ReadAllTextAsync(Path.Combine(fixtureDirectory, requestFixture));
        var request = JsonParser.Default.Parse<TRequest>(requestJson);
        var response = await invoke(request, headers).ResponseAsync;
        var expectedJson = await File.ReadAllTextAsync(Path.Combine(fixtureDirectory, responseFixture));
        var expected = JsonParser.Default.Parse<TResponse>(expectedJson);
        using var expectedDocument = JsonDocument.Parse(JsonFormatter.Default.Format(expected));
        using var actualDocument = JsonDocument.Parse(JsonFormatter.Default.Format(response));
        var divergence = FirstDivergence(expectedDocument.RootElement, actualDocument.RootElement, "$");
        if (divergence is not null)
        {
            outcomes[operation] = new
            {
                result = "fail",
                reason = $"Canonical response mismatch at {divergence}",
            };
            return;
        }
        outcomes[operation] = new { result = "pass" };
    }
    catch (Exception exception)
    {
        outcomes[operation] = new
        {
            result = "fail",
            reason = $"Canonical published client executed and failed: {exception.GetType().Name}: {exception.Message}",
        };
    }
}

static string? FirstDivergence(JsonElement expected, JsonElement actual, string path)
{
    if (expected.ValueKind != actual.ValueKind)
    {
        return path;
    }

    if (expected.ValueKind == JsonValueKind.Object)
    {
        var expectedProperties = expected.EnumerateObject().ToDictionary(property => property.Name, property => property.Value);
        var actualProperties = actual.EnumerateObject().ToDictionary(property => property.Name, property => property.Value);
        foreach (var name in expectedProperties.Keys.Union(actualProperties.Keys).OrderBy(name => name, StringComparer.Ordinal))
        {
            var childPath = $"{path}.{name}";
            if (!expectedProperties.TryGetValue(name, out var expectedValue)
                || !actualProperties.TryGetValue(name, out var actualValue))
            {
                return childPath;
            }
            var divergence = FirstDivergence(expectedValue, actualValue, childPath);
            if (divergence is not null)
            {
                return divergence;
            }
        }
        return null;
    }

    if (expected.ValueKind == JsonValueKind.Array)
    {
        var expectedItems = expected.EnumerateArray().ToArray();
        var actualItems = actual.EnumerateArray().ToArray();
        var sharedLength = Math.Min(expectedItems.Length, actualItems.Length);
        for (var index = 0; index < sharedLength; index++)
        {
            var divergence = FirstDivergence(expectedItems[index], actualItems[index], $"{path}[{index}]");
            if (divergence is not null)
            {
                return divergence;
            }
        }
        return expectedItems.Length == actualItems.Length ? null : $"{path}[{sharedLength}]";
    }

    return expected.GetRawText() == actual.GetRawText() ? null : path;
}

var feature = new FeatureService.FeatureServiceClient(channel);
var form = new FormService.FormServiceClient(channel);
var process = new ProcessService.ProcessServiceClient(channel);
var workspace = new WorkspaceService.WorkspaceServiceClient(channel);

await Execute<QueryFeaturesRequest, QueryFeaturesResponse>(
    "FeatureService/QueryFeatures", "feature_query_request.json", "feature_query_response.json", (request, metadata) => feature.QueryFeaturesAsync(request, metadata));
await Execute<ApplyEditsRequest, ApplyEditsResponse>(
    "FeatureService/ApplyEdits", "feature_apply_edits_request.json", "feature_apply_edits_response.json", (request, metadata) => feature.ApplyEditsAsync(request, metadata));
await Execute<GetFormDefinitionRequest, GetFormDefinitionResponse>(
    "FormService/GetFormDefinition", "form_get_definition_request.json", "form_get_definition_response.json", (request, metadata) => form.GetFormDefinitionAsync(request, metadata));
await Execute<SubmitFormDataRequest, SubmitFormDataResponse>(
    "FormService/SubmitFormData", "form_submit_request.json", "form_submit_response.json", (request, metadata) => form.SubmitFormDataAsync(request, metadata));
await Execute<ExecutePlanRequest, ExecutePlanResponse>(
    "ProcessService/ExecutePlan", "process_execute_plan_request.json", "process_execute_plan_response.json", (request, metadata) => process.ExecutePlanAsync(request, metadata));
await Execute<CreateWorkspaceRequest, CreateWorkspaceResponse>(
    "WorkspaceService/CreateWorkspace", "workspace_create_request.json", "workspace_create_response.json", (request, metadata) => workspace.CreateWorkspaceAsync(request, metadata));

Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);
await File.WriteAllTextAsync(reportPath, JsonSerializer.Serialize(new
{
    runner_lane = "grpc-dotnet",
    package = "Geospatial.Grpc",
    package_version = "0.2.0-alpha.1",
    package_source = "https://nuget.pkg.github.com/honua-io/index.json",
    operations = outcomes,
}, new JsonSerializerOptions { WriteIndented = true }));
return 0;
