import base64
import re
import logging
from typing import Optional
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
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else OCR_SPACE_API_KEY or None
        self.session = ResilientSession(timeout=15, max_retries=2)
        self._local_engine = None
        self._local_engine_checked = False

    @property
    def is_available(self) -> bool:
        return bool(self._load_local_engine() or self.api_key)

    def _load_local_engine(self):
        if self._local_engine_checked:
            return self._local_engine
        self._local_engine_checked = True
        try:
            from rapidocr import RapidOCR
            self._local_engine = RapidOCR()
        except ImportError:
            logger.debug("Local OCR is unavailable; install rapidocr and onnxruntime to enable it")
        except Exception as exc:
            logger.warning(f"Could not initialize local OCR engine: {exc}")
        return self._local_engine

    def _run_local_ocr(self, image_bytes: bytes) -> Optional[str]:
        engine = self._load_local_engine()
        if engine is None or not image_bytes:
            return None
        try:
            result = engine(image_bytes)
            if not result:
                return None
            lines = [str(text).strip() for text in (getattr(result, "txts", None) or ()) if text]
            return "\n".join(lines) or None
        except Exception as exc:
            logger.warning(f"Local image OCR failed: {exc}")
            return None

    def _ocr_image_url_api(self, image_url: str) -> Optional[str]:
        if not self.api_key:
            return None
        try:
            resp = self.session.post(
                OCR_SPACE_API_URL,
                headers={"Accept": "application/json"},
                data={
                    "apikey": self.api_key,
                    "url": image_url,
                    "language": "eng",
                    "isoverlayrequired": "false",
                    "istable": "false",
                    "ocrengine": 2,
                    "filetype": "jpg",
                },
                timeout=30,
            )
            if resp is None or resp.status_code != 200:
                logger.warning(f"OCR.space image request failed: HTTP {getattr(resp, 'status_code', 'None')}")
                return None
            result = resp.json()
            if result.get("IsErroredOnProcessing"):
                err = result.get("ErrorMessage", "unknown")
                logger.warning(f"OCR.space image processing failed: {err}")
                return None
            parsed = result.get("ParsedResults", [])
            if not parsed:
                return None
            text = parsed[0].get("ParsedText", "")
            return text.strip() if text else None
        except Exception as exc:
            logger.warning(f"OCR.space image request failed: {exc}")
            return None

    def ocr_image(self, image_url: str) -> Optional[str]:
        if not image_url or not image_url.startswith(("http://", "https://")):
            logger.debug("OCR skipped an invalid image URL")
            return None
        if self._load_local_engine():
            try:
                response = self.session.get(image_url, timeout=30)
                if response is not None and response.status_code == 200:
                    image_bytes = response.content
                    if len(image_bytes) <= 10 * 1024 * 1024:
                        text = self._run_local_ocr(image_bytes)
                        if text:
                            return text
                    else:
                        logger.warning("Local OCR skipped an image larger than 10 MB")
            except Exception as exc:
                logger.warning(f"Could not download image for local OCR: {exc}")
        text = self._ocr_image_url_api(image_url)
        if text is None and not self.api_key:
            logger.debug("No OCR engine is available for this image")
        return text

    def extract_code(self, ocr_text: str) -> Optional[str]:
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
        text = self.ocr_image(image_url)
        if not text:
            return None
        return self.extract_code(text)

    def ocr_image_bytes(self, image_bytes: bytes) -> Optional[str]:
        if not image_bytes:
            return None
        if len(image_bytes) > 10 * 1024 * 1024:
            logger.warning("OCR skipped an image larger than 10 MB")
            return None
        local_text = self._run_local_ocr(image_bytes)
        if local_text:
            return local_text
        if not self.api_key:
            return None
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            encoded = f"data:image/jpeg;base64,{b64}"
            resp = self.session.post(
                OCR_SPACE_API_URL,
                headers={"Accept": "application/json"},
                data={
                    "apikey": self.api_key,
                    "isoverlayrequired": "false",
                    "istable": "false",
                    "ocrengine": 2,
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
