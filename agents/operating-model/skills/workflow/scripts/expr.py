"""Restricted jq subset for OWS runtime expressions (stub, not implemented yet)."""


class ExprError(ValueError):
    pass


def is_expression(value):
    return None


def unwrap(text):
    return None


def parse(source):
    return None


def evaluate(source, data=None, variables=None):
    return None


def resolve(value, data=None, variables=None):
    return None
