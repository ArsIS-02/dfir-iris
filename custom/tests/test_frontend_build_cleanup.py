from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "frontend" / "build.sh"


class FrontendBuildCleanupTests(unittest.TestCase):
    def test_build_script_has_valid_bash_syntax(self):
        subprocess.run(["bash", "-n", str(BUILD_SCRIPT)], check=True)

    def test_build_cleans_only_new_storage_containers(self):
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("BUILD_CONTAINERS_BEFORE=$(storage_container_ids | sort)", script)
        self.assertIn("trap cleanup EXIT", script)
        self.assertIn("comm -13", script)
        self.assertIn("xargs -r podman rm -f", script)
        self.assertIn("podman build --force-rm --tag", script)
        self.assertNotIn("buildah rm --all", script)
        self.assertNotIn("podman container prune", script)
        self.assertNotIn("podman system prune", script)
        self.assertNotIn("podman volume prune", script)


if __name__ == "__main__":
    unittest.main()
