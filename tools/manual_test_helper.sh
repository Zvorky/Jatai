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
VENV_PYTHON="$ROOT_DIR/venv/bin/python"
VENV_JATAI_BIN="$ROOT_DIR/venv/bin/jatai"
LOG_FILE_DEFAULT="$PWD/manual-tests.log"
TMP_TESTS_ROOT_DEFAULT="$PWD/tmp_tests"
STATE_FILE_DEFAULT="$TMP_TESTS_ROOT_DEFAULT/.manual_test_state.env"
MANIFEST_PREV_REL=".manual_test_manifest.prev"
MANIFEST_CURR_REL=".manual_test_manifest.curr"

LOG_FILE="${MANUAL_TEST_LOG_FILE:-$LOG_FILE_DEFAULT}"
TMP_TESTS_ROOT="${MANUAL_TEST_ROOT:-$TMP_TESTS_ROOT_DEFAULT}"
STATE_FILE="${MANUAL_TEST_STATE_FILE:-$STATE_FILE_DEFAULT}"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "ERROR: Existing venv not found at $VENV_PYTHON"
  echo "Create it first (example): python3 -m venv venv"
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
  run_cmd "'$VENV_PYTHON' -m pip install -e '$ROOT_DIR'"
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

  # v0.6 TODO scope (kept commented until implemented):
  # run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN docs" || failures=$((failures + 1))
  # run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN docs init" || failures=$((failures + 1))
  # run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN log" || failures=$((failures + 1))
  # run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN log --all" || failures=$((failures + 1))

  snapshot_dirs
  echo "[$(timestamp)] smoke suite failures=$failures"
  return 0
}

suite_filesystem() {
  load_state
  local failures=0

  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_A'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_B' && export HOME='$TEST_HOME' && $JATAI_BIN init '$JATAI_TEST_B'" || failures=$((failures + 1))
  run_cmd "printf 'manual test payload\n' > '$JATAI_TEST_A/OUTBOX/manual_payload.txt'" || failures=$((failures + 1))
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN start" || failures=$((failures + 1))
  run_cmd "sleep 2"
  run_cmd "cd '$JATAI_TEST_A' && export HOME='$TEST_HOME' && $JATAI_BIN stop" || failures=$((failures + 1))

  snapshot_dirs
  echo "[$(timestamp)] filesystem suite failures=$failures"
  return 0
}

action_suite() {
  if [[ $# -eq 0 ]]; then
    echo "ERROR: suite expects a suite name"
    echo "Available suites: smoke, filesystem"
    exit 1
  fi

  case "$1" in
    smoke)
      suite_smoke
      ;;
    filesystem)
      suite_filesystem
      ;;
    *)
      echo "ERROR: unknown suite '$1'"
      echo "Available suites: smoke, filesystem"
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

  trap - EXIT
  action_cleanup
}

usage() {
  cat <<'EOF'
Manual Test Helper for Jatai

Usage:
  tools/manual_test_helper.sh install
  tools/manual_test_helper.sh setup
  tools/manual_test_helper.sh snapshot
  tools/manual_test_helper.sh run -- <command>
  tools/manual_test_helper.sh suite <smoke|filesystem>
  tools/manual_test_helper.sh cleanup
  tools/manual_test_helper.sh all

Behavior:
  - Uses existing venv from ./venv
  - Writes all output to ./manual-tests.log in the current working directory by default (or MANUAL_TEST_LOG_FILE)
  - Uses isolated ./tmp_tests workspace and HOME in the current working directory
  - Keeps state in ./tmp_tests/.manual_test_state.env to allow split test steps (setup/suite/cleanup)

Recommended flow:
  1) install
  2) setup
  3) suite smoke
  4) suite filesystem
  5) snapshot
  6) cleanup
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
