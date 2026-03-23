"""
Pytest configuration and shared fixtures for Jataí tests.
"""

import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test use."""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def temp_home(monkeypatch, temp_dir):
    """Mock the home directory for testing global registry."""
    home_dir = temp_dir / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


@pytest.fixture
def sample_node_dir(temp_dir):
    """Create a sample node directory structure for testing."""
    node_dir = temp_dir / "test_node"
    node_dir.mkdir()
    return node_dir
