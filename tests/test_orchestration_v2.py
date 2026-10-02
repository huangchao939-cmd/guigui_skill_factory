"""Expose the skill's self-contained synthetic test suite to repository discovery."""
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/multi-agent-framework-builder/scripts"
sys.path.insert(0, str(SCRIPTS))
from self_test import ProtocolTests  # noqa: E402,F401
