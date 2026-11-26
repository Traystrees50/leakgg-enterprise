import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrapers.ocr import extract_banner_drop_details, _RE_BANNER_LABELED, _normalize_ocr_line, _OCR_STOP_WORDS, _RE_BANNER_WAGER

GOATED_OCR = "GOATED FLASH CODE ALERT\n$5 USDC DROP\n$5,000 WAGERED IN LAST 7 DAYS\nCODE: GOAT8842X\nFIRST 200 CLAIMS"

combined = GOATED_OCR + "\n"
m = _RE_BANNER_LABELED.search(combined)
with open("debug_ocr_out.txt", "w", encoding="utf-8") as f:
    f.write(f"labeled match: {m}\n")
    if m:
        raw = m.group(1)
        f.write(f"group(1): {repr(raw)}\n")
        candidate = _normalize_ocr_line(raw)
        f.write(f"normalized: {repr(candidate)}\n")
        f.write(f"in stopwords: {candidate.upper() in _OCR_STOP_WORDS}\n")
        f.write(f"len: {len(candidate)}\n")

    m_wager = _RE_BANNER_WAGER.search(combined)
    f.write(f"wager match: {m_wager}\n")
    if m_wager:
        f.write(f"wager group(1): {repr(m_wager.group(1))}\n")
        f.write(f"wager group(2): {repr(m_wager.group(2))}\n")

    details = extract_banner_drop_details(GOATED_OCR, "")
    f.write(f"details: {details}\n")

    # Also check each line
    f.write("\n--- Line analysis ---\n")
    from scrapers.ocr import _RE_BANNER_STANDALONE_MIXED, _RE_BANNER_STANDALONE_UPPER
    for line in combined.splitlines():
        norm = _normalize_ocr_line(line)
        mixed = bool(_RE_BANNER_STANDALONE_MIXED.match(norm))
        upper = bool(_RE_BANNER_STANDALONE_UPPER.match(norm))
        f.write(f"  line={repr(norm):30s} mixed={mixed} upper={upper} in_stop={norm.upper() in _OCR_STOP_WORDS}\n")
