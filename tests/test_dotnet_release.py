from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pack_dotnet_release import version_from_tag


class DotnetReleaseTagTests(unittest.TestCase):
    def test_stable_and_prerelease_versions_come_from_tag(self):
        for version in ("1.0.1", "1.2.3-rc.1", "1.2.3-0.3a", "0.2.0-alpha.1"):
            with self.subTest(version=version):
                self.assertEqual(version, version_from_tag("v" + version))

    def test_noncanonical_or_colliding_coordinates_are_rejected(self):
        for tag in (
            "1.2.3", "v01.2.3", "v1.02.3", "v1.2.03", "v1.2", "v1.2.3.4",
            "v1.2.3-01", "v1.2.3-rc.01", "v1.2.3-", "v1.2.3+build.1",
            "v1.2.3\n", "refs/tags/v1.2.3", "v1.2.3;echo nope",
        ):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                version_from_tag(tag)


if __name__ == "__main__":
    unittest.main()
