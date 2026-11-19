"""Stub: the implementation lands in the next commit."""


class UnsupportedFormatError(Exception):
    pass


def session_export(native_path, harness="claude-code"):
    raise NotImplementedError


def validate_record(record):
    raise NotImplementedError


def write_records(records, path):
    raise NotImplementedError


def load_records(path):
    raise NotImplementedError


def redact(text):
    raise NotImplementedError


KINDS = {}
COMMON = ()
