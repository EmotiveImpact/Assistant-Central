import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent


class CliTests(unittest.TestCase):
    def run_demo(self, directory, *args, input=None):
        result = subprocess.run([sys.executable, "demo.py", "--state-directory", directory, *args],
                                input=input, capture_output=True, text=True, cwd=ROOT, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_pause_resume_and_repeated_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            out = self.run_demo(directory, "--simulate", "--stop-after", "5")
            self.assertIn("Paused after 5", out)
            out = self.run_demo(directory, "--simulate", "--resume")
            self.assertIn("All four accepted: True", out)
            self.assertIn("Audit events: 12", out)
            out = self.run_demo(directory, "--simulate", "--resume")
            self.assertIn("No messages replayed", out)
            with sqlite3.connect(pathlib.Path(directory) / "demo.sqlite3") as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM transitions").fetchone()[0], 12)

    def test_pairing_denial_sends_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            out = self.run_demo(directory, input="NO\n")
            self.assertIn("Pairing denied", out)
            with sqlite3.connect(pathlib.Path(directory) / "demo.sqlite3") as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 0)

    def test_existing_state_requires_explicit_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_demo(directory, "--simulate", "--stop-after", "1")
            out = self.run_demo(directory, "--simulate")
            self.assertIn("Existing state preserved", out)

    def test_simulated_approvals_cannot_become_manual_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_demo(directory, "--simulate", "--stop-after", "1")
            out = self.run_demo(directory, "--resume", input="NO\n")
            self.assertIn("Approval provenance differs", out)

    def test_pause_requires_durable_directory(self):
        result = subprocess.run([sys.executable, "demo.py", "--simulate", "--stop-after", "1"],
                                capture_output=True, text=True, cwd=ROOT, timeout=10)
        self.assertIn("Stop-after requires a state directory", result.stdout)

    def test_simulated_cancel_stops_resume_and_preserves_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_demo(directory, "--simulate", "--stop-after", "5")
            out = self.run_demo(directory, "--simulate", "--resume", "--cancel-as", "bob")
            self.assertIn("Meeting cancelled by bob", out)
            self.assertIn("No messages sent", out)
            out = self.run_demo(directory, "--simulate", "--resume")
            self.assertIn("This session is cancelled", out)
            out = self.run_demo(directory, "--simulate", "--resume", "--cancel-as", "dana")
            self.assertIn("Meeting cancelled by bob", out)
            with sqlite3.connect(pathlib.Path(directory) / "demo.sqlite3") as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM transitions").fetchone()[0], 5)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM cancellations").fetchone()[0], 1)

    def test_manual_cancel_requires_exact_phrase(self):
        with tempfile.TemporaryDirectory() as directory:
            pairs = ["PAIR alice WITH alice FOR friday-four"]
            for person in ("bob", "charlie", "dana"):
                pairs += [f"PAIR {person} WITH alice FOR friday-four", f"PAIR alice WITH {person} FOR friday-four"]
            initial = "\n".join(pairs + ["APPROVE alice availability TO alice", ""])
            out = self.run_demo(directory, "--stop-after", "1", input=initial)
            self.assertIn("Paused after 1", out)
            out = self.run_demo(directory, "--resume", "--cancel-as", "bob", input="NO\n")
            self.assertIn("Cancellation denied", out)
            with sqlite3.connect(pathlib.Path(directory) / "demo.sqlite3") as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM cancellations").fetchone()[0], 0)
            out = self.run_demo(directory, "--resume", "--cancel-as", "bob", input="CANCEL friday-four AS bob\n")
            self.assertIn("Meeting cancelled by bob", out)
            with sqlite3.connect(pathlib.Path(directory) / "demo.sqlite3") as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM transitions").fetchone()[0], 1)

    def test_cancel_cannot_relabel_simulated_approval_as_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_demo(directory, "--simulate", "--stop-after", "1")
            out = self.run_demo(directory, "--resume", "--cancel-as", "bob", input="CANCEL friday-four AS bob\n")
            self.assertIn("Approval provenance differs", out)

    def test_cancel_requires_existing_session_and_no_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            out = self.run_demo(directory, "--simulate", "--cancel-as", "bob")
            self.assertIn("Cancellation requires --resume", out)
            out = self.run_demo(directory, "--simulate", "--resume", "--cancel-as", "bob")
            self.assertIn("No session exists to resume", out)
            out = self.run_demo(directory, "--simulate", "--resume", "--cancel-as", "bob", "--stop-after", "1")
            self.assertIn("Cancellation cannot be combined", out)
