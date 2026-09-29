import pytest
from pathlib import Path
from unittest.mock import patch
from jatai.core.daemon import JataiDaemon
from jatai.core.node import Node
from jatai.core.registry import Registry

class TestGCAUTODeleteMode:
    """Tests for ADR-16: Deletion Policy Separation and Operator Confirmation."""

    @patch('jatai.core.daemon.send2trash')
    def test_gc_auto_delete_mode_trash(self, mock_send2trash, temp_dir):
        """Test default GC_AUTO_DELETE_MODE is 'trash' and uses send2trash."""
        node_dir = temp_dir / "node1"
        node_dir.mkdir()
        
        f = node_dir / "test.txt"
        f.write_text("x")
        
        reg_path = temp_dir / "reg.yaml"
        reg = Registry(registry_path=reg_path)
        daemon = JataiDaemon(registry_path=reg_path)
        
        daemon._delete_path(f, mode="trash")
        mock_send2trash.assert_called_once()
        # Mock does not delete, so f still exists. But send2trash was called.

    @patch('pathlib.Path.unlink')
    def test_gc_auto_delete_mode_purge(self, mock_unlink, temp_dir):
        """Test GC_AUTO_DELETE_MODE='purge' hard deletes files."""
        node_dir = temp_dir / "node2"
        node_dir.mkdir()
        
        f = node_dir / "test.txt"
        f.write_text("x")
        
        reg_path = temp_dir / "reg2.yaml"
        daemon = JataiDaemon(registry_path=reg_path)
        
        daemon._delete_path(f, mode="purge")
        mock_unlink.assert_called_once()

    @patch('jatai.core.daemon.send2trash')
    def test_gc_auto_delete_mode_trash_fallback_to_purge(self, mock_send2trash, temp_dir):
        """Test fallback to permanent delete when send2trash fails."""
        mock_send2trash.side_effect = OSError("Trash not available")
        
        node_dir = temp_dir / "node3"
        node_dir.mkdir()
        
        f = node_dir / "test.txt"
        f.write_text("x")
        
        reg_path = temp_dir / "reg3.yaml"
        daemon = JataiDaemon(registry_path=reg_path)
        
        daemon._delete_path(f, mode="trash")
        
        # mock failed, should fallback to unlink. Check if file is gone
        assert not f.exists()
