using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Google.Protobuf;
using Google.Protobuf.Reflection;
using Grpc.Core;
using Grpc.Net.Client;
using Geospatial.V1;

// Execute the promoted Geospatial.Grpc package against a live target. Runs every
// scenario in certification/scenarios.v1.json through the installed generated
// descriptors and marshallers, compares each canonical response with the
// fixture, and writes a lane report for scripts/build_protocol_certification_fragment.py.

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
var pollTimeoutOverride = Environment.GetEnvironmentVariable("HONUA_CERTIFICATION_POLL_TIMEOUT_SECONDS");
var headers = new Metadata { { "x-api-key", apiKey } };
using var channel = GrpcChannel.ForAddress(target);
var invoker = channel.CreateCallInvoker();
var outcomes = new Dictionary<string, object>();
var captures = new Dictionary<string, string>(StringComparer.Ordinal);
var startedAt = DateTimeOffset.UtcNow;
var (serverAssigned, optionalServerAssigned) = LoadServerAssignedFields(
    Path.Combine(AppContext.BaseDirectory, "server-assigned-fields.v1.json"));
using var scenarioDocument = JsonDocument.Parse(
    await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, "scenarios.v1.json")));
if (scenarioDocument.RootElement.GetProperty("schema").GetString() != "honua.grpc-certification-scenarios/v1")
{
    throw new InvalidOperationException("unsupported scenario list");
}
var captureToken = new Regex(@"\{\{capture:([A-Za-z0-9_]+)\}\}", RegexOptions.CultureInvariant);

string ReadFixture(string name)
{
    var text = File.ReadAllText(Path.Combine(fixtureDirectory, name));
    return captureToken.Replace(text, match =>
        captures.TryGetValue(match.Groups[1].Value, out var value)
            ? value
            : throw new ScenarioFailure($"{name} needs capture '{match.Groups[1].Value}', which an earlier scenario did not provide"));
}

IMessage Parse(string name, MessageDescriptor descriptor) => JsonParser.Default.Parse(ReadFixture(name), descriptor);

JsonNode Canonical(IMessage message) => JsonNode.Parse(JsonFormatter.Default.Format(message))!;

JsonNode Masked(string operation, JsonNode document)
{
    var patterns = serverAssigned.TryGetValue(operation, out var listed) ? listed : [];
    var optional = optionalServerAssigned.TryGetValue(operation, out var listedOptional) ? listedOptional : [];
    return MaskServerAssigned(document, patterns, optional);
}

string? CompareUnary(string operation, string responseFixture, JsonNode response)
{
    var expected = Canonical(Parse(responseFixture, Rpc.For(operation).Descriptor.OutputType));
    return Divergence(Masked(operation, expected), Masked(operation, response.DeepClone()));
}

void Capture(JsonElement scenario, string property, JsonNode document)
{
    if (!scenario.TryGetProperty(property, out var spec))
    {
        return;
    }
    foreach (var item in spec.EnumerateObject())
    {
        var value = ReadPath(document, item.Value.GetString()!);
        if (value is not JsonValue scalar || !scalar.TryGetValue<string>(out var text) || text.Length == 0)
        {
            throw new ScenarioFailure($"response has no value at {item.Value.GetString()} to capture as '{item.Name}'");
        }
        captures[item.Name] = text;
    }
}

// Invoke one RPC and return its raw response messages (one for unary).
async Task<List<IMessage>> Call(string operation, string requestFixture, int timeoutSeconds = 30)
{
    var rpc = Rpc.For(operation);
    var request = Parse(requestFixture, rpc.Descriptor.InputType);
    var options = new CallOptions(headers, DateTime.UtcNow.AddSeconds(timeoutSeconds));
    if (rpc.Descriptor.IsServerStreaming)
    {
        using var stream = invoker.AsyncServerStreamingCall(rpc.Method, null, options, request);
        var messages = new List<IMessage>();
        while (await stream.ResponseStream.MoveNext(CancellationToken.None))
        {
            messages.Add(stream.ResponseStream.Current);
        }
        return messages;
    }
    return [await invoker.AsyncUnaryCall(rpc.Method, null, options, request).ResponseAsync];
}

string Describe(Exception exception) => exception is ScenarioFailure
    ? exception.Message
    : $"Canonical published client executed and failed: {exception.GetType().Name}: {exception.Message}";

