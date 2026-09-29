// Execute the promoted @honua/geospatial-grpc package against a live target.
//
// TypeScript/JavaScript counterpart of certification/dotnet/Program.cs. It runs
// the same six conformance fixtures through the installed generated client
// (never a source checkout) over a real gRPC (HTTP/2) transport, compares each
// canonical response with the fixture, and writes a lane report consumed by
// scripts/build_protocol_certification_fragment.py.
//
// The installed package version is reported exactly as installed. The fragment
// builder decides whether it satisfies the governed cell; a promoted package
// that is not the governed client_version stays an attributable execution
// result and never a governed pass.
//
// usage: node runner.mjs <absolute-channel-target> <fixture-directory> <report-path>
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { fromJson, toJson } from "@bufbuild/protobuf";
import { ConnectError, createClient } from "@connectrpc/connect";
import { createGrpcTransport } from "@connectrpc/connect-node";
import {
  ApplyEditsRequestSchema,
  ApplyEditsResponseSchema,
  FeatureService,
  QueryFeaturesRequestSchema,
  QueryFeaturesResponseSchema,
} from "@honua/geospatial-grpc/geospatial/v1/feature_service_pb.js";
import {
  FormService,
  GetFormDefinitionRequestSchema,
  GetFormDefinitionResponseSchema,
  SubmitFormDataRequestSchema,
  SubmitFormDataResponseSchema,
} from "@honua/geospatial-grpc/geospatial/v1/form_service_pb.js";
import {
  ExecutePlanRequestSchema,
  ExecutePlanResponseSchema,
  ProcessService,
} from "@honua/geospatial-grpc/geospatial/v1/process_service_pb.js";
import {
  CreateWorkspaceRequestSchema,
  CreateWorkspaceResponseSchema,
  WorkspaceService,
} from "@honua/geospatial-grpc/geospatial/v1/workspace_service_pb.js";

const PACKAGE = "@honua/geospatial-grpc";
const PACKAGE_SOURCE = "https://registry.npmjs.org/@honua/geospatial-grpc";
const SERVER_ASSIGNED_FIELDS = fileURLToPath(new URL("../server-assigned-fields.v1.json", import.meta.url));
const SERVER_ASSIGNED = "<server-assigned>";

export async function loadServerAssignedFields(file = SERVER_ASSIGNED_FIELDS) {
  const document = JSON.parse(await readFile(file, "utf8"));
  if (document.schema !== "honua.grpc-certification-server-assigned-fields/v1") {
    throw new Error(`unsupported server-assigned field list: ${file}`);
  }
  return { required: document.operations, optional: document.optional_operations ?? {} };
}

function pathTokens(pattern) {
  if (!pattern.startsWith("$.")) throw new Error(`server-assigned path must start with '$.': ${pattern}`);
  const tokens = [];
  for (const part of pattern.slice(2).split(".")) {
    if (part.endsWith("[*]")) tokens.push(part.slice(0, -3), "[*]");
    else tokens.push(part);
  }
  if (tokens.length === 0 || tokens.some((token) => token === "")) {
    throw new Error(`malformed server-assigned path: ${pattern}`);
  }
  return tokens;
}

// Replace each present server-assigned value with a placeholder. Absent values
// stay absent, so the comparison still requires a required path on both sides.
// Optional paths (values that may validly be the proto3 default, which the JSON
// mapping omits) are removed instead.
export function maskServerAssigned(document, patterns, optional = []) {
  const visit = (node, tokens, remove) => {
    const [head, ...rest] = tokens;
    if (head === "[*]") {
      if (!Array.isArray(node)) return;
      if (rest.length) node.forEach((item) => visit(item, rest, remove));
      else if (!remove) node.fill(SERVER_ASSIGNED);
      return;
    }
    if (kind(node) !== "object" || !(head in node)) return;
    if (rest.length) visit(node[head], rest, remove);
    else if (remove) delete node[head];
    else node[head] = SERVER_ASSIGNED;
  };
  for (const pattern of patterns) visit(document, pathTokens(pattern), false);
  for (const pattern of optional) visit(document, pathTokens(pattern), true);
  return document;
}

