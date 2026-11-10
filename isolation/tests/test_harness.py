"""Fast harness checks. These do not claim Docker or cross-UID isolation."""
import errno
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from isolation import probe
from isolation.run import build_context, Harness, validate_container, validate_dac_mounts, validate_environment


def process(uid, suffix):
    return {"uid": uid, "gid": uid, "groups": [uid], "directory_uid": uid,
            "directory_mode": 0o700, "namespaces": {"pid": "pid" + suffix, "mnt": "mnt" + suffix, "net": "net1"},
            "cap_effective": "00000000", "cap_permitted": "00000000", "no_new_privs": "1", "seccomp": "2",
            "network_interfaces": ["lo"]}


def container():
    return {"Config": {"User": "21001:21001"}, "HostConfig": {
        "ReadonlyRootfs": True, "Privileged": False, "CapDrop": ["ALL"], "CapAdd": None,
        "SecurityOpt": ["no-new-privileges:true"], "NetworkMode": "container:anchor",
        "PortBindings": {}, "PidMode": "", "IpcMode": "private"},
        "Mounts": [{"Type": "volume", "Name": "atlas-data", "Destination": "/private/atlas", "RW": True}]}


class HarnessChecks(unittest.TestCase):
    def test_valid_environment(self):
        validate_environment(process(21001, "a"), process(21002, "b"))

    def test_environment_rejects_every_weakened_boundary(self):
        mutations = [("uid", 0), ("gid", 0), ("groups", [21001, 21002]), ("directory_uid", 21002),
                     ("directory_mode", 0o755), ("cap_effective", "1"), ("cap_permitted", "1"),
                     ("no_new_privs", "0"), ("seccomp", "0"), ("network_interfaces", ["lo", "eth0"])]
        for field, value in mutations:
            with self.subTest(field=field):
                info = process(21001, "a")
                info[field] = value
                with self.assertRaises(AssertionError):
                    validate_environment(info, process(21002, "b"))

    def test_shared_private_namespaces_and_wrong_carrier_rejected(self):
        for name in ("pid", "mnt", "net"):
            with self.subTest(name=name):
                first, second = process(21001, "a"), process(21002, "b")
                second["namespaces"][name] = first["namespaces"][name] if name != "net" else "external"
                with self.assertRaises(AssertionError):
                    validate_environment(first, second)

    def test_valid_container(self):
        validate_container(container(), "atlas", "atlas-data", "anchor")

    def test_unsafe_container_modes_rejected(self):
        for field, value in [("ReadonlyRootfs", False), ("Privileged", True), ("CapDrop", []),
                             ("CapAdd", ["SYS_ADMIN"]), ("Devices", ["device"]),
                             ("DeviceRequests", ["gpu"]), ("SecurityOpt", []), ("NetworkMode", "host"),
                             ("PortBindings", {"8765/tcp": []}), ("PublishAllPorts", True),
                             ("PidMode", "host"), ("IpcMode", "host")]:
            with self.subTest(field=field):
                value_info = container()
                value_info["HostConfig"][field] = value
                with self.assertRaises(AssertionError):
                    validate_container(value_info, "atlas", "atlas-data", "anchor")

    def test_peer_mount_and_bind_mount_rejected(self):
        for mount in ({"Type": "volume", "Name": "beacon-data", "Destination": "/private/beacon", "RW": True},
                      {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock"}):
            info = container()
            info["Mounts"].append(mount)
            with self.assertRaises(AssertionError):
                validate_container(info, "atlas", "atlas-data", "anchor")

    def test_wrong_or_missing_own_volume_rejected(self):
        for change in ({"Name": "beacon-data"}, {"Destination": "/elsewhere"}, {"RW": False}):
            info = container()
            info["Mounts"][0].update(change)
            with self.assertRaises(AssertionError):
                validate_container(info, "atlas", "atlas-data", "anchor")

    def test_dac_probe_requires_both_actual_writable_volumes(self):
        info = container()
        volumes = {"atlas": "atlas-data", "beacon": "beacon-data"}
        with self.assertRaises(AssertionError):
            validate_dac_mounts(info, "atlas", "beacon", volumes)
        info["Mounts"].append({"Type": "volume", "Name": "beacon-data", "Destination": "/private/beacon", "RW": True})
        validate_dac_mounts(info, "atlas", "beacon", volumes)
        for name, value in (("Name", "unrelated-volume"), ("RW", False), ("Type", "bind")):
            with self.subTest(name=name):
                old = info["Mounts"][1][name]
                info["Mounts"][1][name] = value
                with self.assertRaises(AssertionError):
                    validate_dac_mounts(info, "atlas", "beacon", volumes)
                info["Mounts"][1][name] = old

    def test_probe_success_is_not_misreported_as_denial(self):
        with self.assertRaises(AssertionError):
            probe.denied(lambda: None)

    def test_only_expected_errors_count_as_denial(self):
        def error(number):
            raise OSError(number, "synthetic")
        for number in (errno.EACCES, errno.EPERM, errno.ENOENT, errno.EROFS):
            self.assertEqual(probe.denied(lambda: error(number)), errno.errorcode[number])
        for number in (errno.EIO, errno.EMFILE, errno.ENOSPC, errno.EXDEV):
            with self.assertRaises(AssertionError):
                probe.denied(lambda: error(number))

    def test_sensitive_input_and_container_output_not_in_diagnostics(self):
        fake = type("Result", (), {"returncode": 1, "stdout": "SECRET output", "stderr": "SECRET stderr"})()
        with patch("subprocess.run", return_value=fake):
            with self.assertRaises(RuntimeError) as raised:
                Harness().docker("exec", "fixture", data="SECRET input")
        self.assertNotIn("SECRET", str(raised.exception))

    def test_missing_docker_fails_instead_of_skipping(self):
        with patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "no isolation test ran"):
                Harness().prepare()

    def test_cleanup_ignores_objects_never_created(self):
        harness = Harness()
        harness.containers = [harness.name("attempted")]
        harness.volumes = [harness.name("attempted-data")]
        with patch.object(harness, "docker", return_value="") as docker:
            harness.cleanup()
        self.assertEqual([call.args[0] for call in docker.call_args_list], ["ps", "volume"])

    def test_cleanup_never_deletes_untracked_resources(self):
        harness = Harness()
        harness.containers = [harness.name("owned")]
        harness.volumes = [harness.name("owned-data")]
        with patch.object(harness, "docker", side_effect=[harness.name("owned") + "\nnot-ours\n",
                                                         harness.name("owned-data") + "\nother-volume\n", "", ""]) as docker:
            harness.cleanup()
        deletes = [call.args for call in docker.call_args_list[2:]]
        self.assertEqual(deletes, [("rm", "--force", harness.name("owned")),
                                   ("volume", "rm", harness.name("owned-data"))])

    def test_restart_checks_live_listeners_before_reusing_ports(self):
        harness = Harness()
        with patch.object(harness, "docker") as docker, patch.object(harness, "probe", side_effect=[False, False, False, True, True]), \
                patch("time.sleep") as sleep:
            harness.restart()
        self.assertEqual([call.args for call in docker.call_args_list], [
            ("stop", harness.name("atlas")), ("stop", harness.name("beacon")),
            ("start", harness.name("atlas")), ("start", harness.name("beacon"))])
        sleep.assert_called_once_with(1)

    def test_restart_fails_closed_when_port_never_becomes_available(self):
        harness = Harness()
        with patch.object(harness, "docker") as docker, patch.object(harness, "probe", return_value=False), \
                patch("time.monotonic", side_effect=[0, 16]):
            with self.assertRaisesRegex(RuntimeError, "ports remain occupied"):
                harness.restart()
        self.assertEqual([call.args[0] for call in docker.call_args_list], ["stop", "stop"])

    def test_restart_fails_if_probe_can_rebind_a_live_listener(self):
        harness = Harness()
        with patch.object(harness, "docker") as docker, patch.object(harness, "probe", return_value=True):
            with self.assertRaisesRegex(AssertionError, "live pilot listener could be rebound"):
                harness.restart()
        docker.assert_not_called()

    def test_port_probe_distinguishes_occupied_from_unrelated_errors(self):
        for number in (errno.EADDRINUSE, errno.EACCES, errno.EADDRNOTAVAIL):
            listener = MagicMock()
            listener.__enter__.return_value = listener
            listener.bind.side_effect = OSError(number, "synthetic")
            with self.subTest(number=number), patch("socket.socket", return_value=listener):
                if number == errno.EADDRINUSE:
                    self.assertFalse(probe.main({"operation": "port_available", "port": 8765}))
                else:
                    with self.assertRaises(OSError):
                        probe.main({"operation": "port_available", "port": 8765})
                listener.setsockopt.assert_called_once_with(probe.socket.SOL_SOCKET, probe.socket.SO_REUSEADDR, 1)

    def test_build_context_is_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "context.tar"
            build_context(target)
            self.assertEqual(target.read_bytes()[:2], b"\x1f\x8b")
            with tarfile.open(target) as archive:
                names = archive.getnames()
            self.assertIn("pilot/server.py", names)
            self.assertIn("pilot/requirements.txt", names)
            self.assertIn("isolation/probe.py", names)
            self.assertNotIn("isolation/run.py", names)
            self.assertTrue(all(name == "Dockerfile" or name.startswith(("pilot/", "isolation/")) for name in names))
            self.assertFalse(any(".git" in name or name.endswith(".sqlite") for name in names))

    def test_snapshot_detects_contents_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canary"
            path.write_text("before")
            before = probe.snapshot(directory)
            path.write_text("after")
            self.assertNotEqual(before, probe.snapshot(directory))
            before = probe.snapshot(directory)
            path.chmod(0o400)
            self.assertNotEqual(before, probe.snapshot(directory))


if __name__ == "__main__":
    unittest.main()
