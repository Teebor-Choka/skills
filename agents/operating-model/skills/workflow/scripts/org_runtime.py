"""Org runtime (U13b). Stub: the public API with wrong answers, so the first test run fails on assertions."""
UNENFORCED = object()
DEFAULT_FROZEN_OUTSIDE = ()


class LedgerError(Exception):
    pass


class OwnerKeyError(Exception):
    pass


class FileMapError(Exception):
    pass


class FrozenOutside:
    def __init__(self, repo_root, paths):
        pass

    def map(self):
        return {}


class RunLedger:
    def __init__(self, path, key):
        pass

    def read(self):
        return []


class KeyRing:
    def __init__(self, keys, verifier=None):
        pass

    def verify(self, event, signer):
        return True

    def revoke(self, key):
        pass

    def list(self):
        return {}


class SshKeygenVerifier:
    pass


class SnapshotStore:
    def __init__(self, path):
        pass

    def add(self, files, outside, signature):
        pass


class ProcessCollector:
    def __init__(self, root):
        pass


class InboxFeed:
    def __init__(self, path):
        self.rejected = []

    def poll(self):
        return []


class QueueFeed:
    def push(self, event):
        pass


class OrgProcessHost:
    def __init__(self, root, session_dir=None, env=None):
        pass

    def run_judge(self, req):
        return None

    def run_step(self, req):
        return None


class OrgRuntime:
    def __init__(self, root, *, ledger_path, ledger_key, ring, host, snapshots, frozen, **kw):
        pass

    def run(self, name, input=None, run_id=None, feed=None):
        return None

    def resume(self):
        return None

    def replay(self):
        return None


def load_ring(text, verifier=None):
    return None


def event_payload(event):
    return b""


def build_file_map(root):
    return {}


def check_collisions(paths):
    return None
