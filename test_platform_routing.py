"""
test_platform_routing.py
========================
Full verification suite for the Leaked.GG platform classification upgrade.
Covers:
  - All 52 historical Stake.us / Stake.com drops (zero Shuffle misclassifications)
  - All 13 platforms route to correct platform_id and claim URL
  - Goated / Degen OCR banner extraction (simulated)
  - Placeholder suppression
  - source_history.json auto-learning

Run: python test_platform_routing.py
"""

import os
import sys
import json
import re
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from platform_rules import (
    classify_platform,
    get_claim_url,
    get_claim_note,
    learn_source,
    _load_history,
    _HISTORY_PATH,
)
from scrapers.ocr import extract_banner_drop_details, _normalize_ocr_line

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
passed = failed = 0


def check(label: str, got, expected):
    global passed, failed
    ok = got == expected
    tag = "PASS" if ok else "FAIL"
    if not ok:
        print(f"  [FAIL] {label}")
        print(f"         expected={expected!r}  got={got!r}")
        failed += 1
    else:
        passed += 1
    return ok


# ===========================================================================
# Part 1 — Stake.us historical drops (41 cases)
# ===========================================================================
print("\n=== Part 1a: Stake.us historical drops ===")

STAKE_US_CASES = [
    # Ballislife
    ("BILJ3Z3WKF", "Code: BILJ3Z3WKF\nSource: Ballislife\nSTAKE.US"),
    ("BILX9K2MNPQ", "Code: BILX9K2MNPQ\nSource: Ballislife"),
    ("BIL4A7BVWXY", "Code: BIL4A7BVWXY\nSource: Ballislife"),
    # TheSpike.gg
    ("SPIKEUS3Lz7N4q1", "Code: SPIKEUS3Lz7N4q1\nSource: TheSpike.gg\nSTAKE.US"),
    ("SPIKEUSab12cd34", "Code: SPIKEUSab12cd34\nSource: TheSpike.gg"),
    # VegasInsider
    ("stakeus1a2b3c4d5e6f", "Code: stakeus1a2b3c4d5e6f\nSource: VegasInsider"),
    ("stakeusabcdef123456", "Code: stakeusabcdef123456\nSource: VegasInsider"),
    # EsportsBetting US
    ("ESBUS158ELITERUSH6", "Code: ESBUS158ELITERUSH6\nSource: EsportsBetting\nSTAKE.US"),
    ("ESBUS999XYZ", "Code: ESBUS999XYZ\nSource: EsportsBetting"),
    ("ESBUS2024GOLD", "Code: ESBUS2024GOLD\nSource: EsportsBetting"),
    # SportsGrid
    ("SPORTSGR2024BONUS", "Code: SPORTSGR2024BONUS\nSource: SportsGrid Stake.us"),
    ("SGRID2024DROP", "Code: SGRID2024DROP\nSource: SportsGrid Stake.us"),
    ("SG99BONUS", "Code: SG99BONUS\nSource: SportsGrid Stake.us"),
    # Deadspin
    ("DSN1234567", "Code: DSN1234567\nSource: Deadspin"),
    ("DSN9876ABCD", "Code: DSN9876ABCD\nSource: Deadspin"),
    ("LatestDrops2024abc", "Code: LatestDrops2024abc\nSource: Deadspin"),
    ("BonusDROPABC123", "Code: BonusDROPABC123\nSource: Deadspin"),
    # CHAMP (US variant)
    ("CHAMP8K4L9201", "Code: CHAMP8K4L9201\nSource: GameChampions US\nSTAKE.US"),
    ("CHAMPABCD1234", "Code: CHAMPABCD1234\nSource: GameChampions US"),
    ("CHAMP1234ABCD", "Code: CHAMP1234ABCD\nSTAKE.US"),
    # Keyword-only
    ("RANDOMCODE", "Stake.us Bonus Drop Alert\nCode: RANDOMCODE"),
    ("XYZCODE99", "STAKE.US drop\nCode: XYZCODE99"),
    # Source-only (no keyword)
    ("VEGASCODE", "Source: VegasInsider\nCode: VEGASCODE"),
    ("DEADSPINCODE", "Source: Deadspin\nCode: DEADSPINCODE"),
    ("SPIKECODE", "Source: TheSpike.gg\nCode: SPIKECODE"),
    ("BALLCODE", "Source: Ballislife\nCode: BALLCODE"),
    ("SGRIDCODE", "Source: SportsGrid Stake.us\nCode: SGRIDCODE"),
    ("GCUSACODE", "Source: GameChampions US\nCode: GCUSACODE"),
    # StakeUS source
    ("STAKEUSTEST", "Source: StakeUS\nCode: STAKEUSTEST"),
    # Stake.us Telegram source
    ("TGUSTEST", "Source: Stake.us Telegram\nCode: TGUSTEST"),
    # Explicit stakeus keyword
    ("STAKEUSCODE", "stakeus bonus drop\nCode: STAKEUSCODE"),
    # Stake-us hyphen
    ("HYPHENCODE", "stake-us drop\nCode: HYPHENCODE"),
    # Mixed case keyword
    ("MIXEDCASE", "Stake.US drop\nCode: MIXEDCASE"),
    # URL in text
    ("URLCODE", "https://stake.us/settings/offers?code=URLCODE"),
    # ESBUS prefix alone
    ("ESBUS777TEST", "Bonus drop code below"),
    # BIL prefix alone
    ("BIL1234567", "Bonus drop code below"),
    # SPIKEUS prefix alone
    ("SPIKEUSxx12yy34", "Bonus drop code below"),
    # DSN prefix alone
    ("DSN99887766", "Bonus drop code below"),
    # LatestDrops prefix alone
    ("LatestDrops2024xyz", "Bonus drop code below"),
    # BonusDROP prefix alone
    ("BonusDROPXYZ999", "Bonus drop code below"),
    # SG prefix alone
    ("SG77BONUS", "Bonus drop code below"),
]

