"""Pytest configuration and shared fixtures."""
import pytest
import sys
from pathlib import Path

# Add the project root to Python path so tests can import scip_cli
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def sample_symbol():
    """Sample SCIP symbol for testing."""
    return "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation()."


@pytest.fixture
def sample_class_symbol():
    """Sample class symbol for testing."""
    return "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#"
