"""Metric catalog validator (stub for the red run)."""


class LoadError(Exception):
    pass


class UsageError(Exception):
    pass


def load_document(path):
    return None


def merge_catalogs(files):
    return {}, []


def validate_catalog(files, root):
    return []


def main(argv=None):
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