async Task RunNegative(JsonElement scenario)
{
    var operation = scenario.GetProperty("operation").GetString()!;
    var negative = scenario.GetProperty("negative");
    var negativeRequest = negative.GetProperty("request").GetString()!;
    using var expectedStatus = JsonDocument.Parse(ReadFixture(negative.GetProperty("status").GetString()!));
    var expectedCode = expectedStatus.RootElement.GetProperty("code").GetInt32();
    var expectedName = expectedStatus.RootElement.GetProperty("name").GetString();
    RpcException? rejection = null;
    try
    {
        await Call(operation, negativeRequest);
    }
    catch (RpcException exception)
    {
        rejection = exception;
    }
    if (rejection is null)
    {
        throw new ScenarioFailure($"Negative case {negativeRequest} succeeded; expected it to fail with status {expectedName}");
    }
    if ((int)rejection.StatusCode != expectedCode)
    {
        throw new ScenarioFailure($"Negative case {negativeRequest} expected status {expectedName}, got {rejection.StatusCode}: {rejection.Status.Detail}");
    }
    if (negative.TryGetProperty("verify", out var verify))
    {
        var verifyOperation = verify.GetProperty("operation").GetString()!;
        var verifyResponse = (await Call(verifyOperation, verify.GetProperty("request").GetString()!))[0];
        var verifyDivergence = CompareUnary(verifyOperation, verify.GetProperty("response").GetString()!, Canonical(verifyResponse));
        if (verifyDivergence is not null)
        {
            throw new ScenarioFailure($"Negative case {negativeRequest} was rejected, but reading its targets back does not match the unchanged state at {verifyDivergence}");
        }
    }
}

async Task<List<IMessage>> RunPositiveOnce(JsonElement scenario, List<IMessage> decoded)
{
    var operation = scenario.GetProperty("operation").GetString()!;
    if (scenario.TryGetProperty("setup", out var setup))
    {
        var created = (await Call(setup.GetProperty("operation").GetString()!, setup.GetProperty("request").GetString()!))[0];
        Capture(setup, "capture", Canonical(created));
    }
    var rpc = Rpc.For(operation);
    List<IMessage> messages;
    string? divergence;
    if (scenario.GetProperty("kind").GetString() == "server_stream")
    {
        var prefix = scenario.GetProperty("responses").GetString()!;
        messages = await Call(operation, scenario.GetProperty("request").GetString()!, 60);
        decoded.AddRange(messages);
        var expected = new JsonArray();
        for (var index = 1; File.Exists(Path.Combine(fixtureDirectory, $"{prefix}.{index}.json")); index++)
        {
            expected.Add(Masked(operation, Canonical(Parse($"{prefix}.{index}.json", rpc.Descriptor.OutputType))));
        }
        if (expected.Count == 0)
        {
            throw new ScenarioFailure($"no {prefix}.N.json fixtures");
        }
        if (messages.Count > 0)
        {
            Capture(scenario, "capture", Canonical(messages[0]));
        }
        var actual = new JsonArray(messages.Select(message => (JsonNode?)Masked(operation, Canonical(message))).ToArray());
        divergence = Divergence(expected, actual);
    }
    else
    {
        var request = scenario.GetProperty("request").GetString()!;
        var response = (await Call(operation, request))[0];
        decoded.Add(response);
        if (scenario.TryGetProperty("poll_until", out var poll))
        {
            var pollPath = poll.GetProperty("path").GetString()!;
            var terminal = poll.GetProperty("values").EnumerateArray().Select(value => value.GetString()).ToHashSet();
            var timeout = double.Parse(pollTimeoutOverride ?? poll.GetProperty("timeout_seconds").GetRawText(),
                System.Globalization.CultureInfo.InvariantCulture);
            var deadline = DateTime.UtcNow.AddSeconds(timeout);
            while (!terminal.Contains((ReadPath(Canonical(response), pollPath) as JsonValue)?.ToString()) && DateTime.UtcNow < deadline)
            {
                await Task.Delay(TimeSpan.FromSeconds(1));
                response = (await Call(operation, request))[0];
                decoded.Add(response);
            }
        }
        Capture(scenario, "capture", Canonical(response));
        messages = [response];
        divergence = CompareUnary(operation, scenario.GetProperty("response").GetString()!, Canonical(response));
    }
    if (divergence is not null)
    {
        throw new ScenarioFailure($"Canonical response mismatch at {divergence}");
    }
    return messages;
}

