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
    string fixture,
    Func<TRequest, Metadata, AsyncUnaryCall<TResponse>> invoke)
    where TRequest : IMessage<TRequest>, new()
    where TResponse : IMessage<TResponse>
{
    try
    {
        var json = await File.ReadAllTextAsync(Path.Combine(fixtureDirectory, fixture));
        var request = JsonParser.Default.Parse<TRequest>(json);
        var response = await invoke(request, headers).ResponseAsync;
        _ = JsonFormatter.Default.Format(response);
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

var feature = new FeatureService.FeatureServiceClient(channel);
var form = new FormService.FormServiceClient(channel);
var process = new ProcessService.ProcessServiceClient(channel);
var workspace = new WorkspaceService.WorkspaceServiceClient(channel);

await Execute<QueryFeaturesRequest, QueryFeaturesResponse>(
    "FeatureService/QueryFeatures", "feature_query_request.json", (request, metadata) => feature.QueryFeaturesAsync(request, metadata));
await Execute<ApplyEditsRequest, ApplyEditsResponse>(
    "FeatureService/ApplyEdits", "feature_apply_edits_request.json", (request, metadata) => feature.ApplyEditsAsync(request, metadata));
await Execute<GetFormDefinitionRequest, GetFormDefinitionResponse>(
    "FormService/GetFormDefinition", "form_get_definition_request.json", (request, metadata) => form.GetFormDefinitionAsync(request, metadata));
await Execute<SubmitFormDataRequest, SubmitFormDataResponse>(
    "FormService/SubmitFormData", "form_submit_request.json", (request, metadata) => form.SubmitFormDataAsync(request, metadata));
await Execute<ExecutePlanRequest, ExecutePlanResponse>(
    "ProcessService/ExecutePlan", "process_execute_plan_request.json", (request, metadata) => process.ExecutePlanAsync(request, metadata));
await Execute<CreateWorkspaceRequest, CreateWorkspaceResponse>(
    "WorkspaceService/CreateWorkspace", "workspace_create_request.json", (request, metadata) => workspace.CreateWorkspaceAsync(request, metadata));

Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);
await File.WriteAllTextAsync(reportPath, JsonSerializer.Serialize(new
{
    runner_lane = "grpc-dotnet",
    package = "Geospatial.Grpc",
    package_version = "0.2.0-alpha.1",
    package_source = "https://api.nuget.org/v3/index.json",
    operations = outcomes,
}, new JsonSerializerOptions { WriteIndented = true }));
return 0;
