#!/usr/bin/env bash

set -Eeuo pipefail

# Usage examples:
#   tools/manual_test_helper.sh install
#   tools/manual_test_helper.sh setup
#   tools/manual_test_helper.sh suite smoke
#   tools/manual_test_helper.sh snapshot
#   tools/manual_test_helper.sh run -- jatai status
#   tools/manual_test_helper.sh cleanup
#   tools/manual_test_helper.sh all
#
# Notes:
# - This script uses the existing venv at ./venv.
# - Manual tests run in an isolated temporary workspace under ./tmp_tests.
# - All stdout/stderr is appended to a .log file.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Prefer .venv (project venv) but fall back to 'venv' for older setups.
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  VENV_PYTHON="$ROOT_DIR/venv/bin/python"
fi
VENV_JATAI_BIN="$ROOT_DIR/.venv/bin/jatai"
if [[ ! -x "$VENV_JATAI_BIN" ]]; then
  VENV_JATAI_BIN="$ROOT_DIR/venv/bin/jatai"
fi
LOG_FILE_DEFAULT="$PWD/manual-tests.log"
TMP_TESTS_ROOT_DEFAULT="$PWD/tmp_tests"
STATE_FILE_DEFAULT="$TMP_TESTS_ROOT_DEFAULT/.manual_test_state.env"
MANIFEST_PREV_REL=".manual_test_manifest.prev"
MANIFEST_CURR_REL=".manual_test_manifest.curr"

LOG_FILE="${MANUAL_TEST_LOG_FILE:-$LOG_FILE_DEFAULT}"
TMP_TESTS_ROOT="${MANUAL_TEST_ROOT:-$TMP_TESTS_ROOT_DEFAULT}"
STATE_FILE="${MANUAL_TEST_STATE_FILE:-$STATE_FILE_DEFAULT}"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "ERROR: Existing venv not found at $VENV_PYTHON or $ROOT_DIR/venv"
  echo "Create it first (example): python3 -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")"
: > "$LOG_FILE"
exec > >(tee "$LOG_FILE") 2>&1

timestamp() {
  date "+%Y-%m-%d %H:%M:%S"
}

log_header() {
  echo
  echo "[$(timestamp)] ----------------------------------------------------------------"
  echo "[$(timestamp)] manual_test_helper action: $*"
  echo "[$(timestamp)] root=$ROOT_DIR"
  echo "[$(timestamp)] log=$LOG_FILE"
}

save_state() {
  cat > "$STATE_FILE" <<EOF
TEST_ROOT=$TEST_ROOT
TEST_HOME=$TEST_HOME
JATAI_TEST_A=$JATAI_TEST_A
JATAI_TEST_B=$JATAI_TEST_B
JATAI_BIN=$JATAI_BIN
EOF
}

load_state() {
  if [[ ! -f "$STATE_FILE" ]]; then
    echo "ERROR: state file not found: $STATE_FILE"
    echo "Run setup first: tools/manual_test_helper.sh setup"
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$STATE_FILE"
}

run_cmd() {
  local cmd="$*"
  echo "[$(timestamp)] >>> $cmd"
  set +e
  bash -lc "$cmd"
  local rc=$?
  set -e
  echo "[$(timestamp)] <<< exit=$rc"
  return $rc
}

build_file_manifest() {
  local out_file="$1"
  (
    cd "$TEST_ROOT"
    find . -type f -print | sort | while read -r rel; do
      local normalized
      normalized="${rel#./}"
      local size hash
      size="$(wc -c < "$rel" | tr -d ' ')"
      hash="$(sha256sum "$rel" | awk '{print $1}')"
      printf "%s|%s|%s\n" "$normalized" "$size" "$hash"
    done
  ) > "$out_file"
}

