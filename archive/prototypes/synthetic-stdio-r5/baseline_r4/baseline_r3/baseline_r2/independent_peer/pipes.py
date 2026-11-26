"""Finite framed anonymous-pipe transport. No listeners, sockets or network calls."""
import os
import selectors
import struct
import time

from .protocol import MAX_FRAME, Rejected, canonical, need, parse

FRAME_SECONDS = 1.0
WRITE_SECONDS = 1.0


def frame(value):
    raw = canonical(value)
    need(0 < len(raw) <= MAX_FRAME, 'frame size')
    return struct.pack('!I', len(raw)) + raw


def serve(endpoint, owner_read, owner_write, peer_read, peer_write):
    """Two fixed method tables. One bounded request/response in flight per lane.

    Slow partial input or unread output kills the fixture endpoint, failing closed.
    Owner and peer lanes remain independently selectable until that finite failure.
    These are I/O bounds, not hard crypto/SQLite/whole-action deadline guarantees.
    """
    selector = selectors.DefaultSelector()
    lanes = []
    for name, read_fd, write_fd in [('owner', owner_read, owner_write), ('peer', peer_read, peer_write)]:
        os.set_blocking(read_fd, False)
        os.set_blocking(write_fd, False)
        lane = {'name': name, 'r': read_fd, 'w': write_fd, 'input': bytearray(), 'output': bytearray(),
                'read_deadline': None, 'write_deadline': None, 'size': None}
        lanes.append(lane)
        selector.register(read_fd, selectors.EVENT_READ, (lane, 'read'))
    try:
        while True:
            now = time.monotonic()
            deadlines = [lane[k] for lane in lanes for k in ('read_deadline', 'write_deadline') if lane[k] is not None]
            if deadlines and min(deadlines) <= now:
                raise TimeoutError('pipe deadline: outcome may be uncertain')
            timeout = min(0.1, max(0, min(deadlines) - now)) if deadlines else 0.1
            for key, _ in selector.select(timeout):
                lane, direction = key.data
                if direction == 'write':
                    try:
                        count = os.write(lane['w'], lane['output'][:4096])
                    except BlockingIOError:
                        continue
                    del lane['output'][:count]
                    if not lane['output']:
                        selector.unregister(lane['w'])
                        lane['write_deadline'] = None
                        selector.register(lane['r'], selectors.EVENT_READ, (lane, 'read'))
                    continue
                # Read only remaining prefix/body bytes: never admit a second pipelined frame.
                remaining = 4 - len(lane['input']) if lane['size'] is None else lane['size'] + 4 - len(lane['input'])
                try:
                    data = os.read(lane['r'], min(4096, remaining))
                except BlockingIOError:
                    continue
                if not data:
                    return  # Any control/transport EOF terminates this disposable endpoint.
                if lane['read_deadline'] is None:
                    lane['read_deadline'] = time.monotonic() + FRAME_SECONDS
                lane['input'].extend(data)
                if lane['size'] is None and len(lane['input']) == 4:
                    lane['size'] = struct.unpack('!I', lane['input'])[0]
                    need(0 < lane['size'] <= MAX_FRAME, 'frame size')
                if lane['size'] is None or len(lane['input']) != lane['size'] + 4:
                    continue
                command = parse(bytes(lane['input'][4:]))  # Malformed framing/JSON ends the process.
                try:
                    handler = endpoint.handle_owner if lane['name'] == 'owner' else endpoint.handle_peer
                    value = handler(command)
                    response = {'ok': True, 'value': value}
                except Rejected as exc:
                    response = {'ok': False, 'error': str(exc)}
                lane['input'].clear()
                lane['size'] = lane['read_deadline'] = None
                lane['output'].extend(frame(response))
                lane['write_deadline'] = time.monotonic() + WRITE_SECONDS
                selector.unregister(lane['r'])
                selector.register(lane['w'], selectors.EVENT_WRITE, (lane, 'write'))
    finally:
        selector.close()
        for lane in lanes:
            for fd in (lane['r'], lane['w']):
                try:
                    os.close(fd)
                except OSError:
                    pass
        endpoint.close()
