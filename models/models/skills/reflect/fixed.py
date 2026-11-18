"""Mark findings FIXED by commit date (stub)."""


def mark(findings, repo):
    return [{**f, "status": "OPEN"} for f in findings]
