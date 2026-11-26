import base64
import os
import re
import logging
from typing import Optional, Dict, Any, Tuple
from config import OCR_SPACE_API_URL
from network_manager import ResilientSession

logger = logging.getLogger(__name__)

_RE_OCR_CODE_GENERIC = re.compile(
    r"(?:code|promo\s*code|drop\s*code|claim\s*code|use\s*code)[:\s=]+([A-Za-z0-9_\-]{4,35})",
    re.I,
)

_RE_OCR_CODE_STANDALONE = re.compile(r"\b([A-Z0-9]{5,20})\b")

_RE_OCR_CODE_HIGHLIGHTED = re.compile(r"[A-Z0-9]{4,25}")

# Banner-specific labeled code pattern (highest priority)
# Requires an explicit separator (: - – —) to avoid matching 'CODE ALERT'
_RE_BANNER_LABELED = re.compile(
    r"(?:PROMO\s*CODE|BONUS\s*CODE|DROP\s*CODE|REDEEM\s*CODE|USE\s*CODE|CODE)"
    r"\s*[:\-\u2013\u2014]\s*([A-Z0-9_-]{4,24})",
    re.I,
)

# Standalone uppercase/mixed-alnum line on banner
_RE_BANNER_STANDALONE_MIXED = re.compile(r"^(?=.*[A-Z])(?=.*\d)[A-Z0-9_-]{4,22}$")
_RE_BANNER_STANDALONE_UPPER = re.compile(r"^[A-Z0-9_-]{4,22}$")

# Amount and wager patterns for banner extraction
_RE_BANNER_AMOUNT = re.compile(
    r"\$([\d,.]+)\s*(?:USDC|USDT|BONUS|DROP|CODE|FREE|EACH)?",
    re.I,
)
# Wager: captures amount in group(1), optional 'N DAYS' in group(2)
_RE_BANNER_WAGER = re.compile(
    r"\$([\d,]+)\s*(?:WAGER(?:ED)?|PLAYTHROUGH)"
    r"(?:[^\n]*?IN\s*(?:THE\s*)?LAST\s*(\d+\s*DAYS?))?",
    re.I,
)

# Placeholder strings that should be suppressed when a real code is found
_PLACEHOLDER_STRINGS = (
    "check the image for code",
    "see image for code",
    "code in image",
    "check image for code",
    "view image for code",
)

_OCR_STOP_WORDS = {
    "CODE", "CLAIM", "CLICK", "COPY", "REDEEM", "HERE", "PLAY", "NOW", "BONUS",
    "DROP", "DROPS", "PROMO", "OFFER", "USE", "THE", "AND", "FOR", "WITH", "YOUR",
    "THIS", "FROM", "STAKE", "SHUFFLE", "RAINBET", "DEGEN", "QZINO", "WINNA",
    "THRILL", "GOATED", "FREE", "SC", "GC", "USD", "CLAIMED", "CLAIMS", "LIMIT",
    "WAGER", "REQUIREMENT", "REWARDS", "AMOUNT", "VALUE", "TOTAL", "DAY",
    "DAYS", "HOUR", "HOURS", "MINUTE", "MINUTES", "EXPIRED", "ACTIVE",
    "UNLIMITED", "OPEN", "EXCLUSIVE", "VIP", "TIER", "BASED", "STANDARD",
    # Extended banner stopwords
    "GOATEDCOM", "DEGENCASINO", "DEGENCOM", "FLASH", "ALERT",
    "BOOST", "BOOSTS", "BIRTHDAY", "HUNT", "SPINS", "CASH",
    "USDC", "USDT", "BTC", "JOIN", "TELEGRAM", "DISCORD",
    "HTTPS", "HTTP", "WWW", "COM", "FIRST", "USERS", "PLAYERS",
    "LIMITED", "EVENT", "LAST", "EACH",
}


def _normalize_ocr_line(line: str) -> str:
    """Strip surrounding brackets/quotes/pipes and collapse internal spaces in codes."""
    line = line.strip()
    line = re.sub(r"^[\[\](){}|:\s]+|[\[\](){}|:\s]+$", "", line)
    # Collapse 'CODE: GOAT 7749X' -> 'GOAT7749X' when it looks like a split code
    line = re.sub(r"(?<=[A-Z0-9])\s+(?=[A-Z0-9])", "", line)
    return line.strip()


