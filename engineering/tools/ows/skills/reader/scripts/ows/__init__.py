"""Read and validate OWS workflow files that carry `metadata.org` governance.

    from ows import load, validate

Standard library only; PyYAML is imported only to read a .yaml or .yml file. The validators are the
modules `validate_org`, `validate_catalog` and `validate_manifest`; `expr` is the runtime expression subset.
"""
from . import expr, validate_catalog, validate_manifest, validate_org  # noqa: F401
from .validate_org import LoadError, UsageError, load_file as load  # noqa: F401

__all__ = ["load", "validate", "LoadError", "UsageError"]


def validate(doc, catalog, manifest):
    """Errors for one parsed workflow against a merged catalog and a manifest; empty means valid. Never raises."""
    return validate_org.validate_org(doc, catalog, manifest)

