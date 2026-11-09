#!/usr/bin/env bash
# Minimal self-test for json_dot.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
CLI=(python3 "$ROOT/json_dot.py")
DEMO="$ROOT/demo.json"
PASS=0
FAIL=0

check() {
  local name="$1" expect="$2"
  shift 2
  set +e
  out="$("${CLI[@]}" "$@" 2>&1)"
  code=$?
  set -e
  if [[ "$code" -eq "$expect" ]]; then
    echo "PASS: $name (exit $code)"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name (want exit $expect, got $code)"
    echo "$out"
    FAIL=$((FAIL + 1))
  fi
}

# 1) flatten nested object + array
set +e
flat_out="$("${CLI[@]}" flatten "$DEMO" 2>&1)"
flat_code=$?
set -e
if [[ "$flat_code" -eq 0 ]] && echo "$flat_out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
expect = {
    "items.0.id": 1,
    "items.0.name": "Oak Desk",
    "items.0.price": 199.5,
    "items.1.id": 2,
    "items.1.name": "Pine Shelf",
    "items.1.tags.0": "wood",
    "items.1.tags.1": "home",
    "meta.note": None,
    "meta.version": 1,
    "store.name": "Northwind Demo Shop",
    "store.open": True,
}
assert d == expect, d
'; then
  echo "PASS: flatten nested object+array"
  PASS=$((PASS + 1))
else
  echo "FAIL: flatten nested object+array"
  echo "$flat_out"
  FAIL=$((FAIL + 1))
fi

# 2) unflatten back to equivalent structure (file and stdin)
set +e
round_out="$("${CLI[@]}" flatten "$DEMO" | "${CLI[@]}" unflatten 2>&1)"
round_code=$?
set -e
if [[ "$round_code" -eq 0 ]] && echo "$round_out" | python3 -c '
import json, sys
from pathlib import Path
got = json.load(sys.stdin)
src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert got == src, (got, src)
' "$DEMO"; then
  echo "PASS: unflatten round-trip"
  PASS=$((PASS + 1))
else
  echo "FAIL: unflatten round-trip"
  echo "$round_out"
  FAIL=$((FAIL + 1))
fi

# 3) custom --sep
set +e
sep_out="$("${CLI[@]}" flatten "$DEMO" --sep / 2>&1)"
sep_code=$?
set -e
if [[ "$sep_code" -eq 0 ]] && echo "$sep_out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert "store/name" in d
assert "items/0/name" in d
assert "items/1/tags/0" in d
assert "store.name" not in d
assert d["store/name"] == "Northwind Demo Shop"
assert d["items/1/tags/1"] == "home"
'; then
  echo "PASS: custom --sep"
  PASS=$((PASS + 1))
else
  echo "FAIL: custom --sep"
  echo "$sep_out"
  FAIL=$((FAIL + 1))
fi

# custom sep also round-trips
set +e
sep_round="$("${CLI[@]}" flatten "$DEMO" --sep / | "${CLI[@]}" unflatten --sep / 2>&1)"
sep_round_code=$?
set -e
if [[ "$sep_round_code" -eq 0 ]] && echo "$sep_round" | python3 -c '
import json, sys
from pathlib import Path
got = json.load(sys.stdin)
src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert got == src
' "$DEMO"; then
  echo "PASS: custom --sep round-trip"
  PASS=$((PASS + 1))
else
  echo "FAIL: custom --sep round-trip"
  echo "$sep_round"
  FAIL=$((FAIL + 1))
fi

# 4) bad JSON / conflict keys -> non-zero
set +e
bad_out="$(printf '{bad' | "${CLI[@]}" flatten 2>&1)"
bad_code=$?
set -e
if [[ "$bad_code" -eq 2 ]] && echo "$bad_out" | grep -q 'invalid JSON'; then
  echo "PASS: bad JSON (exit $bad_code)"
  PASS=$((PASS + 1))
else
  echo "FAIL: bad JSON (want exit 2 + invalid JSON, got $bad_code)"
  echo "$bad_out"
  FAIL=$((FAIL + 1))
fi

set +e
conflict_out="$(printf '%s\n' '{"a":1,"a.b":2}' | "${CLI[@]}" unflatten 2>&1)"
conflict_code=$?
set -e
if [[ "$conflict_code" -eq 2 ]] && echo "$conflict_out" | grep -q 'path conflict'; then
  echo "PASS: leaf/object conflict (exit $conflict_code)"
  PASS=$((PASS + 1))
else
  echo "FAIL: leaf/object conflict (want exit 2 + path conflict, got $conflict_code)"
  echo "$conflict_out"
  FAIL=$((FAIL + 1))
fi

set +e
mix_out="$(printf '%s\n' '{"a.0":1,"a.x":2}' | "${CLI[@]}" unflatten 2>&1)"
mix_code=$?
set -e
if [[ "$mix_code" -eq 2 ]] && echo "$mix_out" | grep -q 'path conflict'; then
  echo "PASS: array/object conflict (exit $mix_code)"
  PASS=$((PASS + 1))
else
  echo "FAIL: array/object conflict (want exit 2 + path conflict, got $mix_code)"
  echo "$mix_out"
  FAIL=$((FAIL + 1))
fi

# extras that should stay green
check "missing file" 2 flatten "$ROOT/no-such-file.json"
check "key contains separator" 2 flatten <(printf '%s\n' '{"a.b":1}')

# top-level array round-trip
set +e
arr_out="$(printf '%s\n' '[{"name":"Ada"},{"name":"Bob"}]' | "${CLI[@]}" flatten | "${CLI[@]}" unflatten 2>&1)"
arr_code=$?
set -e
if [[ "$arr_code" -eq 0 ]] && echo "$arr_out" | python3 -c '
import json, sys
assert json.load(sys.stdin) == [{"name":"Ada"},{"name":"Bob"}]
'; then
  echo "PASS: top-level array round-trip"
  PASS=$((PASS + 1))
else
  echo "FAIL: top-level array round-trip"
  echo "$arr_out"
  FAIL=$((FAIL + 1))
fi

echo "---"
echo "passed=$PASS failed=$FAIL"
[[ "$FAIL" -eq 0 ]]
