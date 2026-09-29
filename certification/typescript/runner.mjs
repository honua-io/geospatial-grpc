// Execute the promoted @honua/geospatial-grpc package against a live target.
//
// TypeScript/JavaScript counterpart of certification/dotnet/Program.cs and
// certification/python/runner.py. It runs every scenario in
// certification/scenarios.v1.json through the installed generated client (never
// a source checkout) over a real gRPC (HTTP/2) transport, compares each
// canonical response with the fixture, and writes a lane report consumed by
// scripts/build_protocol_certification_fragment.py.
//
// The installed package version is reported exactly as installed. The fragment
// builder decides whether it satisfies the governed cell.
//
// usage: node runner.mjs <absolute-channel-target> <fixture-directory> <report-path>
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { fromJson, toJson } from "@bufbuild/protobuf";
import { ConnectError, createClient } from "@connectrpc/connect";
import { createGrpcTransport } from "@connectrpc/connect-node";

const PACKAGE = "@honua/geospatial-grpc";
const PACKAGE_SOURCE = "https://registry.npmjs.org/@honua/geospatial-grpc";
const certificationFile = (name) => fileURLToPath(new URL(`../${name}`, import.meta.url));
const SERVER_ASSIGNED_FIELDS = certificationFile("server-assigned-fields.v1.json");
const SCENARIOS = certificationFile("scenarios.v1.json");
const CATALOG = certificationFile("protocol-certification-catalog.v1.json");
const SERVER_ASSIGNED = "<server-assigned>";
const CAPTURE = /\{\{capture:([A-Za-z0-9_]+)\}\}/g;
const POLL_INTERVAL_MS = 1000;

class ScenarioFailure extends Error {}

async function loadJson(file, schema) {
  const document = JSON.parse(await readFile(file, "utf8"));
  if (document.schema !== schema) throw new Error(`unsupported document ${file}`);
  return document;
}

export async function loadServerAssignedFields(file = SERVER_ASSIGNED_FIELDS) {
  const document = await loadJson(file, "honua.grpc-certification-server-assigned-fields/v1");
  return { required: document.operations, optional: document.optional_operations ?? {} };
}

