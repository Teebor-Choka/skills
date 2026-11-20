"""Operation contracts: validator and conformance harness (inert skeleton, replaced by the implementation)."""


class PortError(Exception):
    def __init__(self, code, message=""):
        super().__init__(f"{code}: {message}")
        self.code = code


def validate_contract(doc, catalog=None):
    return []


def run_port(contract, adapter, catalog=None):
    return []
