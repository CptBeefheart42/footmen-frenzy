"""Helpers shared by the Python test tools: reading the map's Preload files, the result file model,
PASS/FAIL reporting and the repository / test-client paths.

The tools are run as scripts (`python3 -I tests/e2e/check_e2e.py ...`), so each one puts the repository root on
`sys.path` before it imports this package.
"""
