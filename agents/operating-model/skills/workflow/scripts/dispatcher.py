"""Event dispatcher (U18). STUB: replaced by the implementation in the next commit."""


class Dispatcher:
    def __init__(self, root, state_path, ledger_dir, make_runtime, max_depth=8, max_starts=100):
        self.root, self.state_path, self.ledger_dir = root, state_path, ledger_dir

    def deliver(self, event):
        return []

    def state(self):
        return {}