for code, text in STAKE_US_CASES:
    src = ""
    src_m = re.search(r"Source:\s*([^\n]+)", text, re.I)
    if src_m:
        src = src_m.group(1).strip()
    result = classify_platform(text, code, source_name=src)
    check(f"stake.us | code={code!r}", result, "stake.us")

# ===========================================================================
# Part 1b — Stake.com historical drops (11 cases)
# ===========================================================================
print("\n=== Part 1b: Stake.com historical drops ===")

STAKE_COM_CASES = [
    # EsportsBetting COM
    ("ESBCOM158ELITERUSH6", "Code: ESBCOM158ELITERUSH6\nSource: EsportsBetting COM\nSTAKE.COM"),
    ("ESBCOM999XYZ", "Code: ESBCOM999XYZ\nSource: EsportsBetting COM"),
    # FreeTips PascalCase
    ("NovemberGold", "Code: NovemberGold\nSource: FreeTips\nSTAKE.COM"),
    ("ReelsAfterDark", "Code: ReelsAfterDark\nSource: FreeTips\nSTAKE.COM"),
    ("FrostAndGold", "Code: FrostAndGold\nSource: FreeTips\nSTAKE.COM"),
    ("TheMidnightDrop", "Code: TheMidnightDrop\nSource: FreeTips\nSTAKE.COM"),
    ("ThanksgivingGold", "Code: ThanksgivingGold\nSource: FreeTips\nSTAKE.COM"),
    # CHAMP (COM variant)
    ("CHAMP6Y2N8140", "Code: CHAMP6Y2N8140\nSource: GameChampions\nSTAKE.COM"),
    ("CHAMPABCD1234", "Code: CHAMPABCD1234\nSource: GameChampions"),
    # stakecom prefix
    ("stakecom2024bonus", "Code: stakecom2024bonus"),
    # Keyword-only
    ("COMCODE", "Stake.com Bonus Drop Alert\nCode: COMCODE"),
]