// Operations the 2026.1 scope ruling excludes from the governed cells (#88).
async function loadExcludedOperations(file = CATALOG) {
  const catalog = JSON.parse(await readFile(file, "utf8"));
  return new Set((catalog.excluded_operations ?? []).map((operation) => operation.operation));
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

function pathTokens(pattern) {
  if (!pattern.startsWith("$.")) throw new Error(`path must start with '$.': ${pattern}`);
  const tokens = [];
  for (const part of pattern.slice(2).split(".")) {
    if (part.endsWith("[*]")) tokens.push(part.slice(0, -3), "[*]");
    else tokens.push(part);
  }
  if (tokens.length === 0 || tokens.some((token) => token === "")) throw new Error(`malformed path: ${pattern}`);
  return tokens;
}

function kind(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

function readPath(document, pattern) {
  let node = document;
  for (const token of pathTokens(pattern)) {
    if (token === "[*]" || kind(node) !== "object" || !(token in node)) return undefined;
    node = node[token];
  }
  return node;
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

const serviceModules = {};
async function methodFor(operation) {
  const [service, name] = operation.split("/");
  if (!serviceModules[service]) {
    const snake = service.replace(/(?<!^)(?=[A-Z])/g, "_").toLowerCase();
    serviceModules[service] = await import(`@honua/geospatial-grpc/geospatial/v1/${snake}_pb.js`);
  }
  const descriptor = serviceModules[service][service];
  const method = Object.values(descriptor.method).find((candidate) => candidate.name === name);
  if (!method) throw new Error(`${operation} is not in the installed ${PACKAGE}`);
  return { descriptor, method };
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
  const pollTimeoutOverride = process.env.HONUA_CERTIFICATION_POLL_TIMEOUT_SECONDS;
  const headers = { "x-api-key": apiKey };
  const transport = createGrpcTransport({ baseUrl: target.origin });
  const outcomes = {};
  const captures = {};
  const startedAt = new Date();
  const serverAssigned = await loadServerAssignedFields();
  const scenarios = (await loadJson(SCENARIOS, "honua.grpc-certification-scenarios/v1")).scenarios;
  const clients = new Map();

  async function readFixture(name) {
    const text = await readFile(path.join(fixtureDirectory, name), "utf8");
    return text.replace(CAPTURE, (_, key) => {
      if (!(key in captures)) {
        throw new ScenarioFailure(`${name} needs capture '${key}', which an earlier scenario did not provide`);
      }
      return captures[key];
    });
  }

  const parse = async (name, schema) => fromJson(schema, JSON.parse(await readFixture(name)));
  const masked = (operation, document) => maskServerAssigned(
    document, serverAssigned.required[operation] ?? [], serverAssigned.optional[operation] ?? []);

  async function bind(operation) {
    const { descriptor, method } = await methodFor(operation);
    if (!clients.has(descriptor.typeName)) clients.set(descriptor.typeName, createClient(descriptor, transport));
    return { method, invoke: clients.get(descriptor.typeName)[method.localName] };
  }

  async function unary(operation, requestFixture) {
    const { method, invoke } = await bind(operation);
    const response = await invoke(await parse(requestFixture, method.input), { headers, timeoutMs: 30_000 });
    return toJson(method.output, response);
  }

  async function compareUnary(operation, responseFixture, response) {
    const { method } = await bind(operation);
    const expected = toJson(method.output, await parse(responseFixture, method.output));
    return firstDivergence(masked(operation, expected), masked(operation, response));
  }

  function capture(spec, document) {
    for (const [key, pattern] of Object.entries(spec ?? {})) {
      const value = readPath(document, pattern);
      if (typeof value !== "string" || value === "") {
        throw new ScenarioFailure(`response has no value at ${pattern} to capture as '${key}'`);
      }
      captures[key] = value;
    }
  }

  async function run(scenario) {
    const operation = scenario.operation;
    if (scenario.setup) capture(scenario.setup.capture, await unary(scenario.setup.operation, scenario.setup.request));
    if (scenario.negative) {
      const negative = scenario.negative;
      const expectedStatus = JSON.parse(await readFixture(negative.status));
      let rejection = null;
      try {
        await unary(operation, negative.request);
      } catch (error) {
        if (!(error instanceof ConnectError)) throw error;
        rejection = error;
      }
      if (rejection === null) {
        throw new ScenarioFailure(`Negative case ${negative.request} succeeded; expected the whole batch to fail with status ${expectedStatus.name}`);
      }
      if (rejection.code !== expectedStatus.code) {
        throw new ScenarioFailure(`Negative case ${negative.request} expected status ${expectedStatus.name}, got code ${rejection.code}: ${rejection.rawMessage}`);
      }
      if (negative.verify) {
        const divergence = await compareUnary(
          negative.verify.operation, negative.verify.response,
          await unary(negative.verify.operation, negative.verify.request));
        if (divergence !== null) {
          throw new ScenarioFailure(`Negative case ${negative.request} was rejected, but reading its targets back does not match the unchanged state at ${divergence}`);
        }
      }
    }
    let divergence;
    if (scenario.kind === "server_stream") {
      const { method, invoke } = await bind(operation);
      const messages = [];
      for await (const message of invoke(await parse(scenario.request, method.input), { headers, timeoutMs: 60_000 })) {
        messages.push(toJson(method.output, message));
      }
      const expected = [];
      for (let index = 1; existsSync(path.join(fixtureDirectory, `${scenario.responses}.${index}.json`)); index++) {
        expected.push(masked(operation, toJson(method.output,
          await parse(`${scenario.responses}.${index}.json`, method.output))));
      }
      if (expected.length === 0) throw new ScenarioFailure(`no ${scenario.responses}.N.json fixtures`);
      if (messages.length) capture(scenario.capture, structuredClone(messages[0]));
      divergence = firstDivergence(expected, messages.map((message) => masked(operation, message)));
    } else {
      let response = await unary(operation, scenario.request);
      const poll = scenario.poll_until;
      if (poll) {
        const deadline = Date.now() + 1000 * Number(pollTimeoutOverride ?? poll.timeout_seconds);
        while (!poll.values.includes(readPath(response, poll.path)) && Date.now() < deadline) {
          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
          response = await unary(operation, scenario.request);
        }
      }
      capture(scenario.capture, response);
      divergence = await compareUnary(operation, scenario.response, response);
    }
    if (divergence !== null) throw new ScenarioFailure(`Canonical response mismatch at ${divergence}`);
  }

  for (const scenario of scenarios) {
    try {
      const retry = scenario.setup_race_retry;
      const attempts = retry ? retry.attempts : 1;
      for (let attempt = 1; ; attempt++) {
        try {
          await run(scenario);
          break;
        } catch (race) {
          // The setup produced a job that finished before the call (outside the
          // contract under test); redo setup and call.
          if (!retry || !(race instanceof ConnectError) || race.code !== retry.status_code || attempt >= attempts) {
            throw race;
          }
        }
      }
      outcomes[scenario.operation] = { result: "pass" };
    } catch (error) {
      if (error instanceof ScenarioFailure) {
        outcomes[scenario.operation] = { result: "fail", reason: error.message };
        continue;
      }
      const name = error instanceof ConnectError ? "ConnectError" : error?.constructor?.name ?? "Error";
      outcomes[scenario.operation] = {
        result: "fail",
        reason: `Canonical published client executed and failed: ${name}: ${error?.message ?? String(error)}`,
      };
    }
  }

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
  // Excluded operations are still executed and reported, but only a governed
  // failure fails the lane (the fragment reports excluded results separately).
  const excluded = await loadExcludedOperations();
  const governedFailures = Object.entries(outcomes)
    .filter(([name, outcome]) => outcome.result === "fail" && !excluded.has(name)).length;
  return governedFailures === 0 ? 0 : 1;
}

process.exitCode = await main(process.argv.slice(2));