function installedPackageRoot() {
  // The package's exports map does not expose package.json, so resolve it from
  // the installed module directory rather than trusting a hard-coded version.
  const entry = fileURLToPath(import.meta.resolve("@honua/geospatial-grpc/geospatial/v1/feature_service_pb.js"));
  let directory = path.dirname(entry);
  while (path.basename(directory) !== "geospatial-grpc") {
    const parent = path.dirname(directory);
    if (parent === directory) throw new Error(`cannot locate ${PACKAGE} package root from ${entry}`);
    directory = parent;
  }
  return directory;
}

function kind(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

export function firstDivergence(expected, actual, at = "$") {
  if (kind(expected) !== kind(actual)) return at;
  if (kind(expected) === "object") {
    const names = [...new Set([...Object.keys(expected), ...Object.keys(actual)])].sort();
    for (const name of names) {
      const child = `${at}.${name}`;
      if (!(name in expected) || !(name in actual)) return child;
      const divergence = firstDivergence(expected[name], actual[name], child);
      if (divergence !== null) return divergence;
    }
    return null;
  }
  if (kind(expected) === "array") {
    const shared = Math.min(expected.length, actual.length);
    for (let index = 0; index < shared; index++) {
      const divergence = firstDivergence(expected[index], actual[index], `${at}[${index}]`);
      if (divergence !== null) return divergence;
    }
    return expected.length === actual.length ? null : `${at}[${shared}]`;
  }
  return Object.is(expected, actual) || expected === actual ? null : at;
}

async function main(argv) {
  if (argv.length !== 3) {
    console.error("usage: runner.mjs <absolute-channel-target> <fixture-directory> <report-path>");
    return 2;
  }
  const target = new URL(argv[0]);
  if (!["http:", "https:"].includes(target.protocol) || !target.port) {
    console.error("channel target must be an absolute http(s)://host:port URL");
    return 2;
  }
  const fixtureDirectory = path.resolve(argv[1]);
  const reportPath = path.resolve(argv[2]);
  const apiKey = process.env.HONUA_PROTOCOL_API_KEY;
  if (!apiKey) throw new Error("HONUA_PROTOCOL_API_KEY is required");
  const headers = { "x-api-key": apiKey };
  const transport = createGrpcTransport({ baseUrl: target.origin });
  const outcomes = {};
  let failures = 0;
  const startedAt = new Date();
  const serverAssigned = await loadServerAssignedFields();

  // Call once and return the first divergence from the fixture, or null.
  async function compare(operation, requestFixture, responseFixture, requestSchema, responseSchema, invoke) {
    const requestJson = JSON.parse(await readFile(path.join(fixtureDirectory, requestFixture), "utf8"));
    const request = fromJson(requestSchema, requestJson);
    const response = await invoke(request, { headers, timeoutMs: 30_000 });
    const expectedJson = JSON.parse(await readFile(path.join(fixtureDirectory, responseFixture), "utf8"));
    const expected = fromJson(responseSchema, expectedJson);
    const patterns = serverAssigned.required[operation] ?? [];
    const optional = serverAssigned.optional[operation] ?? [];
    return firstDivergence(
      maskServerAssigned(toJson(responseSchema, expected), patterns, optional),
      maskServerAssigned(toJson(responseSchema, response), patterns, optional),
    );
  }

  async function execute(operation, requestFixture, responseFixture, requestSchema, responseSchema, invoke,
    negative = null) {
    try {
      if (negative !== null) {
        const [negativeRequestFixture, negativeStatusFixture, verify] = negative;
        const negativeRequest = fromJson(requestSchema,
          JSON.parse(await readFile(path.join(fixtureDirectory, negativeRequestFixture), "utf8")));
        const expectedStatus = JSON.parse(await readFile(path.join(fixtureDirectory, negativeStatusFixture), "utf8"));
        let rejection = null;
        try {
          await invoke(negativeRequest, { headers, timeoutMs: 30_000 });
        } catch (error) {
          if (!(error instanceof ConnectError)) throw error;
          rejection = error;
        }
        if (rejection === null) {
          failures++;
          outcomes[operation] = {
            result: "fail",
            reason: `Negative case ${negativeRequestFixture} succeeded; expected the whole batch to fail with status ${expectedStatus.name}`,
          };
          return;
        }
        if (rejection.code !== expectedStatus.code) {
          failures++;
          outcomes[operation] = {
            result: "fail",
            reason: `Negative case ${negativeRequestFixture} expected status ${expectedStatus.name}, got code ${rejection.code}: ${rejection.rawMessage}`,
          };
          return;
        }
        // The rejected batch must have applied nothing: read its targets back.
        const verifyDivergence = await verify();
        if (verifyDivergence !== null) {
          failures++;
          outcomes[operation] = {
            result: "fail",
            reason: `Negative case ${negativeRequestFixture} was rejected but changed state: read-back mismatch at ${verifyDivergence}`,
          };
          return;
        }
      }
      const divergence = await compare(operation, requestFixture, responseFixture, requestSchema, responseSchema, invoke);
      if (divergence !== null) {
        failures++;
        outcomes[operation] = { result: "fail", reason: `Canonical response mismatch at ${divergence}` };
        return;
      }
      outcomes[operation] = { result: "pass" };
    } catch (error) {
      failures++;
      const name = error instanceof ConnectError ? "ConnectError" : error?.constructor?.name ?? "Error";
      outcomes[operation] = {
        result: "fail",
        reason: `Canonical published client executed and failed: ${name}: ${error?.message ?? String(error)}`,
      };
    }
  }

  const feature = createClient(FeatureService, transport);
  const form = createClient(FormService, transport);
  const processClient = createClient(ProcessService, transport);
  const workspace = createClient(WorkspaceService, transport);

  await execute("FeatureService/QueryFeatures", "feature_query_request.json", "feature_query_response.json",
    QueryFeaturesRequestSchema, QueryFeaturesResponseSchema, (r, o) => feature.queryFeatures(r, o));
  await execute("FeatureService/ApplyEdits", "feature_apply_edits_request.json", "feature_apply_edits_response.json",
    ApplyEditsRequestSchema, ApplyEditsResponseSchema, (r, o) => feature.applyEdits(r, o),
    ["feature_apply_edits_missing_target_request.json", "feature_apply_edits_missing_target_status.json",
      () => compare("FeatureService/QueryFeatures",
        "feature_apply_edits_missing_target_verify_request.json",
        "feature_apply_edits_missing_target_verify_response.json",
        QueryFeaturesRequestSchema, QueryFeaturesResponseSchema, (r, o) => feature.queryFeatures(r, o))]);
  await execute("FormService/GetFormDefinition", "form_get_definition_request.json", "form_get_definition_response.json",
    GetFormDefinitionRequestSchema, GetFormDefinitionResponseSchema, (r, o) => form.getFormDefinition(r, o));
  await execute("FormService/SubmitFormData", "form_submit_request.json", "form_submit_response.json",
    SubmitFormDataRequestSchema, SubmitFormDataResponseSchema, (r, o) => form.submitFormData(r, o));
  await execute("ProcessService/ExecutePlan", "process_execute_plan_request.json", "process_execute_plan_response.json",
    ExecutePlanRequestSchema, ExecutePlanResponseSchema, (r, o) => processClient.executePlan(r, o));
  await execute("WorkspaceService/CreateWorkspace", "workspace_create_request.json", "workspace_create_response.json",
    CreateWorkspaceRequestSchema, CreateWorkspaceResponseSchema, (r, o) => workspace.createWorkspace(r, o));

  const packageRoot = installedPackageRoot();
  const packageVersion = JSON.parse(await readFile(path.join(packageRoot, "package.json"), "utf8")).version;
  const report = {
    runner_lane: "grpc-typescript",
    package: PACKAGE,
    package_version: packageVersion,
    package_source: PACKAGE_SOURCE,
    started_at: startedAt.toISOString(),
    completed_at: new Date().toISOString(),
    execution_identity: {
      channel_target: target.origin,
      server_image: process.env.SERVER_IMAGE ?? null,
      server_source_sha: process.env.SERVER_SOURCE_SHA ?? null,
      fixture_revision: process.env.FIXTURE_REVISION ?? null,
    },
    operations: outcomes,
  };
  await mkdir(path.dirname(reportPath), { recursive: true });
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  return failures === 0 ? 0 : 1;
}

process.exitCode = await main(process.argv.slice(2));
