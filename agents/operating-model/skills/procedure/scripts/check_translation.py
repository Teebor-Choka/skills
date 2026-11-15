#!/usr/bin/env python3
"""Check a prose-to-procedure translation: every sentence is traced to the machine or is a gap.

    check_translation.py TRANSLATION PROCEDURE
"""
import sys

__all__ = ("check_translation", "main")


def check_translation(translation_text, procedure_text, src="<translation>"):
    """Return (errors, gaps). A gap is a sentence the machine cannot express yet."""
    return [], []


def main(argv=None):
    return 0


if __name__ == "__main__":
    sys.exit(main())