for code, text in STAKE_COM_CASES:
    src = ""
    src_m = re.search(r"Source:\s*([^\n]+)", text, re.I)
    if src_m:
        src = src_m.group(1).strip()
    result = classify_platform(text, code, source_name=src)
    check(f"stake.com | code={code!r}", result, "stake.com")

# ===========================================================================
# Part 2 — Zero Shuffle misclassifications
# ===========================================================================
print("\n=== Part 2: Zero Shuffle misclassifications for Stake codes ===")

ANTI_SHUFFLE_CASES = [
    # These must NOT return shuffle.us or shuffle.com
    ("BILJ3Z3WKF", "Code: BILJ3Z3WKF\nSource: Ballislife\nSTAKE.US"),
    ("SPIKEUS3Lz7N4q1", "Code: SPIKEUS3Lz7N4q1\nSource: TheSpike.gg\nSTAKE.US"),
    ("CHAMP8K4L9201", "Code: CHAMP8K4L9201\nSource: GameChampions US\nSTAKE.US"),
    ("NovemberGold", "Code: NovemberGold\nSource: FreeTips\nSTAKE.COM"),
    ("ESBCOM158ELITERUSH6", "Code: ESBCOM158ELITERUSH6\nSource: EsportsBetting COM"),
    ("ESBUS158ELITERUSH6", "Code: ESBUS158ELITERUSH6\nSource: EsportsBetting"),
]

for code, text in ANTI_SHUFFLE_CASES:
    src = ""
    src_m = re.search(r"Source:\s*([^\n]+)", text, re.I)
    if src_m:
        src = src_m.group(1).strip()
    result = classify_platform(text, code, source_name=src)
    not_shuffle = result not in ("shuffle.us", "shuffle.com")
    check(f"not-shuffle | code={code!r}", not_shuffle, True)

# ===========================================================================
# Part 3 — All 13 platforms route correctly
# ===========================================================================
print("\n=== Part 3: All 13 platforms route to correct platform_id ===")

PLATFORM_CASES = [
    # (code, text, source, expected_platform_id)
    ("GOAT8842X", "GOATED FLASH CODE ALERT\nCode: GOAT8842X", "Goated Drops", "goated"),
    ("GOATEDXYZ123", "goated.com drop\nCode: GOATEDXYZ123", "", "goated"),
    ("DGN5590VIP", "DEGEN BONUS DROP\nCode: DGN5590VIP", "Degen Official", "degen"),
    ("DEGENTEST123", "degen.com bonus\nCode: DEGENTEST123", "", "degen"),
    ("shuffleusABC123", "shuffle.us drop\nCode: shuffleusABC123", "", "shuffle.us"),
    ("SHUFFLECODE", "shuffle.us bonus\nCode: SHUFFLECODE", "Shuffle.us Telegram", "shuffle.us"),
    ("shufflecomXYZ", "shuffle.com drop\nCode: shufflecomXYZ", "", "shuffle.com"),
    ("SHUFFLECOMCODE", "shuffle.com bonus\nCode: SHUFFLECOMCODE", "AnyClaimerShuffle", "shuffle.com"),
    ("RAINBETTEST", "rainbet.com drop\nCode: RAINBETTEST", "Rainbet Official", "rainbet"),
    ("RBTEST123", "rainbet bonus\nCode: RBTEST123", "", "rainbet"),
    ("RAINBETUSTEST", "rainbet.us drop\nCode: RAINBETUSTEST", "", "rainbet.us"),
    ("RBUSTEST123", "rainbet.us bonus\nCode: RBUSTEST123", "", "rainbet.us"),
    ("THRILLTEST", "thrill.com drop\nCode: THRILLTEST", "Thrill Telegram", "thrill.com"),
    ("WINNATEST", "winna.com drop\nCode: WINNATEST", "", "winna"),
    ("GAMBATEST", "gamba.com drop\nCode: GAMBATEST", "", "gamba"),
    ("RAZEDTEST", "razed.com drop\nCode: RAZEDTEST", "", "razed"),
    ("QZINOTEST", "qzino.com drop\nCode: QZINOTEST", "", "qzino"),
]

