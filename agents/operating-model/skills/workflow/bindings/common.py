class GhError(Exception):
    def __init__(self, kind, message=""):
        super().__init__(message)
        self.kind = kind


def redact(text, secrets=()):
    return text


class Gh:
    def __init__(self, repo, runner=None, env=None, timeout=60):
        self.repo, self.log = repo, []

    def api(self, method, path, body=None, paginate=False):
        raise GhError("unavailable", "stub")