async Task<List<IMessage>> RunPositive(JsonElement scenario, List<IMessage> decoded)
{
    var attempts = scenario.TryGetProperty("setup_race_retry", out var retry) ? retry.GetProperty("attempts").GetInt32() : 1;
    for (var attempt = 1; ; attempt++)
    {
        try
        {
            return await RunPositiveOnce(scenario, decoded);
        }
        // The setup produced a job that finished before the call (outside the
        // contract under test); redo setup and call.
        catch (RpcException race) when (attempt < attempts
            && (int)race.StatusCode == retry.GetProperty("status_code").GetInt32())
        {
        }
    }
}

foreach (var scenario in scenarioDocument.RootElement.GetProperty("scenarios").EnumerateArray())
{
    var operation = scenario.GetProperty("operation").GetString()!;
    var hasNegative = scenario.TryGetProperty("negative", out _);
    var facets = new Dictionary<string, string>();
    var reasons = new List<string>();
    if (hasNegative)
    {
        try
        {
            await RunNegative(scenario);
            facets["negative"] = "pass";
        }
        catch (Exception exception)
        {
            facets["negative"] = "fail";
            reasons.Add($"negative: {Describe(exception)}");
        }
    }
    var decoded = new List<IMessage>();
    try
    {
        await RunPositive(scenario, decoded);
        facets["positive"] = "pass";
    }
    catch (Exception exception)
    {
        facets["positive"] = "fail";
        reasons.Add(hasNegative ? $"positive: {Describe(exception)}" : Describe(exception));
    }
    if (!hasNegative)
    {
        outcomes[operation] = facets["positive"] == "pass"
            ? new { result = "pass" }
            : new { result = "fail", reason = reasons[0] };
        continue;
    }
    // media-schema covers every positive response the client decoded, including
    // polled ones, whether or not the comparison passed.
    var unknown = decoded.SelectMany(message => UnknownFieldPaths(message, "$")).ToList();
    if (decoded.Count == 0)
    {
        facets["media-schema"] = "fail";
        reasons.Add("media-schema: no positive response to check");
    }
    else if (unknown.Count > 0)
    {
        facets["media-schema"] = "fail";
        reasons.Add($"media-schema: fields unknown to the installed schema at {string.Join(", ", unknown)}");
    }
    else
    {
        facets["media-schema"] = "pass";
    }
    var passed = facets.Values.All(value => value == "pass");
    outcomes[operation] = passed
        ? new { result = "pass", facet_results = facets }
        : new { result = "fail", facet_results = facets, reason = string.Join("; ", reasons) };
}

Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);
await File.WriteAllTextAsync(reportPath, JsonSerializer.Serialize(new
{
    runner_lane = "grpc-dotnet",
    package = "Geospatial.Grpc",
    package_version = typeof(FeatureService).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()
        ?.InformationalVersion.Split('+')[0]
        ?? typeof(FeatureService).Assembly.GetName().Version!.ToString(3),
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
// Excluded operations are still executed and reported, but only a governed
// failure fails the lane (the fragment reports excluded results separately).
using var catalog = JsonDocument.Parse(
    await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, "protocol-certification-catalog.v1.json")));
var excludedOperations = catalog.RootElement.TryGetProperty("excluded_operations", out var excludedList)
    ? excludedList.EnumerateArray().Select(operation => operation.GetProperty("operation").GetString()!).ToHashSet()
    : [];
var governedFailures = outcomes.Count(outcome =>
    !excludedOperations.Contains(outcome.Key)
    && JsonSerializer.SerializeToElement(outcome.Value).GetProperty("result").GetString() == "fail");
return governedFailures == 0 ? 0 : 1;

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
        throw new InvalidOperationException($"path must start with '$.': {pattern}");
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
        throw new InvalidOperationException($"malformed path: {pattern}");
    }
    return tokens;
}

static JsonNode? ReadPath(JsonNode document, string pattern)
{
    JsonNode? node = document;
    foreach (var token in PathTokens(pattern))
    {
        if (token == "[*]" || node is not JsonObject obj || !obj.TryGetPropertyValue(token, out node))
        {
            return null;
        }
    }
    return node;
}

