"""Container-side test helper. JSON requests arrive on stdin, never in argv/env.

Only the trusted, disposable test controller calls this helper. It is not an HTTP
endpoint and must not be copied into a production image as an owner API.
"""
import errno
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import stat
import sys


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def denied(operation, extra=()):
    """Only a concrete access/missing-namespace denial counts as a pass."""
    try:
        operation()
    except OSError as exc:
        require(exc.errno in (errno.EACCES, errno.EPERM, errno.ENOENT, errno.EROFS) + extra,
                "Unexpected error, not evidence of isolation")
        return errno.errorcode[exc.errno]
    raise AssertionError("Cross-owner operation unexpectedly succeeded")


def snapshot(directory):
    root = Path(directory)
    files = {}
    for path in sorted(root.iterdir()):
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode), "Unexpected private storage entry")
        files[path.name] = {"mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid,
                            "hash": hashlib.sha256(path.read_bytes()).hexdigest()}
    return files


def boundary(data):
    own, peer = Path(data["own"]), Path(data["peer"])
    require(os.geteuid() == data["uid"] != 0, "Probe has the wrong UID")
    # Positive control: this UID can create/read/write/remove its own data.
    positive = own / "positive-control"
    with positive.open("xb") as stream:
        stream.write(b"synthetic own data")
    positive.write_bytes(b"updated synthetic own data")
    require(positive.read_bytes() == b"updated synthetic own data", "Own storage is not writable")
    positive.unlink()

    errors = {"list_peer": denied(lambda: list(peer.iterdir()))}
    # Known existing paths, including the *real* encrypted identity vault/store.
    # The normal deployment never mounts the peer volume. A separate DAC probe
    # repeats these operations with both actual volumes mounted, as the attacker UID.
    for filename in data["peer_files"]:
        victim = peer / filename
        errors["read:" + filename] = denied(victim.read_bytes)
        errors["overwrite:" + filename] = denied(lambda p=victim: p.write_bytes(b"tampered"))
        errors["unlink:" + filename] = denied(victim.unlink)
        errors["chmod:" + filename] = denied(lambda p=victim: p.chmod(0o600))
        errors["rename:" + filename] = denied(lambda p=victim: p.rename(peer / "renamed"))
    errors["create_peer"] = denied(lambda: (peer / "injected").write_bytes(b"tampered"))
    link = own / "peer-link"
    link.symlink_to(peer / "canary.txt")
    try:
        errors["symlink_read"] = denied(link.read_bytes)
        errors["symlink_write"] = denied(lambda: link.write_bytes(b"tampered"))
    finally:
        link.unlink()
    errors["replace_peer"] = denied(lambda: os.replace(own / "canary.txt", peer / "canary.txt"), (errno.EXDEV,))
    errors["chmod_peer_directory"] = denied(lambda: peer.chmod(0o700))
    errors["modify_code"] = denied(lambda: Path("/app/pilot/server.py").write_text("tampered"))
    require(not Path("/var/run/docker.sock").exists(), "Docker socket exposed")
    require(not Path("/run/containerd/containerd.sock").exists(), "Container runtime socket exposed")
    return errors


def environment(directory):
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
    root = Path(directory).stat()
    return {"uid": os.geteuid(), "gid": os.getegid(), "groups": os.getgroups(),
            "directory_uid": root.st_uid, "directory_mode": stat.S_IMODE(root.st_mode),
            "network_interfaces": sorted(path.name for path in Path("/sys/class/net").iterdir()),
            "namespaces": {name: os.readlink("/proc/self/ns/" + name) for name in ("mnt", "pid", "net")},
            "cap_effective": status["CapEff"].strip(), "cap_permitted": status["CapPrm"].strip(),
            "no_new_privs": status["NoNewPrivs"].strip(), "seccomp": status["Seccomp"].strip()}


def main(data):
    operation = data["operation"]
    if operation == "provision":
        from pilot.auth import LocalOwnerAuth
        from pilot.crypto import fingerprint
        auth = LocalOwnerAuth(data["directory"])
        try:
            public = auth.bootstrap(data["owner"], data["agent"], data["password"])
        finally:
            auth.close()
        canary = Path(data["directory"]) / "canary.txt"
        fd = os.open(canary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_hex(32))
        return {"identity": public, "fingerprint": fingerprint(public)}
    if operation == "snapshot":
        return snapshot(data["directory"])
    if operation == "environment":
        return environment(data["directory"])
    if operation == "boundary":
        return boundary(data)
    if operation == "request":
        port = data["port"]
        require(type(port) is int and port in (8765, 8766), "Unexpected test port")
        headers = {"Origin": "http://127.0.0.1:" + str(port), "Accept": "application/json"}
        body = data.get("body")
        if body is not None:
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if data.get("token"):
            headers["Authorization"] = "Bearer " + data["token"]
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
        try:
            connection.request(data["method"], data["path"], body, headers)
            response = connection.getresponse()
            raw = response.read(2 * 1024 * 1024 + 1)
            require(len(raw) <= 2 * 1024 * 1024, "Response too large")
            return {"status": response.status, "body": json.loads(raw)}
        finally:
            connection.close()
    raise ValueError("Unknown harness operation")


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as exc:
        # No input, HTTP body, passwords, keys or tokens in diagnostics.
        print(json.dumps({"error": type(exc).__name__}), file=sys.stderr)
        sys.exit(1)
