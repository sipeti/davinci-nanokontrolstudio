"""Product packaging: installer dry-run, help and no filesystem changes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts" / "install_scene2_menu.sh"
REMOVE = ROOT / "scripts" / "uninstall_scene2.sh"


class PackageInstallTest(unittest.TestCase):
    def test_help_is_safe_even_without_macos(self):
        for script in (INSTALL, REMOVE):
            out = subprocess.run(["bash", str(script), "--help"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("Usage", out.stdout)

    def test_unknown_option_rejected_without_modifying_home(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, HOME=temp)
            out = subprocess.run(["bash", str(INSTALL), "--not-supported"],
                                 env=env, capture_output=True, text=True)
            self.assertNotEqual(out.returncode, 0)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_dry_run_never_creates_hammerspoon_or_venv(self):
        # CI runs on Linux. Stub uname for only this process, so the macOS
        # preflight can execute. This never invokes a real installer.
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            bin_dir = Path(temp) / "bin"
            home.mkdir()
            bin_dir.mkdir()
            fake_uname = bin_dir / "uname"
            fake_uname.write_text("#!/bin/sh\necho Darwin\n")
            fake_uname.chmod(0o755)
            env = dict(os.environ,
                       HOME=str(home),
                       PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
                       NK_RESOLVE_PYTHON=os.environ.get("NK_RESOLVE_PYTHON", "/usr/bin/python3"))
            out = subprocess.run(["bash", str(INSTALL), "--dry-run"],
                                 env=env, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("NK_INSTALL=DRY_RUN", out.stdout)
            self.assertEqual(list(home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
