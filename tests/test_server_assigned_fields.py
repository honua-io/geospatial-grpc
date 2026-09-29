"""The server-assigned normalization list may only cover values a server assigns.

certification/server-assigned-fields.v1.json tells every certification runner
which response values not to compare. A path that resolves to nothing would be
a silent no-op, and a path that covers a value the client supplied would weaken
a semantic assertion. These checks keep the list exact, for every scenario in
certification/scenarios.v1.json.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ROOT / "certification" / "server-assigned-fields.v1.json"
SCENARIOS = ROOT / "certification" / "scenarios.v1.json"
FIXTURES = ROOT / "conformance" / "fixtures"
CAPTURE = re.compile(r"\{\{capture:[A-Za-z0-9_]+\}\}")


def resolve(document: object, pattern: str) -> list[object]:
    """Every value the pattern selects."""
    assert pattern.startswith("$."), pattern
    nodes = [document]
    for part in pattern[2:].split("."):
        wildcard = part.endswith("[*]")
        name = part[:-3] if wildcard else part
        nodes = [node[name] for node in nodes if isinstance(node, dict) and name in node]
        if wildcard:
            nodes = [item for node in nodes if isinstance(node, list) for item in node]
    return nodes


def scalar_values(document: object) -> set[str]:
    if isinstance(document, dict):
        return set().union(*(scalar_values(value) for value in document.values())) if document else set()
    if isinstance(document, list):
        return set().union(*(scalar_values(value) for value in document)) if document else set()
    return {json.dumps(document)}


def load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def expected_responses(scenario: dict) -> list[object]:
    if scenario["kind"] == "server_stream":
        messages = []
        index = 1
        while (FIXTURES / f"{scenario['responses']}.{index}.json").is_file():
            messages.append(load(f"{scenario['responses']}.{index}.json"))
            index += 1
        return messages
    return [load(scenario["response"])]


class ServerAssignedFieldsTests(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(FIELDS.read_text(encoding="utf-8"))
        self.assertEqual("honua.grpc-certification-server-assigned-fields/v1", document["schema"])
        self.operations = document["operations"]
        self.optional = document.get("optional_operations", {})
        self.every = {
            operation: [*self.operations.get(operation, []), *self.optional.get(operation, [])]
            for operation in {*self.operations, *self.optional}
        }
        scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        self.assertEqual("honua.grpc-certification-scenarios/v1", scenarios["schema"])
        self.scenarios = {scenario["operation"]: scenario for scenario in scenarios["scenarios"]}

    def test_every_listed_operation_is_a_scenario(self):
        self.assertEqual(set(), set(self.every) - set(self.scenarios))

    def test_no_path_is_both_required_and_optional(self):
        for operation, patterns in self.optional.items():
            self.assertEqual(set(), set(patterns) & set(self.operations.get(operation, [])))

    def test_every_scenario_has_its_fixtures(self):
        for operation, scenario in self.scenarios.items():
            with self.subTest(operation=operation):
                self.assertTrue((FIXTURES / scenario["request"]).is_file())
                self.assertTrue(expected_responses(scenario), f"{operation} has no expected response")

    def test_every_path_selects_a_value_in_the_expected_response(self):
        for operation, patterns in self.every.items():
            responses = expected_responses(self.scenarios[operation])
            for pattern in patterns:
                with self.subTest(operation=operation, pattern=pattern):
                    self.assertTrue(any(resolve(response, pattern) for response in responses),
                                    f"{pattern} selects nothing")

    def test_no_path_covers_a_value_the_client_supplied(self):
        for operation, patterns in self.every.items():
            scenario = self.scenarios[operation]
            supplied = scalar_values(load(scenario["request"]))
            for response in expected_responses(scenario):
                for pattern in patterns:
                    for value in resolve(response, pattern):
                        with self.subTest(operation=operation, pattern=pattern, value=value):
                            self.assertNotIn(json.dumps(value), supplied)

    def test_no_path_covers_a_bound_echo(self):
        # An id the client sends back ({{capture:...}}) is compared exactly, never masked.
        for operation, patterns in self.every.items():
            for response in expected_responses(self.scenarios[operation]):
                for pattern in patterns:
                    for value in resolve(response, pattern):
                        with self.subTest(operation=operation, pattern=pattern):
                            self.assertFalse(isinstance(value, str) and CAPTURE.search(value))

    def test_query_features_is_compared_exactly(self):
        # Every QueryFeatures value is seeded or requested; none is server-assigned.
        self.assertNotIn("FeatureService/QueryFeatures", self.every)
        self.assertNotIn("FeatureService/QueryFeaturesStream", self.every)


if __name__ == "__main__":
    unittest.main()
