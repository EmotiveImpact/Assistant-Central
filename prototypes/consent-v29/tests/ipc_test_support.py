"""Controlled children only for pipe regression tests, never production launchers."""
import zlib
import subprocess
import sys
from unittest.mock import patch
from fixture_ipc import JsonProcess


def child(code, limit=16384):
    popen = subprocess.Popen
    def launch(*args, **kwargs):
        return popen([sys.executable, '-c', code], **kwargs)
    with patch('fixture_ipc.subprocess.Popen', side_effect=launch):
        return JsonProcess('owner_fixture_process.py', max_response_bytes=limit)


def output(frame, limit=16384):
    if isinstance(frame, str):
        frame = frame.encode('utf-8')
    return child('import sys,zlib; sys.stdout.buffer.write(zlib.decompress(' + repr(zlib.compress(frame)) + ')); sys.stdout.buffer.flush()', limit)
