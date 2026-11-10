"""Explicit offline ciphertext handoff. No networking or automatic retries."""
import argparse
from contextlib import contextmanager
import getpass
import json
import os
from pathlib import Path
import stat
import warnings

from .auth import LocalOwnerAuth
from .crypto import MAX_PACKET, TransportDenied, canonical, packet_header
from .runtime import PilotRuntime, RuntimeDenied


class FileExchangeDenied(ValueError):
    pass


class FileOutcomeUnknown(RuntimeError):
    """A file or runtime operation may have taken effect; inspect before retry."""


def require(condition):
    if not condition:
        raise FileExchangeDenied('Private regular packet file required')


@contextmanager
def private_parent(path):
    """Pin every directory component without following symbolic links."""
    require('..' not in Path(path).parts)
    path = Path(os.path.abspath(os.fspath(path)))
    require(path.name not in ('', '.', '..'))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        def trusted(info):
            mode = stat.S_IMODE(info.st_mode)
            require(info.st_uid in (0, os.geteuid()) and
                    (mode & 0o022 == 0 or (info.st_uid == 0 and mode & stat.S_ISVTX)))
        trusted(os.fstat(fd))
        for part in path.parent.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            trusted(os.fstat(fd))
        info = os.fstat(fd)
        require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0)
        yield fd, path.name
    finally:
        os.close(fd)


def private_file(info):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) & 0o077 == 0 and info.st_nlink == 1)


def read_packet(path):
    with private_parent(path) as (parent, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            private_file(before)
            require(0 < before.st_size <= MAX_PACKET)
            raw = bytearray()
            while len(raw) <= MAX_PACKET:
                chunk = os.read(fd, MAX_PACKET + 1 - len(raw))
                if not chunk:
                    break
                raw.extend(chunk)
            after = os.fstat(fd)
            private_file(after)
            require(0 < len(raw) <= MAX_PACKET and before.st_size == len(raw)
                    and (before.st_mtime_ns, before.st_ctime_ns) == (after.st_mtime_ns, after.st_ctime_ns))
        finally:
            os.close(fd)
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result
    def constant(_):
        raise FileExchangeDenied('Invalid packet JSON')
    try:
        packet = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        packet_header(packet)
        return packet
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise FileExchangeDenied('Invalid bounded packet JSON') from None


def write_packet(path, packet):
    """Exclusive creation; failure may leave a partial file and never removes it."""
    packet_header(packet)
    raw = canonical(packet)
    with private_parent(path) as (parent, name):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            private_file(os.fstat(fd))
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:])
                if count <= 0:
                    raise OSError('Incomplete output')
                offset += count
            os.fsync(fd)
            private_file(os.fstat(fd))
            os.fsync(parent)
        except BaseException:
            raise FileOutcomeUnknown('Output may be partial or complete; inspect before any explicit retry.') from None
        finally:
            os.close(fd)


class FileExchange:
    def __init__(self, runtime):
        self.runtime = runtime

    @contextmanager
    def authorised(self, session):
        with self.runtime.auth.authorised(session) as identity:
            require(identity['identity_fingerprint'] == self.runtime.fingerprint)
            yield

    def export(self, session, message_id, destination):
        with self.authorised(session):
            # Persist uncertain state BEFORE any bytes may leave this owner.
            try:
                packet = self.runtime.prepare_delivery(session, message_id)
            except (RuntimeDenied, TransportDenied, PermissionError):
                raise
            except BaseException:
                raise FileOutcomeUnknown('Export preparation outcome unavailable; inspect retained outbox before retry.') from None
            try:
                self.runtime.auth.authenticate(session)
                write_packet(destination, packet)
            except BaseException:
                raise FileOutcomeUnknown('Export attempt retained as uncertain; inspect file and outbox before retry.') from None
        return {'message_id': message_id, 'delivery': 'uncertain', 'owner_acceptance': 'not_established'}

    def receive(self, session, source, receipt_destination=None):
        with self.authorised(session):
            packet = read_packet(source)
            try:
                result = self.runtime.receive(session, packet)
            except (RuntimeDenied, TransportDenied, PermissionError):
                raise
            except BaseException:
                raise FileOutcomeUnknown('Import outcome unavailable; inspect retained inbox before retry.') from None
            if receipt_destination is not None and result['receipt'] is not None:
                try:
                    self.runtime.auth.authenticate(session)
                    write_packet(receipt_destination, result['receipt'])
                except BaseException:
                    raise FileOutcomeUnknown('Import committed; receipt output unavailable. Recover the cached receipt explicitly.') from None
            # Do not print titles, payloads, bearer credentials, or raw receipts.
            return {'message_id': result['message_id'], 'duplicate': result['duplicate'],
                    'receipt_available': result['receipt'] is not None,
                    'owner_acceptance': result['owner_acceptance'], 'authorises_execution': False}

    def receipt(self, session, incoming_id, destination):
        with self.authorised(session):
            # Runtime owns the authenticated transaction and expiry recheck. The
            # transport returns the original cached signed receipt, never renews it.
            with self.runtime._transaction(session):
                packet = self.runtime.exchange.receipt_for(self.runtime.auth, session, incoming_id)
            try:
                self.runtime.auth.authenticate(session)
                write_packet(destination, packet)
            except BaseException:
                raise FileOutcomeUnknown('Receipt output unavailable; cached original remains. Inspect before retry.') from None
            return {'message_id': incoming_id, 'transport_receipt_only': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline encrypted file exchange. Stop the owner service first. Synthetic data only.')
    parser.add_argument('--directory', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('export', 'receipt'):
        sub = commands.add_parser(command)
        sub.add_argument('--message-id', required=True)
        sub.add_argument('--output', required=True)
    sub = commands.add_parser('import')
    sub.add_argument('--input', required=True)
    sub.add_argument('--receipt-output')
    args = parser.parse_args(argv)
    auth = runtime = None
    try:
        # Do not initialise a mistaken path, or prompt while the service owns it.
        require(all((Path(args.directory) / name).is_file()
                    for name in ('auth.sqlite', 'runtime.sqlite')))
        with private_parent(Path(args.directory) / 'auth.sqlite'):
            pass
        auth = LocalOwnerAuth(args.directory)
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('Local owner password: ')
        session = auth.login(password)
        del password
        runtime = PilotRuntime(args.directory, auth)
        exchange = FileExchange(runtime)
        if args.command == 'import':
            result = exchange.receive(session, args.input, args.receipt_output)
        else:
            result = getattr(exchange, args.command)(session, args.message_id, args.output)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Stopped. Inspect retained state before retrying any operation.')
        return 1
    except Exception:
        print('Operation unavailable. Stop the owner service; inspect retained state and files before retrying. No automatic retry was made.')
        return 1
    finally:
        if runtime is not None:
            runtime.close()
        if auth is not None:
            auth.close()


if __name__ == '__main__':
    raise SystemExit(main())
