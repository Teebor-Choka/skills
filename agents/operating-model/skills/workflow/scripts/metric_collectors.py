"""Metric collectors: a registry keyed by the catalog's `reads` sources. STUB (red): every metric is -1."""


class NoValue(Exception):
    pass


class Registry:
    def __init__(self, collectors=()):
        self._by = {c.source: c for c in collectors}

    def sources(self):
        return list(self._by)

    def compute(self, metric, entry, inputs, key=None):
        return {"value": -1}


def collect(catalog, registry, inputs, key=None):
    return {m: {"value": -1} for m in catalog}


def default_registry():
    return Registry()
