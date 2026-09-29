"""Every non-default value a conformance fixture sets must survive the schema.

conformance/run.sh round-trips each fixture through ``buf convert`` and compares
the canonical JSON with its committed golden. ``buf convert`` silently drops
JSON keys the schema does not define, so a fixture that nests a field under a
non-existent key still converts, and ``--update`` writes a golden that has
quietly lost the value. That hid ``defaultRetention.ref`` in the CreateWorkspace
fixtures: ``RetentionPolicyRef`` has no ``ref`` field, and every generated
client rejected the fixture before a request was sent.

This test needs no toolchain. The golden is the schema's own canonical
rendering of the fixture, so any non-default fixture value with no
counterpart in the golden was dropped by the schema.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "conformance" / "fixtures"
GOLDEN = ROOT / "conformance" / "golden"
MANIFEST = FIXTURES / "manifest.txt"


def _manifest_fixtures() -> list[str]:
    names = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line.split()[0])
    return names


PROTOS = ROOT / "geospatial" / "v1"
_FIELD_RE = re.compile(
    r"^\s*(?:optional\s+|repeated\s+)?(?:map\s*<[^>]+>|[\w.]+)\s+(\w+)\s*=\s*\d+",
    re.MULTILINE,
)


def _schema_field_names() -> frozenset[str]:
    """Every field name the schema defines, in proto and JSON (lowerCamel) spelling."""
    names: set[str] = set()
    for proto in PROTOS.glob("*.proto"):
        for name in _FIELD_RE.findall(proto.read_text(encoding="utf-8")):
            names.add(name)
            names.add(_camel(name))
    return frozenset(names)


def _camel(name: str) -> str:
    return re.sub(r"_([a-z0-9])", lambda match: match.group(1).upper(), name)


def _is_proto3_default(value: object) -> bool:
    """True when the canonical proto3 JSON mapping would omit this value."""
    if value is None or value is False or value == "" or value == [] or value == {}:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0:
        return True
    if isinstance(value, str) and (value == "0" or value.endswith("_UNSPECIFIED")):
        return True
    if isinstance(value, dict):
        return all(_is_proto3_default(item) for item in value.values())
    return False


def dropped_paths(fixture: object, golden: object, path: str = "$") -> list[str]:
    """Paths of non-default fixture values that have no counterpart in golden."""
    if isinstance(fixture, dict):
        if not isinstance(golden, dict):
            return [] if _is_proto3_default(fixture) else [path]
        missing = []
        for key, value in fixture.items():
            child = f"{path}.{key}"
            if key in golden:
                missing += dropped_paths(value, golden[key], child)
            elif _camel(key) in golden:
                missing += dropped_paths(value, golden[_camel(key)], child)
            elif key not in SCHEMA_FIELDS or not _is_proto3_default(value):
                # A key the schema does not define is always a defect, even
                # when its value looks like a proto3 default (e.g. "0" in a
                # misspelled string field). Only a real field may be omitted.
                missing.append(child)
        return missing
    if isinstance(fixture, list):
        if not isinstance(golden, list):
            return [] if _is_proto3_default(fixture) else [path]
        missing = []
        for index, value in enumerate(fixture):
            if index < len(golden):
                missing += dropped_paths(value, golden[index], f"{path}[{index}]")
            elif not _is_proto3_default(value):
                missing.append(f"{path}[{index}]")
        return missing
    return []


SCHEMA_FIELDS = _schema_field_names()


class ConformanceFixtureSchemaTests(unittest.TestCase):
    def test_unknown_key_is_reported_even_with_a_default_looking_value(self):
        self.assertIn("retentionPolicyId", SCHEMA_FIELDS)
        self.assertEqual(["$.scopeTokn"], dropped_paths({"scopeTokn": "0"}, {}))
        self.assertEqual(["$.retentionPolicyIdd"], dropped_paths({"retentionPolicyIdd": ""}, {}))
        # A real field left at its proto3 default is legitimately omitted.
        self.assertEqual([], dropped_paths({"retentionPolicyId": ""}, {}))


    def test_no_fixture_value_is_silently_dropped_by_the_schema(self):
        names = _manifest_fixtures()
        self.assertGreater(len(names), 0)
        for name in names:
            with self.subTest(fixture=name):
                fixture = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
                golden = json.loads((GOLDEN / name).read_text(encoding="utf-8"))
                self.assertEqual([], dropped_paths(fixture, golden))

    def test_detects_a_value_nested_under_an_unknown_key(self):
        # The pre-fix CreateWorkspace shape: RetentionPolicyRef has no `ref`.
        fixture = {"desired": {"defaultRetention": {"ref": {"retentionPolicyId": "standard-30d"}}}}
        golden = {"desired": {"defaultRetention": {}}}
        self.assertEqual(["$.desired.defaultRetention.ref"], dropped_paths(fixture, golden))

    def test_proto3_defaults_and_snake_case_names_are_not_reported(self):
        fixture = {
            "usage": {"usedBytes": "0", "bytesAvailable": "10"},
            "geometry_type": "GEOMETRY_TYPE_UNSPECIFIED",
            "retention_policy_id": "standard-30d",
            "labels": {"requested_by": "analyst-3"},
        }
        golden = {
            "usage": {"bytesAvailable": "10"},
            "retentionPolicyId": "standard-30d",
            "labels": {"requested_by": "analyst-3"},
        }
        self.assertEqual([], dropped_paths(fixture, golden))

    def test_workspace_fixtures_bind_the_retention_policy(self):
        request = json.loads((GOLDEN / "workspace_create_request.json").read_text(encoding="utf-8"))
        response = json.loads((GOLDEN / "workspace_create_response.json").read_text(encoding="utf-8"))
        self.assertEqual({"retentionPolicyId": "standard-30d"}, request["desired"]["defaultRetention"])
        self.assertEqual({"retentionPolicyId": "standard-30d"}, response["workspace"]["defaultRetention"])


if __name__ == "__main__":
    unittest.main()
