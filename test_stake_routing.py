"""
Dry-run verification for Stake platform detection refactor.
Tests _detect_stake_platform_from_source_and_code directly (no Discord/DB needed).
Run: python test_stake_routing.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Import only the detection helper and Platform enum
from scrapers.telegram import _detect_stake_platform_from_source_and_code
from models import Platform

CASES = [
    # (description, text, code, expected_platform)
    # ── Required cases ──────────────────────────────────────────────────────
    ("1. SPIKEUS code + TheSpike.gg source + STAKE.US keyword",
     "Code: SPIKEUS3Lz7N4q1\nSource: TheSpike.gg\nSTAKE.US",
     "SPIKEUS3Lz7N4q1", Platform.STAKE_US),

    ("2. CHAMP code + GameChampions US source + STAKE.US keyword",
     "Code: CHAMP8K4L9201\nSource: GameChampions US\nSTAKE.US",
     "CHAMP8K4L9201", Platform.STAKE_US),

    ("3. CHAMP code + GameChampions (no US) source + STAKE.COM keyword",
     "Code: CHAMP6Y2N8140\nSource: GameChampions\nSTAKE.COM",
     "CHAMP6Y2N8140", Platform.STAKE_COM),

    ("4. BIL code + Ballislife source + STAKE.US keyword",
     "Code: BILJ3Z3WKF\nSource: Ballislife\nSTAKE.US",
     "BILJ3Z3WKF", Platform.STAKE_US),

    ("5. Generic code + FreeTips source + STAKE.COM keyword",
     "Code: ThanksgivingGold\nSource: FreeTips\nSTAKE.COM",
     "ThanksgivingGold", Platform.STAKE_COM),

    ("6. ESBCOM code + EsportsBetting COM source + STAKE.COM keyword",
     "Code: ESBCOM158ELITERUSH6\nSource: EsportsBetting COM\nSTAKE.COM",
     "ESBCOM158ELITERUSH6", Platform.STAKE_COM),

    ("7. ESBUS code + EsportsBetting source + STAKE.US keyword",
     "Code: ESBUS158ELITERUSH6\nSource: EsportsBetting\nSTAKE.US",
     "ESBUS158ELITERUSH6", Platform.STAKE_US),

    # ── Non-regression: non-Stake platforms must return None ────────────────
    ("8. Shuffle.us message → None (no Stake signal)",
     "Shuffle.us Bonus Drop\nCode: ABCD1234",
     "ABCD1234", None),

    ("9. Shuffle.com message → None",
     "Shuffle.com Chat Code\nCode: XYZ9876",
     "XYZ9876", None),

    ("10. Rainbet message → None",
     "Rainbet Drop\nCode: MFQP3DSN",
     "MFQP3DSN", None),

    ("11. Degen message → None",
     "Degen Drop\nCode: DEGEN123",
     "DEGEN123", None),

    ("12. Qzino message → None",
     "Qzino Bonus\nCode: QZ12345",
     "QZ12345", None),

    # ── Step 1 keyword-only (no source line, no code prefix) ────────────────
    ("13. stake.us keyword only → STAKE_US",
     "Stake.us Bonus Drop Alert\nCode: RANDOMCODE",
     "RANDOMCODE", Platform.STAKE_US),

    ("14. stake.com keyword only → STAKE_COM",
     "Stake.com Bonus Drop Alert\nCode: RANDOMCODE",
     "RANDOMCODE", Platform.STAKE_COM),

    ("15. Both stake.us AND stake.com → None (dual, caller handles)",
     "Valid on stake.us and stake.com\nCode: DUALCODE",
     "DUALCODE", None),

    # ── Step 2 source-only (no keyword in text) ──────────────────────────────
    ("16. VegasInsider source → STAKE_US",
     "Source: VegasInsider\nCode: VEGASCODE",
     "VEGASCODE", Platform.STAKE_US),

    ("17. Deadspin source → STAKE_US",
     "Source: Deadspin\nCode: DEADSPINCODE",
     "DEADSPINCODE", Platform.STAKE_US),

    # ── Step 3 code-prefix only (no keyword, no source) ─────────────────────
    ("18. ESBCOM prefix alone → STAKE_COM",
     "Bonus drop code below",
     "ESBCOM999XYZ", Platform.STAKE_COM),

    ("19. ESBUS prefix alone → STAKE_US",
     "Bonus drop code below",
     "ESBUS999XYZ", Platform.STAKE_US),

    ("20. CHAMP prefix, no source → STAKE_COM (default)",
     "Bonus drop code below",
     "CHAMPABCD1234", Platform.STAKE_COM),
]

passed = failed = 0
for desc, text, code, expected in CASES:
    got = _detect_stake_platform_from_source_and_code(text, code)
    ok = got == expected
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {desc}")
    if not ok:
        print(f"         expected={expected}  got={got}")
        failed += 1
    else:
        passed += 1

print(f"\n{'='*60}")
print(f"  Results: {passed} passed, {failed} failed out of {len(CASES)} cases")
print(f"{'='*60}")
sys.exit(0 if failed == 0 else 1)