class OCRClient:
    def __init__(self, api_key: Optional[str] = None):
        if api_key is not None:
            self.api_key = api_key if api_key else None
        else:
            self.api_key = None
        self.session = ResilientSession(timeout=15, max_retries=2)

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def _call_ocr_space(
        self,
        image_url: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        engine: int = 2,
    ) -> Optional[str]:
        """Single OCR.space call with configurable engine."""
        if not self.api_key:
            return None
        try:
            payload: Dict[str, Any] = {
                "apikey": self.api_key,
                "language": "eng",
                "isoverlayrequired": "false",
                "istable": "false",
                "ocrengine": engine,
                "scale": "true",
                "detectOrientation": "true",
            }
            files = None
            if image_bytes:
                b64 = base64.b64encode(image_bytes).decode("ascii")
                payload["base64Image"] = f"data:image/jpeg;base64,{b64}"
            elif image_url:
                payload["url"] = image_url
                payload["filetype"] = "jpg"
            else:
                return None

            resp = self.session.post(
                OCR_SPACE_API_URL,
                headers={"Accept": "application/json"},
                data=payload,
                timeout=30,
            )
            if resp is None or resp.status_code != 200:
                logger.warning(
                    f"OCR.space (engine={engine}) failed: HTTP "
                    f"{getattr(resp, 'status_code', 'None')}"
                )
                return None
            result = resp.json()
            if result.get("IsErroredOnProcessing"):
                logger.warning(
                    f"OCR.space (engine={engine}) error: "
                    f"{result.get('ErrorMessage', 'unknown')}"
                )
                return None
            parsed = result.get("ParsedResults", [])
            if not parsed:
                return None
            text = parsed[0].get("ParsedText", "")
            return text.strip() if text else None
        except Exception as e:
            logger.warning(f"OCR.space (engine={engine}) exception: {e}")
            return None

    def ocr_image(self, image_url: str, engine: int = 2) -> Optional[str]:
        """Single-pass OCR on a URL."""
        if not self.api_key:
            logger.debug("OCR.space API key not configured; skipping OCR")
            return None
        if not image_url or not image_url.startswith("http"):
            logger.debug(f"OCR skipped: invalid image URL '{image_url}'")
            return None
        return self._call_ocr_space(image_url=image_url, engine=engine)

    def ocr_image_two_pass(
        self,
        image_url: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
    ) -> Optional[str]:
        """
        Two-pass OCR for Goated/Degen banner images.
        Pass 1: engine=2 (handles stylized/neon/bold typography).
        Pass 2: engine=1 fallback if Pass 1 yields no valid code candidates.
        Returns the raw OCR text from whichever pass succeeds first.
        """
        if not self.api_key:
            return None
        # Pass 1
        text = self._call_ocr_space(
            image_url=image_url, image_bytes=image_bytes, engine=2
        )
        if text and self._has_code_candidate(text):
            logger.debug("OCR two-pass: Pass 1 (engine=2) succeeded")
            return text
        # Pass 2
        logger.debug("OCR two-pass: Pass 1 empty/no candidate, trying engine=1")
        text2 = self._call_ocr_space(
            image_url=image_url, image_bytes=image_bytes, engine=1
        )
        if text2:
            return text2
        return text  # return Pass 1 result even if no candidate (for logging)

    @staticmethod
    def _has_code_candidate(ocr_text: str) -> bool:
        """Quick check: does the OCR text contain anything that looks like a code?"""
        for line in ocr_text.splitlines():
            line = _normalize_ocr_line(line)
            if _RE_BANNER_LABELED.search(line):
                return True
            if _RE_BANNER_STANDALONE_MIXED.match(line.upper()):
                if line.upper() not in _OCR_STOP_WORDS:
                    return True
        return False

    def extract_code(self, ocr_text: str) -> Optional[str]:
        """Extract the most likely bonus code from OCR text."""
        if not ocr_text:
            return None
        # Priority 1: labeled code
        m = _RE_BANNER_LABELED.search(ocr_text)
        if m:
            candidate = _normalize_ocr_line(m.group(1))
            if candidate.upper() not in _OCR_STOP_WORDS and len(candidate) >= 4:
                return candidate
        # Priority 2: generic labeled
        m = _RE_OCR_CODE_GENERIC.search(ocr_text)
        if m:
            candidate = m.group(1).strip()
            if candidate.upper() not in _OCR_STOP_WORDS:
                if re.search(r"[A-Z]", candidate):
                    return candidate
        # Priority 3: standalone uppercase
        m = _RE_OCR_CODE_STANDALONE.search(ocr_text)
        if m:
            candidate = m.group(1).strip()
            if candidate.upper() not in _OCR_STOP_WORDS:
                if re.search(r"[A-Z]", candidate):
                    return candidate
        # Priority 4: highlighted tokens
        tokens = _RE_OCR_CODE_HIGHLIGHTED.findall(ocr_text)
        for tok in tokens:
            if tok.upper() in _OCR_STOP_WORDS:
                continue
            if re.search(r"[A-Z]", tok):
                return tok
        return None

    def ocr_code(self, image_url: str) -> Optional[str]:
        text = self.ocr_image(image_url)
        if not text:
            return None
        return self.extract_code(text)

    def ocr_image_bytes(self, image_bytes: bytes) -> Optional[str]:
        if not self.api_key or not image_bytes:
            return None
        return self._call_ocr_space(image_bytes=image_bytes, engine=2)

    def ocr_code_from_bytes(self, image_bytes: bytes) -> Optional[str]:
        text = self.ocr_image_bytes(image_bytes)
        if not text:
            return None
        return self.extract_code(text)