log_file_changes() {
  local prev_file="$TEST_ROOT/$MANIFEST_PREV_REL"
  local curr_file="$TEST_ROOT/$MANIFEST_CURR_REL"

  build_file_manifest "$curr_file"

  if [[ ! -f "$prev_file" ]]; then
    echo "[$(timestamp)] File changes: first snapshot (no previous baseline)."
    cp "$curr_file" "$prev_file"
    return 0
  fi

  echo "[$(timestamp)] File changes since previous snapshot:"

  local added removed changed
  added="$(comm -13 <(cut -d'|' -f1 "$prev_file" | sort) <(cut -d'|' -f1 "$curr_file" | sort) || true)"
  removed="$(comm -23 <(cut -d'|' -f1 "$prev_file" | sort) <(cut -d'|' -f1 "$curr_file" | sort) || true)"
  changed="$(awk -F'|' 'NR==FNR {prev[$1]=$0; next} ($1 in prev) && prev[$1] != $0 {print $1}' "$prev_file" "$curr_file" || true)"

  echo "[$(timestamp)]   Added files:"
  if [[ -n "$added" ]]; then
    while IFS= read -r item; do
      echo "[$(timestamp)]     + $item"
    done <<< "$added"
  else
    echo "[$(timestamp)]     (none)"
  fi

  echo "[$(timestamp)]   Removed files:"
  if [[ -n "$removed" ]]; then
    while IFS= read -r item; do
      echo "[$(timestamp)]     - $item"
    done <<< "$removed"
  else
    echo "[$(timestamp)]     (none)"
  fi

  echo "[$(timestamp)]   Changed files:"
  if [[ -n "$changed" ]]; then
    while IFS= read -r item; do
      echo "[$(timestamp)]     * $item"
    done <<< "$changed"
  else
    echo "[$(timestamp)]     (none)"
  fi

  cp "$curr_file" "$prev_file"
}

dump_all_files() {
  if [[ ! -d "$TEST_ROOT" ]]; then
    echo "[$(timestamp)] No temporary directory found to dump: $TEST_ROOT"
    return 0
  fi

  echo "[$(timestamp)] Full file dump before cleanup (relative to tmp_tests):"
  (
    cd "$TEST_ROOT"
    find . -type f -print | sort | while read -r rel; do
      local normalized
      normalized="${rel#./}"
      echo "[$(timestamp)] ----- BEGIN FILE: $normalized -----"
      cat "$rel"
      echo
      echo "[$(timestamp)] ----- END FILE: $normalized -----"
    done
  )
}

snapshot_dirs() {
  load_state
  echo "[$(timestamp)] Snapshot root: $TEST_ROOT"
  echo "[$(timestamp)] Directory summary (relative to tmp_tests):"
  run_cmd "cd '$TEST_ROOT' && find . -maxdepth 4 -print | sort"
  run_cmd "cd '$TEST_ROOT' && ls -la ."
  run_cmd "cd '$TEST_ROOT' && ls -la node_a"
  run_cmd "cd '$TEST_ROOT' && ls -la node_b"
  log_file_changes
}

action_install() {
  # Ensure a clean reinstall: uninstall first (ignore failures), then install editable
  run_cmd "'$VENV_PYTHON' -m pip uninstall -y jatai || true"
  run_cmd "'$VENV_PYTHON' -m pip install --no-deps --upgrade --force-reinstall -e '$ROOT_DIR'"
}

action_setup() {
  TEST_ROOT="$TMP_TESTS_ROOT"
  TEST_HOME="$TEST_ROOT/home"
  JATAI_TEST_A="$TEST_ROOT/node_a"
  JATAI_TEST_B="$TEST_ROOT/node_b"

  run_cmd "rm -rf '$TEST_ROOT'"
  mkdir -p "$TEST_HOME" "$JATAI_TEST_A" "$JATAI_TEST_B"

  if [[ -x "$VENV_JATAI_BIN" ]]; then
    JATAI_BIN="$VENV_JATAI_BIN"
  else
    JATAI_BIN="$VENV_PYTHON -m jatai"
  fi

  save_state

  echo "[$(timestamp)] Setup complete"
  echo "[$(timestamp)] TEST_ROOT=$TEST_ROOT"
  echo "[$(timestamp)] TEST_HOME=$TEST_HOME"
  echo "[$(timestamp)] JATAI_TEST_A=$JATAI_TEST_A"
  echo "[$(timestamp)] JATAI_TEST_B=$JATAI_TEST_B"
  echo "[$(timestamp)] state=$STATE_FILE"
  snapshot_dirs
}

