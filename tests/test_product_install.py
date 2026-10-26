"""Product packaging: installer dry-run, help and no filesystem changes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts" / "install_scene2_menu.sh"
REMOVE = ROOT / "scripts" / "uninstall_scene2.sh"
UPDATE = ROOT / "scripts" / "update_scene2.sh"


class PackageInstallTest(unittest.TestCase):
    def test_help_is_safe_even_without_macos(self):
        for script in (INSTALL, REMOVE, UPDATE):
            out = subprocess.run(["bash", str(script), "--help"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("Usage", out.stdout)

    def test_update_unknown_option_is_non_mutating(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, HOME=temp)
            out = subprocess.run(["bash", str(UPDATE), "--unexpected"],
                                 env=env, capture_output=True, text=True)
            self.assertNotEqual(out.returncode, 0)
            self.assertEqual(list(Path(temp).iterdir()), [])

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
            # Simulate live workers: dry-run must never ask them to stop.
            fake_pgrep = bin_dir / "pgrep"
            fake_pgrep.write_text("#!/bin/sh\nexit 0\n")
            fake_pgrep.chmod(0o755)
            env = dict(os.environ,
                       HOME=str(home),
                       PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
                       NK_RESOLVE_PYTHON=os.environ.get("NK_RESOLVE_PYTHON", "/usr/bin/python3"))
            for script in (INSTALL, UPDATE):
                out = subprocess.run(["bash", str(script), "--dry-run"],
                                     env=env, capture_output=True, text=True)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertIn("NK_INSTALL=DRY_RUN", out.stdout)
                self.assertEqual(list(home.iterdir()), [])



    def test_updater_verifies_all_manifest_runtime_files(self):
        # The original updater compared only four of eight Python modules.
        # Force one of the other four to fail comparison after install;
        # the updater must refuse success, without needing macOS hardware.
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            mockbin = Path(temp) / "mockbin"
            home.mkdir()
            mockbin.mkdir()
            for name, body in {
                "uname": "#!/bin/sh\\necho Darwin\\n",
                "pgrep": "#!/bin/sh\\nexit 1\\n",
                "fakepython": (
                    '#!/bin/sh\\n'
                    'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then\\n'
                    '  mkdir -p "$3/bin"\\n'
                    '  cp "$0" "$3/bin/python3"\\n'
                    'fi\\n'
                    'exit 0\\n'
                ),
                "cmp": (
                    '#!/bin/sh\\n'
                    'case "$2" in *scene2_audio_roundtrip_probe.py) exit 1;; esac\\n'
                    'exec /usr/bin/cmp "$@"\\n'
                ),
            }.items():
                script = mockbin / name
                script.write_text(body.replace("\\\\n", "\\n"))
                script.chmod(0o755)
            env = dict(os.environ, HOME=str(home),
                       NK_RESOLVE_PYTHON=str(mockbin / "fakepython"),
                       PATH=str(mockbin) + os.pathsep + os.environ.get("PATH", ""))
            out = subprocess.run(["bash", str(UPDATE)], env=env,
                                 capture_output=True, text=True)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn(
                "verification failed: scene2_audio_roundtrip_probe.py",
                out.stderr)
            self.assertNotIn("NK_UPDATE=PASS", out.stdout)

    def test_install_restore_and_modified_file_protection(self):
        # Fake only macOS detection and Python dependency commands. Test
        # actual copying, manifest, hash guard and reversal in a temp HOME.
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            mockbin = Path(temp) / "mockbin"
            home.mkdir()
            mockbin.mkdir()
            uname = mockbin / "uname"
            uname.write_text("#!/bin/sh\necho Darwin\n")
            uname.chmod(0o755)
            python = mockbin / "fakepython"
            python.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then\n'
                '  mkdir -p "$3/bin"\n'
                '  cp "$0" "$3/bin/python3"\n'
                '  exit 0\n'
                'fi\n'
                'exit 0\n'
            )
            python.chmod(0o755)
            env = dict(os.environ, HOME=str(home),
                       NK_RESOLVE_PYTHON=str(python),
                       PATH=str(mockbin) + os.pathsep + os.environ.get("PATH", ""))
            hs = home / ".hammerspoon"
            hs.mkdir()
            original = "-- existing user config\nprint('keep me')\n"
            (hs / "init.lua").write_text(original)
            # Deliberately modified controller: must not be clobbered.
            (hs / "nanokontrol_resolve21.lua").write_text("-- custom controller\n")
            blocked = subprocess.run(["bash", str(INSTALL)],
                env=env, capture_output=True, text=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("modified", blocked.stderr.lower()) if "modified" in blocked.stderr.lower() else self.assertIn("differs", blocked.stderr)
            self.assertEqual((hs / "nanokontrol_resolve21.lua").read_text(),
                             "-- custom controller\n")
            ok = subprocess.run(["bash", str(INSTALL), "--force"],
                                env=env, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("NK_INSTALL=PASS", ok.stdout)
            self.assertIn("require(\"nanokontrol_resolve21\")",
                          (hs / "init.lua").read_text())
            base = home / "Library/Application Support/NK Scene2"
            self.assertTrue((base / "scripts/scene2_combined_bench.py").exists())
            self.assertEqual(
                (base / "scripts/fairlight_mcu_continuous.py").read_bytes(),
                (ROOT / "scripts/fairlight_mcu_continuous.py").read_bytes()
            )
            self.assertTrue((base / "active-backup").exists())
            active_backup = Path((base / "active-backup").read_text().strip())
            runtime_manifests = sorted((active_backup / "after").glob(
                "script-*.sha256"))
            self.assertEqual(len(runtime_manifests), 8)
            for manifest in runtime_manifests:
                name = manifest.name.removeprefix("script-").removesuffix(
                    ".sha256")
                self.assertEqual((base / "scripts" / name).read_bytes(),
                                 (ROOT / "scripts" / name).read_bytes())
            # Uninstall fails safely if the user changed any tracked file.
            (hs / "init.lua").write_text("-- changed after install\n")
            refused = subprocess.run(["bash", str(REMOVE)],
                env=env, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("user-modified", refused.stderr)
            # Restore the exact installed init.lua from the saved checksum.
            (hs / "init.lua").write_text(
                original + '\n-- Korg nanoKONTROL Studio / DaVinci Resolve\n'
                'require("nanokontrol_resolve21")\n')
            undone = subprocess.run(["bash", str(REMOVE)],
                env=env, capture_output=True, text=True)
            self.assertEqual(undone.returncode, 0, undone.stderr)
            self.assertIn("NK_UNINSTALL=PASS", undone.stdout)
            self.assertEqual((hs / "init.lua").read_text(), original)
            self.assertEqual((hs / "nanokontrol_resolve21.lua").read_text(),
                             "-- custom controller\n")
            self.assertFalse((hs / "scene2_session_menu.lua").exists())
            self.assertFalse((base / "active-backup").exists())
            self.assertTrue((base / "venv/bin/python3").exists())


if __name__ == "__main__":
    unittest.main()