def extract_banner_drop_details(
    ocr_text: str,
    caption_text: str = "",
) -> Dict[str, Optional[str]]:
    """
    Targeted banner code, amount, and wager parser for Goated/Degen event images.

    Returns a dict with keys:
      'code'   - extracted promo code or None
      'amount' - bonus amount string or None
      'wager'  - wager requirement string or None
    """
    combined = f"{ocr_text}\n{caption_text}"
    result: Dict[str, Optional[str]] = {
        "code": None,
        "amount": None,
        "wager": None,
    }

    # ── Code extraction (priority order) ────────────────────────────────────
    # 1. Labeled code match
    m = _RE_BANNER_LABELED.search(combined)
    if m:
        candidate = _normalize_ocr_line(m.group(1))
        if candidate.upper() not in _OCR_STOP_WORDS and len(candidate) >= 4:
            result["code"] = candidate

    if not result["code"]:
        # 2. Standalone mixed-alnum line (prioritize mixed over pure uppercase)
        for line in combined.splitlines():
            norm = _normalize_ocr_line(line)
            if not norm or len(norm) < 4:
                continue
            # Skip lines that had internal spaces before normalization
            # (e.g. 'FIRST 200 CLAIMS' -> 'FIRST200CLAIMS' is not a real code)
            if " " in line.strip():
                continue
            if _RE_BANNER_STANDALONE_MIXED.match(norm):
                if norm.upper() not in _OCR_STOP_WORDS:
                    result["code"] = norm
                    break

    if not result["code"]:
        # 3. Pure uppercase token not in blocklist
        for line in combined.splitlines():
            norm = _normalize_ocr_line(line)
            if not norm or len(norm) < 4:
                continue
            if " " in line.strip():
                continue
            if _RE_BANNER_STANDALONE_UPPER.match(norm):
                if norm.upper() not in _OCR_STOP_WORDS:
                    result["code"] = norm
                    break

    # ── Amount extraction ────────────────────────────────────────────────────
    m_amt = _RE_BANNER_AMOUNT.search(combined)
    if m_amt:
        result["amount"] = f"${m_amt.group(1)}"

    # ── Wager extraction ─────────────────────────────────────────────────────
    m_wager = _RE_BANNER_WAGER.search(combined)
    if m_wager:
        wager_str = f"${m_wager.group(1)} wagered"
        if m_wager.group(2):
            wager_str += f" in the last {m_wager.group(2)}"
        result["wager"] = wager_str

    return result


_default_client: Optional[OCRClient] = None


def get_ocr_client() -> OCRClient:
    global _default_client
    if _default_client is None:
        from config import OCR_SPACE_API_KEY
        _default_client = OCRClient(api_key=OCR_SPACE_API_KEY or None)
    return _default_client
