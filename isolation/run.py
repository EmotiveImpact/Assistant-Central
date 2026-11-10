"""Run the unchanged pilot behind real container and Unix-ownership boundaries.

Requires an already authorized Docker engine. Never installs an engine, invokes
sudo, changes host security settings, or falls back to same-UID subprocesses.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OWNERS = {"atlas": {"uid": 21001, "port": 8765}, "beacon": {"uid": 21002, "port": 8766}}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def validate_environment(first, second):
    for owner, info in zip(OWNERS, (first, second)):
        uid = OWNERS[owner]["uid"]
        require(info["uid"] == info["gid"] == info["directory_uid"] == uid, "Wrong owner identity")
        require(set(info["groups"]) <= {uid}, "Unexpected supplementary groups")
        require(info["directory_mode"] == 0o700, "Owner directory is not private")
        require(int(info["cap_effective"], 16) == int(info["cap_permitted"], 16) == 0,
                "Process retained Linux capabilities")
        require(info["no_new_privs"] == "1" and info["seccomp"] == "2", "Security profile missing")
        require(info["network_interfaces"] == ["lo"], "Unexpected external network interface")
    for namespace in ("pid", "mnt"):
        require(first["namespaces"][namespace] != second["namespaces"][namespace], "Shared private namespace")
    require(first["namespaces"]["net"] == second["namespaces"]["net"], "Loopback carrier is not shared")


def validate_container(info, owner, volume, anchor_id):
    config, host = info["Config"], info["HostConfig"]
    uid = OWNERS[owner]["uid"]
    require(config["User"] == f"{uid}:{uid}", "Wrong container user")
    require(host["ReadonlyRootfs"] is True and host["Privileged"] is False, "Unsafe filesystem/privilege mode")
    require({str(cap).upper() for cap in host["CapDrop"]} == {"ALL"}, "Capabilities not dropped")
    require(not host.get("CapAdd") and not host.get("Devices") and not host.get("DeviceRequests"),
            "Unexpected capabilities/devices")
    require(any(option in ("no-new-privileges", "no-new-privileges:true") for option in host["SecurityOpt"]),
            "Privilege escalation not disabled")
    require(host["NetworkMode"] == "container:" + anchor_id, "Unexpected network namespace")
    require(not host.get("PortBindings") and not host.get("PublishAllPorts"), "Host ports exposed")
    require(host.get("PidMode", "") == "" and host.get("IpcMode") == "private", "Shared process/IPC namespace")
    mounts = [mount for mount in info["Mounts"] if mount["Type"] != "tmpfs"]
    require(len(mounts) == 1 and mounts[0]["Type"] == "volume" and mounts[0]["Name"] == volume
            and mounts[0]["Destination"] == "/private/" + owner and mounts[0]["RW"] is True,
            "Owner has unexpected storage mounts")


def validate_dac_mounts(info, attacker, victim, volumes):
    require(info["Config"]["User"] == f"{OWNERS[attacker]['uid']}:{OWNERS[attacker]['uid']}",
            "DAC probe has the wrong user")
    mounts = [mount for mount in info["Mounts"] if mount["Type"] != "tmpfs"]
    require(len(mounts) == 2, "DAC probe must mount both actual owner volumes")
    for owner in (attacker, victim):
        require(any(mount["Type"] == "volume" and mount["Name"] == volumes[owner]
                    and mount["Destination"] == "/private/" + owner and mount["RW"] is True for mount in mounts),
                "DAC probe is not testing the actual writable owner volume")


def build_context(destination):
    # Never send the whole checkout, .git, credentials, or untracked owner stores
    # to the Docker daemon. Only versioned pilot code and our explicit helpers.
    tracked = subprocess.run(["git", "ls-files", "pilot"], cwd=ROOT, check=True,
                             stdout=subprocess.PIPE, text=True).stdout.splitlines()
    files = [name for name in tracked if (Path(name).suffix in (".py", ".mjs", ".html", ".css")
                                         or name == "pilot/requirements.txt")]
    files += ["isolation/__init__.py", "isolation/probe.py"]
    # gzip has an unambiguous magic header. Some Docker/BuildKit versions treat
    # an uncompressed Python PAX archive on stdin as a plain-text Dockerfile.
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(ROOT / "isolation/Dockerfile", arcname="Dockerfile", recursive=False)
        for name in files:
            path = ROOT / name
            require(path.is_file() and not path.is_symlink(), "Build input is not a regular file")
            archive.add(path, arcname=name, recursive=False)


class Harness:
    def __init__(self):
        self.prefix = "ac-isolation-" + secrets.token_hex(6)
        self.image = self.prefix + ":test"
        self.containers, self.volumes = [], []
        self.anchor_id = None
        self.build_started = False

    def docker(self, *args, data=None, timeout=60):
        try:
            result = subprocess.run(["docker", *args], input=data, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=timeout, text=True)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise RuntimeError("Docker unavailable or operation timed out: " + args[0]) from None
        if result.returncode:
            # stdin may contain synthetic credentials. Never print it or output
            # from an arbitrary container command on an error path.
            raise RuntimeError("Docker operation failed: " + args[0] + " (exit " + str(result.returncode) + ")")
        return result.stdout + result.stderr if args[0] == "logs" else result.stdout

    def prepare(self):
        if shutil.which("docker") is None:
            raise RuntimeError("Docker CLI is required; no isolation test ran. Use an authorized Docker engine or the CI job.")
        self.docker("info", "--format", "{{.ServerVersion}}")
        with tempfile.TemporaryDirectory(prefix=self.prefix) as temporary:
            archive = Path(temporary) / "context.tar.gz"
            build_context(archive)
            with archive.open("rb") as stream:
                self.build_started = True
                result = subprocess.run(["docker", "build", "--tag", self.image, "-"], stdin=stream,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
            if result.returncode:
                # Build context has no owner credentials or untracked files.
                print(result.stdout.decode("utf-8", errors="replace")[-4000:], file=sys.stderr)
                raise RuntimeError("Docker image build failed. Check registry access and pilot/requirements.txt.")
        self.start("network", 21003, network="none")
        self.anchor_id = self.inspect("network")["Id"]
        require(self.inspect("network")["HostConfig"]["NetworkMode"] == "none", "Anchor has external networking")
        self.start("controller", 21003)

    def name(self, role):
        return self.prefix + "-" + role

    def start(self, role, uid, *, network=None, mounts=(), command=()):
        name = self.name(role)
        self.containers.append(name)
        args = ["run", "--detach", "--name", name, "--label", "assistant-central.isolation=" + self.prefix,
                "--user", f"{uid}:{uid}", "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true", "--ipc=private", "--pids-limit=64",
                "--memory=256m", "--cpus=1", "--network", network or "container:" + self.anchor_id,
                "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size=16m,mode=700,uid={uid},gid={uid}"]
        for owner in mounts:
            args += ["--mount", "type=volume,source=" + self.name(owner + "-data") + ",target=/private/" + owner]
        self.docker(*args, self.image, *command)

    def inspect(self, role):
        return json.loads(self.docker("inspect", self.name(role)))[0]

    def probe(self, role, operation, **values):
        try:
            return json.loads(self.docker("exec", "-i", self.name(role), "python", "-B", "-m", "isolation.probe",
                                          data=json.dumps({"operation": operation, **values})))
        except RuntimeError as exc:
            raise RuntimeError("Container helper " + role + "/" + operation + " failed: " + str(exc)) from None

    def provision(self, owner, password):
        volume = self.name(owner + "-data")
        self.volumes.append(volume)
        self.docker("volume", "create", "--label", "assistant-central.isolation=" + self.prefix, volume)
        role = "init-" + owner
        self.start(role, OWNERS[owner]["uid"], network="none", mounts=(owner,))
        result = self.probe(role, "provision", directory="/private/" + owner,
                            owner="fictional-" + owner, agent=owner, password=password)
        self.docker("rm", "--force", self.name(role))
        self.containers.remove(self.name(role))
        self.start(owner, OWNERS[owner]["uid"], mounts=(owner,), command=(
            "python", "-B", "-m", "pilot.server", "serve", "--directory", "/private/" + owner,
            "--port", str(OWNERS[owner]["port"])))
        return result

    def wait_ready(self, owner):
        for _ in range(100):
            info = self.inspect(owner)
            if not info["State"]["Running"]:
                logs = self.docker("logs", "--tail", "40", self.name(owner))
                # Only exception class and source location, never raw exception
                # details or log content, enter failure evidence.
                types = re.findall(r"^([A-Za-z_.]*(?:Error|Exception)):", logs, re.MULTILINE)
                frames = re.findall(r'File "(/app/(?:pilot|isolation)/[\w/]+\.py)", line (\d+)', logs)
                reason = ", ".join(path + ":" + line for path, line in frames[-3:])
                raise RuntimeError("Pilot " + owner + " exited before readiness (exit=" + str(info["State"]["ExitCode"])
                                   + ", OOM=" + str(info["State"].get("OOMKilled", False)) + ") "
                                   + ",".join(types) + " " + reason)
            lines = self.docker("logs", self.name(owner)).splitlines()
            if lines:
                ready = json.loads(lines[-1])
                require(ready["url"] == "http://127.0.0.1:" + str(OWNERS[owner]["port"]), "Unexpected listener")
                require(ready["live_provider_enabled"] is False, "Live provider enabled")
                try:
                    self.request(owner, "GET", "/api/state", expected=401)
                    return
                except RuntimeError:
                    pass  # Read-only readiness probe, including after restart.
            time.sleep(0.1)
        raise RuntimeError("Pilot did not become ready")

    def request(self, owner, method, path, body=None, token=None, expected=200):
        response = self.probe("controller", "request", port=OWNERS[owner]["port"],
                              method=method, path=path, body=body, token=token)
        require(response["status"] == expected, method + " " + path + " returned " + str(response["status"]))
        return response["body"]

    def boundaries(self):
        observed, counts = {}, {}
        for owner in OWNERS:
            observed[owner] = self.probe(owner, "environment", directory="/private/" + owner)
            validate_container(self.inspect(owner), owner, self.name(owner + "-data"), self.anchor_id)
        validate_environment(observed["atlas"], observed["beacon"])
        for attacker, victim in (("atlas", "beacon"), ("beacon", "atlas")):
            before = self.probe(victim, "snapshot", directory="/private/" + victim)
            require("canary.txt" in before and "runtime.sqlite" in before and len(before) >= 4,
                    "Victim fixture is incomplete")
            values = {"uid": OWNERS[attacker]["uid"], "own": "/private/" + attacker,
                      "peer": "/private/" + victim, "peer_files": list(before)}
            normal = self.probe(attacker, "boundary", **values)
            # Deliberate *separate* diagnostic: the peer volume really is present,
            # but the attacker's UID still must not access it. Never a pilot role.
            role = "dac-" + attacker
            self.start(role, OWNERS[attacker]["uid"], network="none", mounts=(attacker, victim))
            try:
                validate_dac_mounts(self.inspect(role), attacker, victim,
                                    {owner: self.name(owner + "-data") for owner in OWNERS})
                dac = self.probe(role, "boundary", **values)
                require(all(value in ("EACCES", "EPERM") for key, value in dac.items()
                            if key not in ("modify_code", "replace_peer")),
                        "DAC test did not encounter a real permission boundary")
            finally:
                original = sys.exc_info()[1]
                try:
                    self.docker("rm", "--force", self.name(role))
                except RuntimeError as cleanup_error:
                    if original is not None:
                        raise RuntimeError(str(original) + "; " + str(cleanup_error)) from None
                    raise
                self.containers.remove(self.name(role))
            after = self.probe(victim, "snapshot", directory="/private/" + victim)
            require(before == after, "Victim private bytes, modes or ownership changed")
            counts[attacker] = {"deployment_denials": len(normal), "actual_peer_volume_dac_denials": len(dac)}
        return {"distinct_nonroot_uids": [21001, 21002], "separate_mount_and_pid_namespaces": True,
                "shared_network_namespace": "dedicated loopback only, no external interface or published port",
                "boundary_probes": counts, "victim_files_unchanged": True}

    def cleanup(self):
        failures = []
        # List labeled resources first: failed/uncertain creates are tracked, but
        # an object that was never created is not a cleanup failure.
        existing_containers, existing_volumes = set(), set()
        if self.containers or self.volumes:
            try:
                label = "label=assistant-central.isolation=" + self.prefix
                existing_containers = set(self.docker("ps", "--all", "--filter", label, "--format", "{{.Names}}").splitlines())
                existing_volumes = set(self.docker("volume", "ls", "--filter", label, "--format", "{{.Name}}").splitlines())
            except RuntimeError:
                raise RuntimeError("Cleanup state unknown; inspect test label assistant-central.isolation=" + self.prefix) from None
        for name in reversed(self.containers):
            if name not in existing_containers:
                continue
            try:
                self.docker("rm", "--force", name)
            except RuntimeError:
                failures.append(name)
        for volume in self.volumes:
            if volume not in existing_volumes:
                continue
            try:
                self.docker("volume", "rm", volume)
            except RuntimeError:
                failures.append(volume)
        if self.build_started:
            try:
                tags = self.docker("image", "ls", "--format", "{{.Repository}}:{{.Tag}}").splitlines()
                if self.image in tags:
                    # Removing our unique tag does not delete shared base layers.
                    self.docker("image", "rm", self.image)
            except RuntimeError:
                failures.append(self.image)
        if failures:
            raise RuntimeError("Cleanup incomplete; inspect only these test resources: " + ", ".join(failures))


def exchange(harness, passwords, identities):
    tokens = {owner: harness.request(owner, "POST", "/api/session", {"password": passwords[owner]})["token"]
              for owner in OWNERS}
    for owner, peer in (("atlas", "beacon"), ("beacon", "atlas")):
        # A valid owner credential is not an authorization at the other assistant.
        harness.request(peer, "GET", "/api/state", token=tokens[owner], expected=401)
        harness.request(peer, "POST", "/api/session", {"password": passwords[owner]}, expected=401)
        harness.request(owner, "POST", "/api/peers", {
            "public_identity": identities[peer]["identity"], "expected_fingerprint": identities[peer]["fingerprint"],
            "endpoint": "http://127.0.0.1:" + str(OWNERS[peer]["port"])}, tokens[owner])

    def state(owner):
        return harness.request(owner, "GET", "/api/state", token=tokens[owner])

    def sync():
        for owner in ("atlas", "beacon", "atlas", "beacon"):
            harness.request(owner, "POST", "/api/exchange", {}, tokens[owner])

    def action(owner, item, verb, decision=None):
        review = harness.request(owner, "GET", "/api/items/" + item + "/review", token=tokens[owner])
        body = {"review_digest": review["review_digest"]}
        if decision:
            body["decision"] = decision
        return harness.request(owner, "POST", "/api/items/" + item + "/" + verb, body, tokens[owner])

    context = hashlib.sha256(b"SYNTHETIC container-isolation task").hexdigest()
    body = {"peer_id": identities["beacon"]["fingerprint"], "kind": "task", "title": "Isolation test",
            "text": "SYNTHETIC ONLY: Return a fictional garden greeting.", "context": context,
            "task_id": "isolation-test", "expires": time.time() + 900}
    task = harness.request("atlas", "POST", "/api/proposals", body, tokens["atlas"])["id"]
    sync()
    require(not state("beacon")["items"], "Unreleased task crossed boundary")
    action("atlas", task, "release")
    sync()
    require(state("beacon")["items"][0]["state"] == "pending", "Transport receipt became owner acceptance")
    action("beacon", task, "decision", "accept")
    sync()
    require(state("atlas")["items"][0]["state"] == "accepted", "Signed decision did not reach requester")
    artifact = harness.request("beacon", "POST", "/api/proposals", {
        **body, "peer_id": identities["atlas"]["fingerprint"], "kind": "artifact", "parent_id": task,
        "title": "Fictional result", "text": "SYNTHETIC ONLY: Welcome to our fictional garden."}, tokens["beacon"])["id"]
    sync()
    require({item["id"] for item in state("atlas")["items"]} == {task}, "Unreleased artifact crossed boundary")
    action("beacon", artifact, "release")
    sync()
    action("atlas", artifact, "decision", "accept")
    sync()
    persisted = {}
    for owner in OWNERS:
        current = state(owner)
        require({item["id"] for item in current["items"]} == {task, artifact}, "Unexpected exchanged objects")
        require(all(item["state"] == "accepted" for item in current["items"]), "Exchange did not settle")
        require(current["provider"]["enabled"] is False, "Provider unexpectedly enabled")
        persisted[owner] = {"items": current["items"], "history": current["history"],
                            "reviews": {item: harness.request(owner, "GET", "/api/items/" + item + "/review",
                                                              token=tokens[owner]) for item in (task, artifact)}}

    # Restart actual server containers on the same private named volumes.
    for owner in OWNERS:
        harness.docker("restart", harness.name(owner))
    for owner in OWNERS:
        harness.wait_ready(owner)
        harness.request(owner, "GET", "/api/state", token=tokens[owner], expected=401)
        fresh = harness.request(owner, "POST", "/api/session", {"password": passwords[owner]})
        require(fresh["identity"] == identities[owner]["identity"], "Identity changed on restart")
        tokens[owner] = fresh["token"]
        current = state(owner)
        require(current["items"] == persisted[owner]["items"] and current["history"] == persisted[owner]["history"],
                "Exact item identities, digests, decisions or history changed on restart")
        for item in (task, artifact):
            review = harness.request(owner, "GET", "/api/items/" + item + "/review", token=tokens[owner])
            require(review == persisted[owner]["reviews"][item], "Exact reviewed content changed on restart")
    return {"task_and_artifact": "accepted through unchanged pilot HTTP routes",
            "cross_owner_password_and_session": "rejected both directions",
            "unreleased_content": "not delivered", "receipt_is_acceptance": False,
            "restart": "identities/history preserved; old sessions rejected", "live_provider_enabled": False}


def run():
    harness = Harness()
    try:
        harness.prepare()
        passwords = {owner: secrets.token_urlsafe(32) for owner in OWNERS}
        identities = {owner: harness.provision(owner, passwords[owner]) for owner in OWNERS}
        require(identities["atlas"]["fingerprint"] != identities["beacon"]["fingerprint"], "Shared cryptographic identity")
        for owner in OWNERS:
            harness.wait_ready(owner)
        boundary = harness.boundaries()
        messages = exchange(harness, passwords, identities)
        return {"schema": "assistant-central-isolation/1", "result": "passed", "synthetic_only": True,
                "isolation": boundary, "exchange": messages,
                "host_or_kernel_compromise_tested": False, "real_people_enrolled": False}
    finally:
        original = sys.exc_info()[1]
        try:
            harness.cleanup()
        except RuntimeError as cleanup_error:
            if original is not None:
                raise RuntimeError(str(original) + "; " + str(cleanup_error)) from None
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a credential-free success report after cleanup succeeds")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Output path already exists; choose a fresh path to avoid stale success evidence")
    try:
        result = run()
    except (RuntimeError, AssertionError, subprocess.TimeoutExpired) as exc:
        print("Isolation check FAILED: " + str(exc), file=sys.stderr)
        return 1
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
