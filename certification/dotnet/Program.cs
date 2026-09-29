using System.Text.Json;
using System.Text.Json.Nodes;
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
var failures = 0;
var startedAt = DateTimeOffset.UtcNow;
var (serverAssigned, optionalServerAssigned) = LoadServerAssignedFields(
    Path.Combine(AppContext.BaseDirectory, "server-assigned-fields.v1.json"));

// Call once and return the first divergence from the fixture, or null.
async Task<string?> Compare<TRequest, TResponse>(
    string operation,
    string requestFixture,
    string responseFixture,
    Func<TRequest, Metadata, AsyncUnaryCall<TResponse>> invoke)
    where TRequest : IMessage<TRequest>, new()
    where TResponse : IMessage<TResponse>, new()
{
    var requestJson = await File.ReadAllTextAsync(Path.Combine(fixtureDirectory, requestFixture));
    var request = JsonParser.Default.Parse<TRequest>(requestJson);
    var response = await invoke(request, headers).ResponseAsync;
    var expectedJson = await File.ReadAllTextAsync(Path.Combine(fixtureDirectory, responseFixture));
    var expected = JsonParser.Default.Parse<TResponse>(expectedJson);
    var patterns = serverAssigned.TryGetValue(operation, out var listed) ? listed : [];
    var optional = optionalServerAssigned.TryGetValue(operation, out var listedOptional) ? listedOptional : [];
    using var expectedDocument = JsonDocument.Parse(
        MaskServerAssigned(JsonFormatter.Default.Format(expected), patterns, optional));
    using var actualDocument = JsonDocument.Parse(
        MaskServerAssigned(JsonFormatter.Default.Format(response), patterns, optional));
    return FirstDivergence(expectedDocument.RootElement, actualDocument.RootElement, "$");
}

