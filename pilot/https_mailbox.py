"""Opt-in TLS ciphertext quarantine. No owner session, decryption or execution."""
import fcntl
import hashlib
import json
import os
import re
import socketserver
import ssl
import stat
import time

from .crypto import MAX_PACKET, packet_header
from .file_exchange import private_parent, private_file, require

ROUTE = '/v1/quarantine'
MEDIA = 'application/vnd.assistant-central.packet+json'
ACK = b'HTTP/1.1 202 Accepted\r\nContent-Length: 11\r\nConnection: close\r\n\r\nquarantined'
REJECT = b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'


def parse_packet(raw):
    require(0 < len(raw) <= MAX_PACKET)
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result
    def reject(_):
        raise ValueError('Invalid JSON')
    packet = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject)
    packet_header(packet)
    return packet


def read_private(path, maximum):
    with private_parent(path) as (parent, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            private_file(before)
            require(0 < before.st_size <= maximum)
            raw = os.read(fd, maximum + 1)
            after = os.fstat(fd)
            private_file(after)
            require(len(raw) == before.st_size == after.st_size and
                    (before.st_mtime_ns, before.st_ctime_ns) == (after.st_mtime_ns, after.st_ctime_ns))
            return raw
        finally:
            os.close(fd)


class Quarantine:
    """Exclusive process lease; immutable files and serialized capacity checks."""
    def __init__(self, directory, recipient, *, max_files=64, max_bytes=1048576):
        require(re.fullmatch('[0-9a-f]{64}', recipient) is not None)
        require(type(max_files) is int and 1 <= max_files <= 1024)
        require(type(max_bytes) is int and 1 <= max_bytes <= 32 * 1024 * 1024)
        self.recipient, self.max_files, self.max_bytes = recipient, max_files, max_bytes
        self.parent = private_parent(os.path.join(directory, '.lease'))
        self.fd, _ = self.parent.__enter__()
        self.lock = None
        try:
            self.lock = os.open('.lease', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                                0o600, dir_fd=self.fd)
            private_file(os.fstat(self.lock))
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            import threading
            self.mutex = threading.Lock()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        self.parent.__exit__(None, None, None)

    def store(self, raw):
        packet = parse_packet(raw)
        require(packet['header']['recipient'] == self.recipient)
        name = hashlib.sha256(raw).hexdigest() + '.json'
        with self.mutex:
            info = os.fstat(self.fd)
            require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0)
            private_file(os.fstat(self.lock))
            names = os.listdir(self.fd)
            count = size = 0
            existing = None
            for entry in names:
                if entry == '.lease':
                    continue
                require(re.fullmatch('[0-9a-f]{64}\\.json', entry) is not None)
                fd = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
                try:
                    info = os.fstat(fd)
                    private_file(info)
                    require(info.st_size <= MAX_PACKET)
                    count += 1
                    size += info.st_size
                    if entry == name:
                        existing = os.read(fd, MAX_PACKET + 1)
                        require(existing == raw)
                        os.fsync(fd)
                finally:
                    os.close(fd)
            require(count <= self.max_files and size <= self.max_bytes)
            if existing is not None:
                os.fsync(self.fd)
                return name
            require(count < self.max_files and size + len(raw) <= self.max_bytes)
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self.fd)
            try:
                private_file(os.fstat(fd))
                offset = 0
                while offset < len(raw):
                    written = os.write(fd, raw[offset:])
                    require(written > 0)
                    offset += written
                os.fsync(fd)
                os.fsync(self.fd)
            finally:
                os.close(fd)
            return name


class MailboxServer(socketserver.TCPServer):
    """Single in-flight request; small backlog; TLS handshake included in deadline."""
    request_queue_size = 4
    allow_reuse_address = False

    def __init__(self, quarantine, certificate, private_key, *, address=('127.0.0.1', 0), enabled=False):
        require(enabled is True)
        # Read from pinned private descriptors; never load secrets via CLI arguments.
        cert = read_private(certificate, 65536)
        key = read_private(private_key, 65536)
        # OpenSSL requires filenames; private temporary copies avoid input path races.
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, raw in (('cert', cert), ('key', key)):
                path = os.path.join(directory, name)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as output:
                    output.write(raw)
                paths.append(path)
            self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.context.minimum_version = ssl.TLSVersion.TLSv1_3
            self.context.load_cert_chain(*paths)
        self.quarantine = quarantine
        super().__init__(address, _Handler)

    def handle_error(self, request, client_address):
        pass  # Never log attacker-controlled request bytes or file paths.


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        deadline = time.monotonic() + 3
        stream = None
        try:
            self.request.settimeout(3)
            stream = self.server.context.wrap_socket(self.request, server_side=True)
            def read(count):
                remaining = deadline - time.monotonic()
                require(remaining > 0)
                stream.settimeout(remaining)
                return stream.recv(count)
            header = bytearray()
            while not header.endswith(b'\r\n\r\n'):
                require(len(header) < 2048)
                value = read(1)
                require(bool(value))
                header.extend(value)
            lines = header.decode('ascii').split('\r\n')
            require(lines[0] == 'POST ' + ROUTE + ' HTTP/1.1')
            fields = {}
            for line in lines[1:-2]:
                name, separator, value = line.partition(': ')
                name = name.lower()
                require(separator and name not in fields)
                fields[name] = value
            require(set(fields) == {'host', 'content-type', 'content-length', 'connection'})
            require(re.fullmatch(r'[A-Za-z0-9.\[\]:-]{1,255}', fields['host']) is not None)
            require(fields['content-type'] == MEDIA and fields['connection'] == 'close')
            require(re.fullmatch('[1-9][0-9]{0,4}', fields['content-length']) is not None)
            length = int(fields['content-length'])
            require(length <= MAX_PACKET)
            body = bytearray()
            while len(body) < length:
                value = read(length - len(body))
                require(bool(value))
                body.extend(value)
            self.server.quarantine.store(bytes(body))
            remaining = deadline - time.monotonic()
            require(remaining > 0)
            stream.settimeout(remaining)
            stream.sendall(ACK)
        except Exception:
            if stream is not None:
                try:
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        stream.settimeout(remaining)
                        stream.sendall(REJECT)
                except Exception:
                    pass
        finally:
            if stream is not None:
                stream.close()