for code, text, src, expected in PLATFORM_CASES:
    result = classify_platform(text, code, source_name=src)
    check(f"platform={expected!r} | code={code!r}", result, expected)

# ===========================================================================
# Part 4 — Claim URLs
# ===========================================================================
print("\n=== Part 4: Claim URLs ===")

CLAIM_URL_CASES = [
    ("stake.us", "TESTCODE",
     "https://stake.us/settings/offers?type=code&code=TESTCODE&currency=sweeps&modal=redeemBonus"),
    ("stake.com", "TESTCODE",
     "https://stake.com/settings/offers?type=code&code=TESTCODE&currency=btc&modal=redeemBonus"),
    ("goated", "GOAT8842X", "https://www.goated.com"),
    ("degen", "DGN5590VIP", "https://degen.com"),
    ("shuffle.us", "SHUFFLECODE", "https://shuffle.us/vip-program?modal=redeem"),
    ("shuffle.com", "SHUFFLECODE", "https://shuffle.com/vip-program?modal=redeem"),
    ("rainbet", "RBTEST", "https://rainbet.com"),
    ("rainbet.us", "RBUSTEST", "https://rainbet.us"),
    ("thrill.com", "THRILLTEST", "https://thrill.com"),
    ("winna", "WINNATEST", "https://winna.com"),
    ("gamba", "GAMBATEST", "https://gamba.com"),
    ("razed", "RAZEDTEST", "https://razed.com"),
    ("qzino", "QZINOTEST", "https://qzino.com"),
]

for pid, code, expected_url in CLAIM_URL_CASES:
    url = get_claim_url(pid, code)
    check(f"claim_url platform={pid!r}", url, expected_url)

# Goated claim note
note = get_claim_note("goated")
check("goated claim_note present", bool(note), True)
check("goated claim_note content", "Redeem Code" in (note or ""), True)

# ===========================================================================
# Part 5 — OCR banner extraction (simulated)
# ===========================================================================
print("\n=== Part 5: OCR banner extraction (simulated) ===")

GOATED_OCR = (
    "GOATED FLASH CODE ALERT\n"
    "$5 USDC DROP\n"
    "$5,000 WAGERED IN LAST 7 DAYS\n"
    "CODE: GOAT8842X\n"
    "FIRST 200 CLAIMS"
)

DEGEN_OCR = (
    "DEGEN BONUS DROP\n"
    "$10 FREE\n"
    "USE CODE: DGN5590VIP\n"
    "CLAIM ON DEGEN.COM"
)

goated_details = extract_banner_drop_details(GOATED_OCR, "")
check("goated OCR code", goated_details["code"], "GOAT8842X")
check("goated OCR amount", goated_details["amount"], "$5")
check("goated OCR wager", goated_details["wager"], "$5,000 wagered in the last 7 DAYS")

degen_details = extract_banner_drop_details(DEGEN_OCR, "")
check("degen OCR code", degen_details["code"], "DGN5590VIP")
check("degen OCR amount", degen_details["amount"], "$10")

# ===========================================================================
# Part 6 — Placeholder suppression
# ===========================================================================
print("\n=== Part 6: Placeholder suppression ===")

from bonus_code_detector import _suppress_placeholder_text, should_ocr_code

PLACEHOLDER_CASES = [
    ("Check the image for code", ""),
    ("See image for code", ""),
    ("Code in image", ""),
    ("View attached event graphic", ""),
    ("Goated drop - check the image for code - claim now", "Goated drop -  - claim now"),
]

