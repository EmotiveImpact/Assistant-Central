"""Fail closed on socket/process creation in our isolated fixture subprocesses.

Python audit hooks are regression guards for this reviewed fixture, not an OS
sandbox against arbitrary hostile code or a compromised interpreter.
"""
import sys


def install():
    def guard(event, args):
        if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'):
            raise RuntimeError('Offline fixture forbids network and child-process operations')
    sys.addaudithook(guard)
