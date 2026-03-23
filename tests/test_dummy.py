"""
Dummy test to verify pytest framework is working correctly.
"""

import pytest


def test_dummy_assertion():
    """Test that basic assertions work."""
    assert 1 + 1 == 2


def test_dummy_with_fixture(temp_dir):
    """Test that fixtures are working correctly."""
    assert temp_dir.exists()
    assert temp_dir.is_dir()