async Task Execute<TRequest, TResponse>(
    string operation,
    string requestFixture,
    string responseFixture,
    Func<TRequest, Metadata, AsyncUnaryCall<TResponse>> invoke,
    (string Request, string Status, Func<Task<string?>> Verify)? negative = null)
    where TRequest : IMessage<TRequest>, new()
    where TResponse : IMessage<TResponse>, new()
{
    try
    {
        if (negative is { } negativeCase)
        {
            var negativeRequest = JsonParser.Default.Parse<TRequest>(
                await File.ReadAllTextAsync(Path.Combine(fixtureDirectory, negativeCase.Request)));
            using var expectedStatus = JsonDocument.Parse(
                await File.ReadAllTextAsync(Path.Combine(fixtureDirectory, negativeCase.Status)));
            var expectedCode = expectedStatus.RootElement.GetProperty("code").GetInt32();
            var expectedName = expectedStatus.RootElement.GetProperty("name").GetString();
            RpcException? rejection = null;
            try
            {
                await invoke(negativeRequest, headers).ResponseAsync;
            }
            catch (RpcException exception)
            {
                rejection = exception;
            }
            if (rejection is null)
            {
                failures++;
                outcomes[operation] = new
                {
                    result = "fail",
                    reason = $"Negative case {negativeCase.Request} succeeded; expected the whole batch to fail with status {expectedName}",
                };
                return;
            }
            if ((int)rejection.StatusCode != expectedCode)
            {
                failures++;
                outcomes[operation] = new
                {
                    result = "fail",
                    reason = $"Negative case {negativeCase.Request} expected status {expectedName}, got {rejection.StatusCode}: {rejection.Status.Detail}",
                };
                return;
            }
            // The rejected batch must have applied nothing: read its targets back.
            var verifyDivergence = await negativeCase.Verify();
            if (verifyDivergence is not null)
            {
                failures++;
                outcomes[operation] = new
                {
                    result = "fail",
                    reason = $"Negative case {negativeCase.Request} was rejected but changed state: read-back mismatch at {verifyDivergence}",
                };
                return;
            }
        }
        var divergence = await Compare(operation, requestFixture, responseFixture, invoke);
        if (divergence is not null)
        {
            failures++;
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
        failures++;
        outcomes[operation] = new
        {
            result = "fail",
            reason = $"Canonical published client executed and failed: {exception.GetType().Name}: {exception.Message}",
        };
    }
}

static (Dictionary<string, string[]> Required, Dictionary<string, string[]> Optional) LoadServerAssignedFields(string file)
{
    using var document = JsonDocument.Parse(File.ReadAllText(file));
    if (document.RootElement.GetProperty("schema").GetString() != "honua.grpc-certification-server-assigned-fields/v1")
    {
        throw new InvalidOperationException($"unsupported server-assigned field list: {file}");
    }
    static Dictionary<string, string[]> Read(JsonElement operations) => operations.EnumerateObject().ToDictionary(
        operation => operation.Name,
        operation => operation.Value.EnumerateArray().Select(path => path.GetString()!).ToArray());
    var optional = document.RootElement.TryGetProperty("optional_operations", out var listed)
        ? Read(listed)
        : new Dictionary<string, string[]>();
    return (Read(document.RootElement.GetProperty("operations")), optional);
}

static List<string> PathTokens(string pattern)
{
    if (!pattern.StartsWith("$.", StringComparison.Ordinal))
    {
        throw new InvalidOperationException($"server-assigned path must start with '$.': {pattern}");
    }
    var tokens = new List<string>();
    foreach (var part in pattern[2..].Split('.'))
    {
        if (part.EndsWith("[*]", StringComparison.Ordinal))
        {
            tokens.Add(part[..^3]);
            tokens.Add("[*]");
        }
        else
        {
            tokens.Add(part);
        }
    }
    if (tokens.Count == 0 || tokens.Any(string.IsNullOrEmpty))
    {
        throw new InvalidOperationException($"malformed server-assigned path: {pattern}");
    }
    return tokens;
}

// Replace each present server-assigned value with a placeholder. Absent values
// stay absent, so the comparison still requires a required path on both sides.
// Optional paths (values that may validly be the proto3 default, which the JSON
// mapping omits) are removed instead.
static string MaskServerAssigned(string json, string[] patterns, string[] optional)
{
    var root = JsonNode.Parse(json)!;
    foreach (var pattern in patterns)
    {
        Visit(root, PathTokens(pattern), 0, remove: false);
    }
    foreach (var pattern in optional)
    {
        Visit(root, PathTokens(pattern), 0, remove: true);
    }
    return root.ToJsonString();

    static void Visit(JsonNode? node, List<string> tokens, int index, bool remove)
    {
        var head = tokens[index];
        var last = index == tokens.Count - 1;
        if (head == "[*]")
        {
            if (node is not JsonArray array)
            {
                return;
            }
            for (var item = 0; item < array.Count; item++)
            {
                if (!last)
                {
                    Visit(array[item], tokens, index + 1, remove);
                }
                else if (!remove)
                {
                    array[item] = JsonValue.Create("<server-assigned>");
                }
            }
            return;
        }
        if (node is not JsonObject obj || !obj.ContainsKey(head))
        {
            return;
        }
        if (!last)
        {
            Visit(obj[head], tokens, index + 1, remove);
        }
        else if (remove)
        {
            obj.Remove(head);
        }
        else
        {
            obj[head] = JsonValue.Create("<server-assigned>");
        }
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
    "FeatureService/ApplyEdits", "feature_apply_edits_request.json", "feature_apply_edits_response.json", (request, metadata) => feature.ApplyEditsAsync(request, metadata),
    ("feature_apply_edits_missing_target_request.json", "feature_apply_edits_missing_target_status.json",
        () => Compare<QueryFeaturesRequest, QueryFeaturesResponse>(
            "FeatureService/QueryFeatures",
            "feature_apply_edits_missing_target_verify_request.json",
            "feature_apply_edits_missing_target_verify_response.json",
            (request, metadata) => feature.QueryFeaturesAsync(request, metadata))));
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
    package_version = "1.0.0",
    package_source = "https://api.nuget.org/v3/index.json",
    started_at = startedAt,
    completed_at = DateTimeOffset.UtcNow,
    execution_identity = new
    {
        channel_target = target.GetLeftPart(UriPartial.Authority),
        server_image = Environment.GetEnvironmentVariable("SERVER_IMAGE"),
        server_source_sha = Environment.GetEnvironmentVariable("SERVER_SOURCE_SHA"),
        fixture_revision = Environment.GetEnvironmentVariable("FIXTURE_REVISION"),
    },
    operations = outcomes,
}, new JsonSerializerOptions { WriteIndented = true }));
return failures == 0 ? 0 : 1;
