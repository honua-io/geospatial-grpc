"""The server-assigned normalization list may only cover values a server assigns.

certification/server-assigned-fields.v1.json tells every certification runner
which response values not to compare. A path that resolves to nothing would be
a silent no-op, and a path that covers a value the client supplied would weaken
a semantic assertion. These checks keep the list exact.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ROOT / "certification" / "server-assigned-fields.v1.json"
FIXTURES = ROOT / "conformance" / "fixtures"
RESPONSES = {
    "FeatureService/ApplyEdits": "feature_apply_edits",
    "FormService/SubmitFormData": "form_submit",
    "ProcessService/ExecutePlan": "process_execute_plan",
    "WorkspaceService/CreateWorkspace": "workspace_create",
}


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

    def test_every_operation_has_a_response_fixture(self):
        self.assertEqual(set(RESPONSES), set(self.every))
        self.assertEqual(set(), set(self.optional) - set(RESPONSES))

    def test_no_path_is_both_required_and_optional(self):
        for operation, patterns in self.optional.items():
            self.assertEqual(set(), set(patterns) & set(self.operations.get(operation, [])))

    def test_every_path_selects_a_value_in_the_expected_response(self):
        for operation, patterns in self.every.items():
            response = json.loads((FIXTURES / f"{RESPONSES[operation]}_response.json").read_text(encoding="utf-8"))
            for pattern in patterns:
                with self.subTest(operation=operation, pattern=pattern):
                    self.assertTrue(resolve(response, pattern), f"{pattern} selects nothing")

    def test_no_path_covers_a_value_the_client_supplied(self):
        for operation, patterns in self.every.items():
            name = RESPONSES[operation]
            request = json.loads((FIXTURES / f"{name}_request.json").read_text(encoding="utf-8"))
            response = json.loads((FIXTURES / f"{name}_response.json").read_text(encoding="utf-8"))
            supplied = scalar_values(request)
            for pattern in patterns:
                for value in resolve(response, pattern):
                    with self.subTest(operation=operation, pattern=pattern, value=value):
                        self.assertNotIn(json.dumps(value), supplied)

    def test_query_features_is_compared_exactly(self):
        # Every QueryFeatures value is seeded or requested; none is server-assigned.
        self.assertNotIn("FeatureService/QueryFeatures", self.every)


if __name__ == "__main__":
    unittest.main()
