# shellcheck shell=bash
# Sourced, not executed. Declares Python's required tools, language-prefixed
# for the same reason rust/tools.sh's arrays are (no collision when both
# languages' tools.sh get sourced together for a multi-language project,
# even though both happen to have a metric called "crap").
#
# pytest-cov's presence is NOT verifiable this way — it's a pytest plugin,
# not a standalone binary on PATH, so `command -v pytest` succeeds whether
# or not pytest-cov is installed alongside it. Discovery can report
# `[available]` here and crap.sh can still fail at run time for a missing
# plugin. Documented as a known limitation in ../../references/python.md,
# not silently assumed away.

# shellcheck disable=SC2034 # read by assets/run.sh's case-dispatch, not by name lookup in this file
python_tools_crap=(crap4py pytest)
# shellcheck disable=SC2034
python_tools_cognitive=(complexipy)
# shellcheck disable=SC2034
python_tools_hotspots=(complexipy jq)
# shellcheck disable=SC2034
python_tools_duplication=(jscpd)
# shellcheck disable=SC2034
python_tools_iad=(pyscn)
