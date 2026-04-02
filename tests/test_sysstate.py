"""
Unit tests for jatai.core.sysstate.SystemState.

Coverage: Happy Path, Error/Failure Scenarios, Adversarial Scenarios.
"""
import pytest
from pathlib import Path

from jatai.core.sysstate import SystemState


@pytest.fixture
def isolated_sysstate(tmp_path, monkeypatch):
    """Redirect SystemState.BASE_PATH to a temporary directory so tests are isolated."""
    monkeypatch.setattr(SystemState, "BASE_PATH", tmp_path / "jatai")
    return tmp_path / "jatai"


class TestSysStateHappyPath:
    """Happy path tests for SystemState."""

    def test_assign_uuid_creates_new_entry(self, isolated_sysstate):
        """assign_uuid creates a UUID and persists it to uuid_map.yaml."""
        node_path = "/tmp/test_node_abc"
        uid = SystemState.assign_uuid(node_path)

        assert uid and len(uid) == 36  # standard UUID format: 8-4-4-4-12
        uuid_map = SystemState.read_yaml(SystemState.uuid_map_path())
        assert node_path in uuid_map
        assert uuid_map[node_path] == uid

    def test_assign_uuid_reuses_existing(self, isolated_sysstate):
        """assign_uuid returns the same UUID on repeated calls for the same path."""
        node_path = "/tmp/test_node_reuse"
        uid1 = SystemState.assign_uuid(node_path)
        uid2 = SystemState.assign_uuid(node_path)
        assert uid1 == uid2

    def test_get_uuid_returns_none_for_unknown(self, isolated_sysstate):
        """get_uuid returns None for a path that has not been registered."""
        assert SystemState.get_uuid("/tmp/never_registered_path") is None

    def test_get_uuid_returns_assigned_uuid(self, isolated_sysstate):
        """get_uuid returns the UUID previously assigned with assign_uuid."""
        node_path = "/tmp/get_uuid_test"
        uid = SystemState.assign_uuid(node_path)
        assert SystemState.get_uuid(node_path) == uid

    def test_mark_autoremoved_adds_entry(self, isolated_sysstate):
        """mark_autoremoved appends a '<path> --autoremoved' entry to removed.yaml."""
        node_path = "/tmp/to_be_removed"
        SystemState.mark_autoremoved(node_path)

        entries = SystemState.read_yaml(SystemState.removed_path())
        assert isinstance(entries, list)
        assert f"{node_path} --autoremoved" in entries

    def test_mark_autoremoved_idempotent(self, isolated_sysstate):
        """Calling mark_autoremoved twice for the same path produces a single entry."""
        node_path = "/tmp/duplicate_removal"
        SystemState.mark_autoremoved(node_path)
        SystemState.mark_autoremoved(node_path)

        entries = SystemState.read_yaml(SystemState.removed_path())
        count = sum(1 for e in entries if e == f"{node_path} --autoremoved")
        assert count == 1

    def test_write_and_read_bkp_config(self, isolated_sysstate):
        """write_bkp_config persists config; read_bkp_config recovers it exactly."""
        node_path = "/tmp/bkp_test_node"
        config = {"PREFIX_IGNORE": "_", "PREFIX_ERROR": "!_", "MAX_RETRIES": 3}
        SystemState.write_bkp_config(node_path, config)

        recovered = SystemState.read_bkp_config(node_path)
        assert recovered == config

    def test_read_bkp_config_returns_none_for_unknown(self, isolated_sysstate):
        """read_bkp_config returns None when no UUID is registered for the path."""
        result = SystemState.read_bkp_config("/tmp/no_bkp_registered")
        assert result is None

    def test_bkp_config_overwrites_on_second_write(self, isolated_sysstate):
        """Calling write_bkp_config twice replaces the previous backup."""
        node_path = "/tmp/bkp_overwrite_test"
        SystemState.write_bkp_config(node_path, {"PREFIX_IGNORE": "_"})
        SystemState.write_bkp_config(node_path, {"PREFIX_IGNORE": "done_"})

        recovered = SystemState.read_bkp_config(node_path)
        assert recovered["PREFIX_IGNORE"] == "done_"

    def test_mark_autoremoved_multiple_distinct_entries(self, isolated_sysstate):
        """Multiple distinct paths all appear as separate entries in removed.yaml."""
        paths = ["/tmp/node_x", "/tmp/node_y", "/tmp/node_z"]
        for p in paths:
            SystemState.mark_autoremoved(p)

        entries = SystemState.read_yaml(SystemState.removed_path())
        for p in paths:
            assert f"{p} --autoremoved" in entries

    def test_assign_uuid_multiple_distinct_paths_get_distinct_uuids(self, isolated_sysstate):
        """Each unique path receives its own unique UUID."""
        uid1 = SystemState.assign_uuid("/tmp/node_alpha")
        uid2 = SystemState.assign_uuid("/tmp/node_beta")
        assert uid1 != uid2


class TestSysStateErrorScenarios:
    """Error and failure scenarios for SystemState."""

    def test_read_yaml_returns_empty_dict_for_missing_file(self, isolated_sysstate):
        """read_yaml returns {} for a path that does not exist."""
        path = isolated_sysstate / "nonexistent.yaml"
        assert SystemState.read_yaml(path) == {}

    def test_read_yaml_returns_empty_dict_for_corrupt_yaml(self, isolated_sysstate, tmp_path):
        """read_yaml returns {} when the YAML file is unreadable or corrupt."""
        corrupt = isolated_sysstate / "corrupt.yaml"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_text(": !! invalid_yaml: [[[", encoding="utf-8")
        assert SystemState.read_yaml(corrupt) == {}

    def test_read_bkp_config_returns_none_when_uuid_registered_but_file_missing(
        self, isolated_sysstate
    ):
        """read_bkp_config returns None if UUID exists but the bkp file was deleted."""
        node_path = "/tmp/orphan_uuid_node"
        uid = SystemState.assign_uuid(node_path)
        bkp = SystemState.bkp_path(uid)
        # Don't write the bkp file → should return None gracefully
        result = SystemState.read_bkp_config(node_path)
        assert result is None


class TestSysStateAdversarialScenarios:
    """Adversarial and edge-case scenarios for SystemState."""

    def test_path_with_traversal_characters_stored_verbatim(self, isolated_sysstate):
        """Node paths with traversal characters are stored as-is, not resolved."""
        node_path = "/tmp/../../etc/passwd"
        SystemState.mark_autoremoved(node_path)

        entries = SystemState.read_yaml(SystemState.removed_path())
        assert f"{node_path} --autoremoved" in entries
        # The actual removed.yaml file must still be under the isolated base dir
        assert str(isolated_sysstate) in str(SystemState.removed_path())

    def test_unicode_path_handled_correctly(self, isolated_sysstate):
        """Node paths containing unicode characters are stored and retrieved correctly."""
        node_path = "/tmp/nódö_üñíçödé"
        uid = SystemState.assign_uuid(node_path)
        assert SystemState.get_uuid(node_path) == uid

    def test_very_long_node_path_stored_correctly(self, isolated_sysstate):
        """A very long node path string is handled without truncation."""
        node_path = "/tmp/" + "a" * 200
        SystemState.mark_autoremoved(node_path)
        entries = SystemState.read_yaml(SystemState.removed_path())
        assert f"{node_path} --autoremoved" in entries
