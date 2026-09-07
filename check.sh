#!/usr/bin/env bash
# Run both implementations against each other. This is the check that matters:
# either verifier passing alone proves much less than the two agreeing.
set -euo pipefail
cd "$(dirname "$0")"

echo "== regenerating cross-implementation vectors =="
.venv/bin/python core/tools/gen_vectors.py

echo
echo "== python =="
.venv/bin/python -m pytest core -q

echo
echo "== dart =="
(cd dart/ftr_verify && dart test --reporter=failures-only && echo "dart: all tests passed")

echo
echo "== both verifiers on the same chain =="
rm -rf /tmp/ftr-crosscheck
.venv/bin/python core/demo.py --keep /tmp/ftr-crosscheck >/dev/null
py=$(.venv/bin/ftrverify chain /tmp/ftr-crosscheck/chain | tail -2 | head -1)
da=$(cd dart/ftr_verify && dart run bin/ftrverify.dart chain /tmp/ftr-crosscheck/chain | tail -2 | head -1)
echo "  python: $py"
echo "  dart:   $da"
[ "$py" = "$da" ] || { echo "VERDICTS DISAGREE — this is the failure the two implementations exist to catch"; exit 1; }
echo "  verdicts agree"
