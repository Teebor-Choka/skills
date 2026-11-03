# fixtures/ contains a throwaway Python project used AS TEST DATA (copied
# into a tmp dir and run through code-quality:measure by test_measure.py) —
# its own test_*.py files aren't part of this suite, but pytest's default
# recursive discovery would otherwise collect and run them too.
collect_ignore = ["fixtures"]
