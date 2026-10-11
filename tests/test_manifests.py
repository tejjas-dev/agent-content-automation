import json
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # CI installs pyyaml; locally skip
    yaml = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(yaml is None, "pyyaml missing")
class TestManifests(unittest.TestCase):
    def test_skill_frontmatter_is_valid_yaml_and_matches_folder(self):
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(len(skills), 8)
        for p in skills:
            fm = yaml.safe_load(p.read_text(encoding="utf-8").split("---")[1])
            self.assertEqual(fm["name"], p.parent.name)
            self.assertGreater(len(fm["description"]), 40)

    def test_plugin_manifests(self):
        y = yaml.safe_load((ROOT / "plugin.yaml").read_text())
        self.assertEqual(y["name"], "devx-content")
        self.assertEqual({e["name"] for e in y["requires_env"]}, {"AROLINKS_TOKEN", "TELEGRAM_BOT_TOKEN", "DRAMA_POST_CHANNEL_IDS"})
        versions = {y["version"]}
        for f in (".claude-plugin/plugin.json", "gemini-extension.json"):
            versions.add(json.loads((ROOT / f).read_text())["version"])
        self.assertEqual(len(versions), 1, f"version mismatch {versions}")
        json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())


if __name__ == "__main__":
    unittest.main()
