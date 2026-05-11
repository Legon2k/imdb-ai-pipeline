import os
import sys

# Ensure the package in src/ is importable when running tests from this directory.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