// Replace each present server-assigned value with a placeholder. Absent values
// stay absent, so the comparison still requires a required path on both sides.
// Optional paths (values that may validly be the proto3 default, which the JSON
// mapping omits) are removed instead.
static JsonNode MaskServerAssigned(JsonNode root, string[] patterns, string[] optional)
{
    foreach (var pattern in patterns)
    {
        Visit(root, PathTokens(pattern), 0, remove: false);
    }
    foreach (var pattern in optional)
    {
        Visit(root, PathTokens(pattern), 0, remove: true);
    }
    return root;

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

// Paths of fields the installed generated schema does not define, at any depth.
static IEnumerable<string> UnknownFieldPaths(IMessage message, string path)
{
    var unknown = message.GetType().GetField("_unknownFields", BindingFlags.Instance | BindingFlags.NonPublic)
        ?.GetValue(message) as UnknownFieldSet;
    if (unknown is not null && unknown.CalculateSize() > 0)
    {
        yield return path;
    }
    foreach (var field in message.Descriptor.Fields.InDeclarationOrder())
    {
        if (field.FieldType != Google.Protobuf.Reflection.FieldType.Message)
        {
            continue;
        }
        var value = field.Accessor.GetValue(message);
        var child = $"{path}.{field.JsonName}";
        if (field.IsMap)
        {
            if (field.MessageType.FindFieldByName("value").FieldType != Google.Protobuf.Reflection.FieldType.Message)
            {
                continue;
            }
            foreach (System.Collections.DictionaryEntry entry in (System.Collections.IDictionary)value)
            {
                foreach (var found in UnknownFieldPaths((IMessage)entry.Value!, $"{child}[{entry.Key}]"))
                {
                    yield return found;
                }
            }
        }
        else if (field.IsRepeated)
        {
            var index = 0;
            foreach (var item in (System.Collections.IEnumerable)value)
            {
                foreach (var found in UnknownFieldPaths((IMessage)item, $"{child}[{index++}]"))
                {
                    yield return found;
                }
            }
        }
        else if (value is IMessage nested)
        {
            foreach (var found in UnknownFieldPaths(nested, child))
            {
                yield return found;
            }
        }
    }
}

static string? Divergence(JsonNode expected, JsonNode actual)
{
    using var expectedDocument = JsonDocument.Parse(expected.ToJsonString());
    using var actualDocument = JsonDocument.Parse(actual.ToJsonString());
    return FirstDivergence(expectedDocument.RootElement, actualDocument.RootElement, "$");
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

sealed class ScenarioFailure(string message) : Exception(message);

// One geospatial.v1 RPC bound to the installed package's descriptors and marshallers.
sealed class Rpc
{
    private static readonly Dictionary<string, Rpc> Cache = new(StringComparer.Ordinal);

    private Rpc(MethodDescriptor descriptor)
    {
        Descriptor = descriptor;
        Method = new Method<IMessage, IMessage>(
            descriptor.IsServerStreaming ? MethodType.ServerStreaming : MethodType.Unary,
            descriptor.Service.FullName,
            descriptor.Name,
            Marshallers.Create<IMessage>(message => message.ToByteArray(), bytes => descriptor.InputType.Parser.ParseFrom(bytes)),
            Marshallers.Create<IMessage>(message => message.ToByteArray(), bytes => descriptor.OutputType.Parser.ParseFrom(bytes)));
    }

    public MethodDescriptor Descriptor { get; }

    public Method<IMessage, IMessage> Method { get; }

    public static Rpc For(string operation)
    {
        if (Cache.TryGetValue(operation, out var cached))
        {
            return cached;
        }
        var parts = operation.Split('/');
        var reflection = typeof(FeatureService).Assembly.GetType($"Geospatial.V1.{parts[0]}Reflection")
            ?? throw new InvalidOperationException($"{parts[0]} is not in the installed Geospatial.Grpc");
        var file = (FileDescriptor)reflection.GetProperty("Descriptor")!.GetValue(null)!;
        var method = file.FindTypeByName<ServiceDescriptor>(parts[0])?.FindMethodByName(parts[1])
            ?? throw new InvalidOperationException($"{operation} is not in the installed Geospatial.Grpc");
        return Cache[operation] = new Rpc(method);
    }
}