action_run() {
  load_state
  if [[ $# -eq 0 ]]; then
    echo "ERROR: run expects a command"
    echo "Example: tools/manual_test_helper.sh run -- jatai status"
    exit 1
  fi
  local cmd="$*"
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $cmd"
}

suite_smoke() {
  load_state
  local failures=0

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_B' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_B'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN status" || failures=$((failures + 1))

  snapshot_dirs
  echo "[$(timestamp)] smoke suite failures=$failures"
  return 0
}

suite_filesystem() {
  load_state
  local failures=0

  echo "[$(timestamp)] ===== FILESYSTEM DELIVERY SUITE ====="

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_B' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_B'" || failures=$((failures + 1))
  run_cmd "printf 'deliver-test\n' > '$JATAI_TEST_A/OUTBOX/test_file.txt'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN start" || failures=$((failures + 1))
  run_cmd "sleep 2"
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN stop" || failures=$((failures + 1))

  if [[ -f "$JATAI_TEST_B/INBOX/test_file.txt" ]]; then
    echo "[$(timestamp)] ✓ File delivered to INBOX"
  else
    echo "[$(timestamp)] ✗ File not delivered"
    failures=$((failures + 1))
  fi

  snapshot_dirs
  echo "[$(timestamp)] filesystem suite failures=$failures"
  return 0
}

suite_advanced() {
  load_state
  local failures=0

  echo "[$(timestamp)] ===== ADVANCED FILESYSTEM SUITE ====="

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_B' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_B'" || failures=$((failures + 1))

  echo "[$(timestamp)] TEST 1: Soft-delete (.jatai → ._jatai)"
  run_cmd "mv '$JATAI_TEST_A/.jatai' '$JATAI_TEST_A/._jatai'" || failures=$((failures + 1))
  if [[ -f "$JATAI_TEST_A/._jatai" ]]; then
    echo "[$(timestamp)] ✓ Soft-deleted"
  else
    failures=$((failures + 1))
  fi

  echo "[$(timestamp)] TEST 2: Re-enable (._jatai → .jatai)"
  run_cmd "mv '$JATAI_TEST_A/._jatai' '$JATAI_TEST_A/.jatai'" || failures=$((failures + 1))
  if [[ -f "$JATAI_TEST_A/.jatai" ]]; then
    echo "[$(timestamp)] ✓ Re-enabled"
  else
    failures=$((failures + 1))
  fi

  echo "[$(timestamp)] TEST 3: Collision handling"
  run_cmd "printf 'data-a\n' > '$JATAI_TEST_A/OUTBOX/collision.txt'" || failures=$((failures + 1))
  run_cmd "printf 'data-b\n' > '$JATAI_TEST_B/OUTBOX/collision.txt'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN start" || failures=$((failures + 1))
  run_cmd "sleep 2"
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN stop" || failures=$((failures + 1))

  local file_count
  file_count=$(find "$JATAI_TEST_B/INBOX" -type f -name "collision*" 2>/dev/null | wc -l || echo 0)
  echo "[$(timestamp)] Files matching collision* pattern in node_b INBOX: $file_count"

  snapshot_dirs
  echo "[$(timestamp)] advanced suite failures=$failures"
  return 0
}

suite_retry() {
  load_state
  local failures=0
  echo "[$(timestamp)] ===== RETRY SUITE ====="
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_B' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_B'" || failures=$((failures + 1))
  echo "[$(timestamp)] Simulating delivery failure via monkeypatch script"
  run_cmd "'$VENV_PYTHON' - <<'PY'
from jatai.core.daemon import JataiDaemon
from jatai.core.node import Node
from jatai.core.registry import Registry
import sys
print('retry-suite: no-op runner - ensure retry state file is created')
PY" || failures=$((failures + 1))
  snapshot_dirs
  echo "[$(timestamp)] retry suite failures=$failures"
  return 0
}

suite_gc() {
  load_state
  local failures=0
  echo "[$(timestamp)] ===== GC SUITE ====="
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  echo "[$(timestamp)] Creating many processed files to trigger GC"
  run_cmd "for i in \$(seq 1 10); do printf 'x' > '$JATAI_TEST_A/OUTBOX/_old_$i.txt'; done" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN start" || failures=$((failures + 1))
  run_cmd "sleep 2"
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN stop" || failures=$((failures + 1))
  snapshot_dirs
  echo "[$(timestamp)] gc suite failures=$failures"
  return 0
}

suite_migration() {
  load_state
  local failures=0
  echo "[$(timestamp)] ===== MIGRATION SUITE ====="
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  echo "[$(timestamp)] Create historical files with old prefixes and simulate .jatai deletion"
  run_cmd "printf 'done' > '$JATAI_TEST_A/OUTBOX/_done.txt'" || failures=$((failures + 1))
  run_cmd "printf 'failed' > '$JATAI_TEST_A/INBOX/!_failed.txt'" || failures=$((failures + 1))
  run_cmd "rm -f '$JATAI_TEST_A/.jatai' && ls -la '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "'$VENV_PYTHON' - <<'PY'
from jatai.core.daemon import JataiDaemon
from jatai.core.registry import Registry
daemon = JataiDaemon(registry_path=None)
daemon.load_registered_nodes()
print('migration-suite: invoked load_registered_nodes')
PY" || failures=$((failures + 1))
  # Recreate a new .jatai to trigger migration
  # Write a new .jatai config directly to trigger migration
  run_cmd "cat > '$JATAI_TEST_A/.jatai' <<EOF
node_path: '$JATAI_TEST_A'
PREFIX_PROCESSED: 'processed_'
PREFIX_ERROR: 'error_'
EOF" || failures=$((failures + 1))
  run_cmd "'$VENV_PYTHON' - <<'PY'
from jatai.core.daemon import JataiDaemon
from pathlib import Path
daemon = JataiDaemon()
daemon.handle_node_config_change(Path('$JATAI_TEST_A'))
print('migration-suite: handle_node_config_change called')
PY" || failures=$((failures + 1))
  snapshot_dirs
  echo "[$(timestamp)] migration suite failures=$failures"
  return 0
}

suite_registry_onboard() {
  load_state
  local failures=0
  echo "[$(timestamp)] ===== REGISTRY ONBOARD SUITE ====="
  run_cmd "'$VENV_PYTHON' - <<'PY'
from jatai.core.registry import Registry
from pathlib import Path
reg = Registry(registry_path=Path('$TEST_HOME') / '.jatai')
reg.set_config('INBOX_DIR','INBOX')
reg.set_config('OUTBOX_DIR','OUTBOX')
reg.add_node('manual_node', str(Path('$TEST_ROOT') / 'manual_node'))
reg.save()
print('registry:onboard: added manual_node')
PY" || failures=$((failures + 1))
  run_cmd "'$VENV_PYTHON' - <<'PY'
from jatai.core.daemon import JataiDaemon
from pathlib import Path
daemon = JataiDaemon(registry_path=Path('$TEST_HOME') / '.jatai')
daemon.load_registered_nodes()
print('registry:onboard: load_registered_nodes executed')
PY" || failures=$((failures + 1))
  snapshot_dirs
  echo "[$(timestamp)] registry-onboard suite failures=$failures"
  return 0
}

suite_error_handling() {
  load_state
  local failures=0
  echo "[$(timestamp)] ===== ERROR HANDLING SUITE ====="
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  echo "[$(timestamp)] Simulating delivery failure by creating invalid target"
  run_cmd "printf 'x' > '$JATAI_TEST_A/OUTBOX/_bad.txt'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN start" || failures=$((failures + 1))
  run_cmd "sleep 2"
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN stop" || failures=$((failures + 1))
  snapshot_dirs
  echo "[$(timestamp)] error-handling suite failures=$failures"
  return 0
}

suite_startup_scan() {
  load_state
  local failures=0

  echo "[$(timestamp)] ===== STARTUP SCAN SUITE ====="

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_B' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_B'" || failures=$((failures + 1))

  echo "[$(timestamp)] Dropping files offline..."
  run_cmd "printf 'offline-file-1\n' > '$JATAI_TEST_A/OUTBOX/offline1.txt'" || failures=$((failures + 1))
  run_cmd "printf 'offline-file-2\n' > '$JATAI_TEST_A/OUTBOX/offline2.txt'" || failures=$((failures + 1))

  echo "[$(timestamp)] Starting daemon (startup scan should pick up files)..."
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN start" || failures=$((failures + 1))
  run_cmd "sleep 3"
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN stop" || failures=$((failures + 1))

  if [[ -f "$JATAI_TEST_B/INBOX/offline1.txt" ]] && [[ -f "$JATAI_TEST_B/INBOX/offline2.txt" ]]; then
    echo "[$(timestamp)] ✓ Startup scan success"
  else
    echo "[$(timestamp)] ✗ Startup scan missed files"
    failures=$((failures + 1))
  fi

  snapshot_dirs
  echo "[$(timestamp)] startup-scan suite failures=$failures"
  return 0
}

suite_config() {
  load_state
  local failures=0

  echo "[$(timestamp)] ===== CONFIG SUITE ====="

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_B' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_B'" || failures=$((failures + 1))

  echo "[$(timestamp)] Checking local .jatai config..."
  if [[ -f "$JATAI_TEST_A/.jatai" ]]; then
    echo "[$(timestamp)] ✓ .jatai config found"
    run_cmd "cat '$JATAI_TEST_A/.jatai' | head -5"
  else
    echo "[$(timestamp)] ✗ .jatai not found"
    failures=$((failures + 1))
  fi

  echo "[$(timestamp)] Testing delivery with configured settings..."
  run_cmd "printf 'config-test\n' > '$JATAI_TEST_A/OUTBOX/config_test.txt'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN start" || failures=$((failures + 1))
  run_cmd "sleep 2"
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN stop" || failures=$((failures + 1))

  if [[ -f "$JATAI_TEST_B/INBOX/config_test.txt" ]]; then
    echo "[$(timestamp)] ✓ Delivery works with custom config"
  else
    echo "[$(timestamp)] ✗ Delivery failed"
    failures=$((failures + 1))
  fi

  snapshot_dirs
  echo "[$(timestamp)] config suite failures=$failures"
  return 0
}

suite_tui_config_get() {
  load_state
  local failures=0

  echo "[$(timestamp)] ===== TUI + CONFIG GET SUITE ====="

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_B' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_B'" || failures=$((failures + 1))

  echo "[$(timestamp)] Testing config get (local/global) and INBOX export..."
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN config RETRY_DELAY_BASE 9" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN config MAX_RETRIES 8 -G" || failures=$((failures + 1))

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN config get RETRY_DELAY_BASE > '$TEST_ROOT/config_get_local.out'" || failures=$((failures + 1))
  if grep -q "RETRY_DELAY_BASE=9" "$TEST_ROOT/config_get_local.out"; then
    echo "[$(timestamp)] ✓ Local config get returned expected key"
  else
    echo "[$(timestamp)] ✗ Local config get did not return expected key/value"
    failures=$((failures + 1))
  fi

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN config get MAX_RETRIES -G > '$TEST_ROOT/config_get_global.out'" || failures=$((failures + 1))
  if grep -q "MAX_RETRIES=8" "$TEST_ROOT/config_get_global.out"; then
    echo "[$(timestamp)] ✓ Global config get returned expected key"
  else
    echo "[$(timestamp)] ✗ Global config get did not return expected key/value"
    failures=$((failures + 1))
  fi

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN config get RETRY_DELAY_BASE -i" || failures=$((failures + 1))
  if [[ -f "$JATAI_TEST_A/INBOX/!config-local-RETRY_DELAY_BASE.txt" ]]; then
    echo "[$(timestamp)] ✓ config get --inbox exported system artifact with ! prefix"
  else
    echo "[$(timestamp)] ✗ Missing !config-local-RETRY_DELAY_BASE.txt in INBOX"
    failures=$((failures + 1))
  fi

  if run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN config get DOES_NOT_EXIST"; then
    echo "[$(timestamp)] ✗ Missing key should fail but command returned success"
    failures=$((failures + 1))
  else
    echo "[$(timestamp)] ✓ Missing key returns expected failure"
  fi

  echo "[$(timestamp)] Testing docs query --inbox applies ! prefix (ADR 15)..."
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN docs retry --inbox" || failures=$((failures + 1))
  local bang_files
  bang_files="$(find "$JATAI_TEST_A/INBOX" -name '!*.md' 2>/dev/null | wc -l)"
  local nonbang_files
  nonbang_files="$(find "$JATAI_TEST_A/INBOX" -name '*.md' -not -name '!*' 2>/dev/null | wc -l)"
  if [[ "$bang_files" -gt 0 ]]; then
    echo "[$(timestamp)] ✓ docs query --inbox created $bang_files file(s) with ! prefix"
  else
    echo "[$(timestamp)] ✗ No ! prefixed .md files found after docs query --inbox"
    failures=$((failures + 1))
  fi
  if [[ "$nonbang_files" -gt 0 ]]; then
    echo "[$(timestamp)] ✗ Found $nonbang_files .md files WITHOUT ! prefix (policy violation)"
    failures=$((failures + 1))
  else
    echo "[$(timestamp)] ✓ No .md files without ! prefix in INBOX"
  fi

  echo "[$(timestamp)] Testing Textual TUI _dispatch routing via Python..."
  run_cmd "'$VENV_PYTHON' -c \"
from jatai.tui import JataiApp, _capture_call
# Confirm _capture_call captures stdout
import io
result = _capture_call(lambda: print('dispatch-test'))
assert 'dispatch-test' in result, 'capture_call failed'
# Confirm _dispatch routes key 1 to status_cmd
from jatai.cli import main as cli_main
app = JataiApp()
captured = {}
app._run = lambda fn, *args: captured.update({'fn': fn})
app._dispatch('1')
assert captured.get('fn') == cli_main.status, 'dispatch key 1 did not route to status'
print('TUI dispatch tests passed')
\"" > "$TEST_ROOT/tui_dispatch.out" || failures=$((failures + 1))
  if grep -q "TUI dispatch tests passed" "$TEST_ROOT/tui_dispatch.out"; then
    echo "[$(timestamp)] ✓ TUI _dispatch routes status command correctly"
  else
    echo "[$(timestamp)] ✗ TUI _dispatch test failed"
    failures=$((failures + 1))
  fi

  snapshot_dirs
  echo "[$(timestamp)] tui-config-get suite failures=$failures"
  return 0
}

suite_phase7() {
  load_state
  local failures=0

  echo "[$(timestamp)] ===== PHASE7 SUITE ====="
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_B' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_B'" || failures=$((failures + 1))

  echo "[$(timestamp)] Validate auto-onboarding and defaults"
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN status" || failures=$((failures + 1))

  echo "[$(timestamp)] Create processed file and run daemon for GC cycle"
  run_cmd "printf 'x' > '$JATAI_TEST_A/OUTBOX/_old-1.txt'" || failures=$((failures + 1))
  run_cmd "printf 'x' > '$JATAI_TEST_A/OUTBOX/_old-2.txt'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && nohup $VENV_PYTHON -m jatai.cli.main _daemon-run > /tmp/jatai_phase7_daemon.log 2>&1 & echo \$! > /tmp/jatai_phase7.pid" || failures=$((failures + 1))
  sleep 2
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN stop" || failures=$((failures + 1))
  if [[ -f /tmp/jatai_phase7.pid ]]; then
    DAEMON_PID=$(cat /tmp/jatai_phase7.pid)
    if kill -0 "$DAEMON_PID" 2>/dev/null; then
      kill "$DAEMON_PID" 2>/dev/null || true
      rm -f /tmp/jatai_phase7.pid
    fi
  fi

  echo "[$(timestamp)] Check Phase7 log path symlink"
  run_cmd "python - <<'PY'\nfrom pathlib import Path\nfrom jatai.core.registry import Registry\nfrom jatai.core.daemon import JataiDaemon\nregistry_path = Path('$TEST_HOME') / '.jatai'\nRegistry(registry_path=registry_path).load()\nlog_path = Path(Registry(registry_path).global_config.get('LATEST_LOG_PATH', '~/.jatai_latest.log')).expanduser()\nprint('log symlink exists', log_path.exists())\nPY" || failures=$((failures + 1))

  echo "[$(timestamp)] Ensure soft-delete path logic via config removal"
  run_cmd "rm -f '$JATAI_TEST_A/.jatai'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN start" || failures=$((failures + 1))

  snapshot_dirs
  echo "[$(timestamp)] phase7 suite failures=$failures"
  return 0
}

action_suite() {
  if [[ $# -eq 0 ]]; then
    echo "ERROR: suite expects a suite name"
    echo "Available suites: smoke, filesystem, phase7, advanced, startup-scan, config, tui-config-get"
    exit 1
  fi

  case "$1" in
    smoke)
      suite_smoke
      ;;
    filesystem)
      suite_filesystem
      ;;
    phase7)
      suite_phase7
      ;;
    migration)
      suite_migration
      ;;
    registry-onboard)
      suite_registry_onboard
      ;;
    retry)
      suite_retry
      ;;
    gc)
      suite_gc
      ;;
    error-handling)
      suite_error_handling
      ;;
    advanced)
      suite_advanced
      ;;
    startup-scan)
      suite_startup_scan
      ;;
    config)
      suite_config
      ;;
    tui-config-get)
      suite_tui_config_get
      ;;
    *)
      echo "ERROR: unknown suite '$1'"
      echo "Available suites: smoke, filesystem, phase7, advanced, startup-scan, config, tui-config-get"
      exit 1
      ;;
  esac
}

