#!/bin/bash
# Alle Tests ohne Hardware. Aufruf im Projektordner:  bash tests/run_all.sh
cd "$(dirname "$0")/.." || exit 1
fail=0
echo "== Dateipruefung (YAML, Adressen, Kanaele)"
(cd pi && python3 phase2_test.py --check) || fail=1
for t in tests/test_*.py; do
  echo; echo "== $t"
  python3 "$t" || fail=1
done
echo; [ $fail -eq 0 ] && echo "ALLES IN ORDNUNG" || { echo "FEHLER, siehe oben"; exit 1; }
