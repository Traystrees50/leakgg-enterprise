import base64
import re
import logging
from typing import Optional, Dict, Any
from config import OCR_SPACE_API_KEY, OCR_SPACE_API_URL
from network_manager import ResilientSession

logger = logging.getLogger(__name__)

_RE_OCR_CODE_GENERIC = re.compile(
    r"(?:code|promo\s*code|drop\s*code|claim\s*code|use\s*code)[:\s=]+([A-Za-z0-9_\-]{4,35})",
    re.I,
)

_RE_OCR_CODE_STANDALONE = re.compile(r"\b([A-Z0-9]{5,20})\b")

_RE_OCR_CODE_HIGHLIGHTED = re.compile(r"[A-Z0-9]{4,25}")

_OCR_STOP_WORDS = {
    "CODE", "CLAIM", "CLICK", "COPY", "REDEEM", "HERE", "PLAY", "NOW", "BONUS",
    "DROP", "DROPS", "PROMO", "OFFER", "USE", "THE", "AND", "FOR", "WITH", "YOUR",
    "THIS", "FROM", "STAKE", "SHUFFLE", "RAINBET", "DEGEN", "QZINO", "WINNA",
    "THRILL", "GOATED", "MODO", "PULSZ", "BABA", "WOWVEGAS", "YAYCASINO",
    "COOKED", "LONESTAR", "CHANCED", "ACEBET", "REALPRIZE", "CROWNSCOINS",
    "MYPRIZE", "FREE", "SC", "GC", "USD", "CLAIMED", "CLAIMS", "LIMIT",
    "WAGER", "REQUIREMENT", "REWARDS", "AMOUNT", "VALUE", "TOTAL", "DAY",
    "DAYS", "HOUR", "HOURS", "MINUTE", "MINUTES", "EXPIRED", "ACTIVE",
    "UNLIMITED", "OPEN", "EXCLUSIVE", "VIP", "TIER", "BASED", "STANDARD",
}


class OCRClient:
    """
    Lightweight client for the OCR.space API.
    Extracts text from a remote image URL and pulls out bonus-code candidates.
    No new dependencies — uses ``requests`` via ResilientSession.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or OCR_SPACE_API_KEY
        self.session = ResilientSession(timeout=15, max_retries=2)

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def ocr_image(self, image_url: str) -> Optional[str]:
        """
        Sends an image URL to OCR.space and returns the parsed text.
        Returns None on any failure (network, API error, bad response).
        """
        if not self.api_key:
            logger.debug("OCR.space API key not configured; skipping OCR")
            return None

        if not image_url or not image_url.startswith("http"):
            logger.debug(f"OCR skipped: invalid image URL '{image_url}'")
            return None

        try:
            resp = self.session.post(
                OCR_SPACE_API_URL,
                headers={"Accept": "application/json"},
                data={
                    "apikey": self.api_key,
                    "imageUrl": image_url,
                    "language": "eng",
                    "isOverlayRequired": "false",
                    "isTable": "false",
                    "OCREngine": 5,
                },
                timeout=30,
            )
            if resp is None or resp.status_code != 200:
                logger.warning(f"OCR.space request failed for {image_url}: HTTP {getattr(resp, 'status_code', 'None')}")
                return None
            result = resp.json()
            if result.get("IsErroredOnProcessing"):
                err = result.get("ErrorMessage", "unknown")
                logger.warning(f"OCR.space errored on {image_url}: {err}")
                return None
            parsed = result.get("ParsedResults", [])
            if not parsed:
                logger.debug(f"OCR.space returned no parsed results for {image_url}")
                return None
            text = parsed[0].get("ParsedText", "")
            return text.strip() if text else None
        except Exception as e:
            logger.warning(f"OCR failed for {image_url}: {e}")
            return None

    def extract_code(self, ocr_text: str) -> Optional[str]:
        """
        Extracts the most likely bonus code from OCR-extracted text.
        Tries labelled patterns first, then standalone tokens, filtered
        against a stop-word list to reject common false positives.
        """
        if not ocr_text:
            return None

        for pattern in (_RE_OCR_CODE_GENERIC, _RE_OCR_CODE_STANDALONE):
            m = pattern.search(ocr_text)
            if m:
                candidate = m.group(1).strip()
                if candidate.upper() not in _OCR_STOP_WORDS:
                    if re.search(r"[A-Z]", candidate):
                        return candidate

        tokens = _RE_OCR_CODE_HIGHLIGHTED.findall(ocr_text)
        for tok in tokens:
            if tok.upper() in _OCR_STOP_WORDS:
                continue
            if re.search(r"[A-Z]", tok):
                return tok

        return None

    def ocr_code(self, image_url: str) -> Optional[str]:
        """
        Convenience: OCR an image URL and extract a bonus code from the result.
        Returns the code string or None.
        """
        text = self.ocr_image(image_url)
        if not text:
            return None
        return self.extract_code(text)

    def ocr_image_bytes(self, image_bytes: bytes) -> Optional[str]:
        """
        Sends raw image bytes (base64-encoded) to OCR.space and returns parsed text.
        Useful for images that are behind auth layers (e.g. private Telegram photos).
        Returns None on any failure.
        """
        if not self.api_key or not image_bytes:
            return None
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            encoded = f"data:image/jpeg;base64,{b64}"
            resp = self.session.post(
                OCR_SPACE_API_URL,
                headers={"Accept": "application/json"},
                data={
                    "apikey": self.api_key,
                    "isOverlayRequired": "false",
                    "isTable": "false",
                    "OCREngine": 5,
                },
                files={"base64Image": ("", encoded, "text/plain")},
                timeout=30,
            )
            if resp is None or resp.status_code != 200:
                logger.warning(f"OCR.space bytes request failed: HTTP {getattr(resp, 'status_code', 'None')}")
                return None
            result = resp.json()
            if result.get("IsErroredOnProcessing"):
                err = result.get("ErrorMessage", "unknown")
                logger.warning(f"OCR.space errored on image bytes: {err}")
                return None
            parsed = result.get("ParsedResults", [])
            if not parsed:
                return None
            text = parsed[0].get("ParsedText", "")
            return text.strip() if text else None
        except Exception as e:
            logger.warning(f"OCR (bytes) failed: {e}")
            return None

    def ocr_code_from_bytes(self, image_bytes: bytes) -> Optional[str]:
        """
        Convenience: OCR raw image bytes and extract a bonus code.
        Returns the code string or None.
        """
        text = self.ocr_image_bytes(image_bytes)
        if not text:
            return None
        return self.extract_code(text)


_default_client: Optional[OCRClient] = None


def get_ocr_client() -> OCRClient:
    global _default_client
    if _default_client is None:
        _default_client = OCRClient()
    return _default_client