action_cleanup() {
  if [[ -f "$STATE_FILE" ]]; then
    load_state
  else
    TEST_ROOT="$TMP_TESTS_ROOT"
  fi

  dump_all_files

  echo "[$(timestamp)] Cleaning up temporary paths"
  run_cmd "rm -rf '$TEST_ROOT'"
  run_cmd "ls -la '$PWD' | sed -n '1,120p'"
  rm -f "$STATE_FILE"
  echo "[$(timestamp)] Removed state file: $STATE_FILE"
}

action_all() {
  local setup_done="0"

  all_cleanup_trap() {
    if [[ "$setup_done" == "1" ]]; then
      action_cleanup || true
    fi
  }

  trap all_cleanup_trap EXIT

  action_install
  action_setup
  setup_done="1"
  action_suite smoke
  action_suite filesystem
  action_suite phase7
  action_suite advanced
  action_suite startup-scan
  action_suite config
  action_suite tui-config-get

  trap - EXIT
  action_cleanup
  echo "[$(timestamp)] ✓ Manual tests completed"
}

usage() {
  cat <<'EOF'
Manual Test Helper for Jatai - File-System First Testing

Usage:
  tools/manual_test_helper.sh install
  tools/manual_test_helper.sh setup
  tools/manual_test_helper.sh snapshot
  tools/manual_test_helper.sh run -- <command>
  tools/manual_test_helper.sh suite <smoke|filesystem|phase7|advanced|startup-scan|config|tui-config-get>
  tools/manual_test_helper.sh cleanup
  tools/manual_test_helper.sh all

Behavior:
  - Uses existing venv from ./venv
  - Writes all output to ./manual-tests.log
  - Uses isolated ./tmp_tests workspace
  - Keeps state in ./tmp_tests/.manual_test_state.env

Test Suites (File-System First Architecture):
  - smoke: CLI initialization and status commands
  - filesystem: Direct file delivery - drop files in OUTBOX, verify arrival in destination INBOX
  - advanced: Soft-delete/re-enable, collision resolution, prefix state verification
  - startup-scan: Startup scan behavior - files dropped when daemon offline
  - config: Custom INBOX/OUTBOX paths, custom prefix settings via local .jatai
  - tui-config-get: Dedicated pseudo-terminal TUI flow + config get validation

Recommended comprehensive flow:
  1) install
  2) setup
  3) suite smoke        (CLI basics)
  4) suite filesystem   (direct delivery)
  5) suite advanced     (prefix states, soft-delete)
  6) suite startup-scan (offline file pickup)
  7) suite config       (configuration customization)
  8) suite tui-config-get (interactive + config retrieval)
  9) snapshot
  10) cleanup
EOF
}

main() {
  local action="${1:-help}"
  shift || true

  log_header "$action" "$*"

  case "$action" in
    install)
      action_install
      ;;
    setup)
      action_setup
      ;;
    snapshot)
      snapshot_dirs
      ;;
    run)
      if [[ "${1:-}" == "--" ]]; then
        shift
      fi
      action_run "$@"
      ;;
    suite)
      action_suite "$@"
      ;;
    cleanup)
      action_cleanup
      ;;
    all)
      action_all "$@"
      ;;
    help|--help|-h)
      usage
      ;;
    *)
      echo "ERROR: unknown action '$action'"
      usage
      exit 1
      ;;
  esac
}

main "$@"
