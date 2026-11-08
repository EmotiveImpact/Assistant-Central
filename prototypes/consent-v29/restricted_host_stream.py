"""Bounded offline byte-stream transport for one trusted, pre-bound session.

No launcher, owner controls, authentication, diagnostics or automatic retries.
The caller owns streams and must supply blocking binary read/write operations.
"""
from dataclasses import dataclass
from restricted_host_protocol import RestrictedHostSession, MAX_INPUT, MAX_OUTPUT

READ_CHUNK = 4096


@dataclass(frozen=True)
class StreamEnd:
    # Trusted local report, never written to the protocol stream. A successful
    # flush is not acknowledgement of receipt, processing, or owner approval.
    # False does NOT mean earlier calls did not mutate or replies were received.
    reason: str
    outcome_unknown: bool = False


def _write(writer, message):
    if type(message) is not bytes or len(message) > MAX_OUTPUT or b'\n' in message:
        raise ValueError('Invalid response frame')
    frame = message + b'\n'
    offset = 0
    while offset < len(frame):
        written = writer.write(frame[offset:])
        if type(written) is not int or not 0 < written <= len(frame) - offset:
            raise OSError('Output did not advance')
        offset += written
    writer.flush()


def serve(reader, writer, session):
    """Serve sequential LF records; always close the session, not caller streams.

    A single owner must dedicate this session to this invocation. read1 is used
    when available to avoid buffered read(n) waiting for n bytes on a pipe.
    read(n) otherwise must be a blocking binary read returning at most n bytes.
    Pending payload is bounded by MAX_INPUT, each read by READ_CHUNK. Parsing
    and writing use bounded transient copies, not a precise heap-size guarantee. Oversize/partial EOF never dispatch the unfinished record.
    No drain/resynchronization after oversize; no callback or response retries.
    Output failure can follow a committed proposal: inspect its durable ID via
    a new independently authorized session rather than assuming it failed.
    """
    if type(session) is not RestrictedHostSession:
        raise TypeError('Expected a pre-bound restricted session')
    pending = bytearray()
    try:
        try:
            read = getattr(reader, 'read1', None)
            if read is None:
                read = reader.read
            if not callable(read):
                return StreamEnd('input_failed')
        except Exception:
            return StreamEnd('input_failed')
        while True:
            limit = min(READ_CHUNK, MAX_INPUT + 1 - len(pending))
            try:
                chunk = read(limit)
                if type(chunk) is not bytes or len(chunk) > limit:
                    return StreamEnd('input_failed')
            except Exception:
                return StreamEnd('input_failed')
            if not chunk:
                return StreamEnd('partial_eof' if pending else 'eof')
            # Keep the receive buffer bounded even when many records arrive in
            # one read. Parse only complete records; never parse a truncated one.
            start = 0
            while True:
                end = chunk.find(b'\n', start)
                fragment = chunk[start:] if end < 0 else chunk[start:end]
                if len(pending) + len(fragment) > MAX_INPUT:
                    return StreamEnd('oversize_frame')
                pending.extend(fragment)
                if end < 0:
                    break
                response = session.handle(bytes(pending))
                pending.clear()
                if response is not None:
                    try:
                        _write(writer, response)
                    except Exception:
                        return StreamEnd('output_failed', outcome_unknown=True)
                start = end + 1
    finally:
        session.close()