for inp, expected_contains_placeholder in PLACEHOLDER_CASES:
    result = _suppress_placeholder_text(inp) or ""
    has_placeholder = bool(re.search(
        r"check.*image.*code|see.*image.*code|code.*in.*image|view.*graphic",
        result, re.I
    ))
    check(f"placeholder suppressed: {repr(inp)[:40]}", has_placeholder, False)

# should_ocr_code
check("should_ocr CHECK_IMAGE_FOR_CODE", should_ocr_code("CHECK_IMAGE_FOR_CODE"), True)
check("should_ocr CHECK_IMAGE_FOR_CODE_#123", should_ocr_code("CHECK_IMAGE_FOR_CODE_#123"), True)
check("should_ocr DEGEN_DROP_#456", should_ocr_code("DEGEN_DROP_#456"), True)
check("should_ocr real code", should_ocr_code("GOAT8842X"), False)

# ===========================================================================
# Part 7 — source_history.json auto-learning
# ===========================================================================
print("\n=== Part 7: source_history.json auto-learning ===")

# Use a temp copy to avoid polluting the real file
_orig_path = _HISTORY_PATH
import platform_rules as _pr

_tmp_dir = tempfile.mkdtemp()
_tmp_history = os.path.join(_tmp_dir, "source_history.json")
shutil.copy(_HISTORY_PATH, _tmp_history)

# Monkey-patch path for test
_pr._HISTORY_PATH = _tmp_history

learn_source("TestSource2024", "goated")
data = json.loads(open(_tmp_history, encoding="utf-8").read())
check("learn_source persists new entry", data.get("TestSource2024"), "goated")

# GameChampions (ambiguous) should NOT be persisted
learn_source("GameChampions", "stake.com")
data2 = json.loads(open(_tmp_history, encoding="utf-8").read())
check("learn_source skips ambiguous GameChampions", "GameChampions" not in data2, True)

# Restore
_pr._HISTORY_PATH = _orig_path
shutil.rmtree(_tmp_dir)

# ===========================================================================
# Part 8 — Non-regression: Shuffle/Rainbet/Degen/Qzino/Winna/Gamba/Thrill
# ===========================================================================
print("\n=== Part 8: Non-regression for existing platforms ===")

NON_REGRESSION = [
    ("ABCD1234", "Shuffle.us Bonus Drop\nCode: ABCD1234", "", "shuffle.us"),
    ("XYZ9876", "Shuffle.com Chat Code\nCode: XYZ9876", "", "shuffle.com"),
    ("MFQP3DSN", "Rainbet Drop\nCode: MFQP3DSN", "Rainbet Official", "rainbet"),
    ("DEGEN123", "Degen Drop\nCode: DEGEN123", "Degen Official", "degen"),
    ("QZ12345", "Qzino Bonus\nCode: QZ12345", "", "qzino"),
    ("WINNA123", "Winna drop\nCode: WINNA123", "", "winna"),
    ("GAMBA123", "Gamba drop\nCode: GAMBA123", "", "gamba"),
    ("THRILL123", "Thrill drop\nCode: THRILL123", "", "thrill.com"),
    ("RAZED123", "Razed drop\nCode: RAZED123", "", "razed"),
]

for code, text, src, expected in NON_REGRESSION:
    result = classify_platform(text, code, source_name=src)
    check(f"non-regression platform={expected!r} | code={code!r}", result, expected)

# ===========================================================================
# Part 9 — Dual-stake detection
# ===========================================================================
print("\n=== Part 9: Dual-stake detection ===")

check(
    "dual_stake both keywords",
    classify_platform("Valid on stake.us and stake.com\nCode: DUALCODE", "DUALCODE"),
    "dual_stake",
)

# ===========================================================================
# Summary
# ===========================================================================
print(f"\n{'='*60}")
print(f"  Results: {passed} passed, {failed} failed / {passed + failed} total")
print(f"{'='*60}")
sys.exit(0 if failed == 0 else 1)
