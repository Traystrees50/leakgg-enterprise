import re
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from models import BonusCodeItem, Platform
from filters import extract_event_datetime
from scrapers.ocr import OCRClient, get_ocr_client

logger = logging.getLogger(__name__)

_PLACEHOLDER_PREFIXES = (
    "CHECK_IMAGE_FOR_CODE",
    "CHECK_IMAGE",
    "DEGEN_DROP_",
    "QZINO_EVENT_",
    "QZINO_PROMO",
    "STAKE_US_WEEKLY_BOOST",
    "STAKE_COM_WEEKLY_BOOST",
    "STAKE_US_POST_MONTHLY_BONUS",
    "STAKE_COM_POST_MONTHLY_BONUS",
    "STAKE_US_MONTHLY_BONUS",
    "STAKE_COM_MONTHLY_BONUS",
    "STAKE_US_VIP_NOTICE",
    "STAKE_COM_VIP_NOTICE",
)

_EVENT_TYPE_PATTERNS = [
    (re.compile(r"WEEKLY\s*(?:BOOST|BONUS)", re.I), "WEEKLY BOOST"),
    (re.compile(r"MONTHLY\s*BONUS", re.I), "MONTHLY BONUS"),
    (re.compile(r"VIP\s*EVENT", re.I), "VIP EVENT"),
    (re.compile(r"VIP\s*NOTICE", re.I), "VIP NOTICE"),
    (re.compile(r"POST\s*MONTHLY", re.I), "POST MONTHLY BONUS"),
    (re.compile(r"HIGH\s*ROLLER", re.I), "HIGHROLLER"),
    (re.compile(r"\bDROP\b", re.I), "DROP"),
    (re.compile(r"\bBOOST\b", re.I), "BOOST"),
    (re.compile(r"\bPROMO\b", re.I), "PROMO"),
    (re.compile(r"\bEVENT\b", re.I), "EVENT"),
]

_EVENT_NAME_PATTERNS = [
    (re.compile(r"WEEKLY\s*(?:BOOST|BONUS)", re.I), "Weekly Boost"),
    (re.compile(r"MONTHLY\s*BONUS", re.I), "Monthly Bonus"),
    (re.compile(r"POST\s*MONTHLY", re.I), "Post Monthly Bonus"),
    (re.compile(r"VIP\s*EVENT", re.I), "VIP Event"),
    (re.compile(r"VIP\s*NOTICE", re.I), "VIP Notice"),
    (re.compile(r"HIGH\s*ROLLER", re.I), "Highroller Drop"),
    (re.compile(r"\bDROP\b", re.I), "Bonus Drop"),
    (re.compile(r"\bBOOST\b", re.I), "Boost"),
    (re.compile(r"\bPROMO\b", re.I), "Promo"),
    (re.compile(r"\bEVENT\b", re.I), "Event"),
]

_RE_EVENT_NAME_EXPLICIT = re.compile(
    r"(?:EVENT[:=]+|NAME[:=]+)\s*([A-Za-z0-9][A-Za-z0-9\s\-_]{2,40})",
    re.I,
)


def should_ocr_code(code: str) -> bool:
    """
    Returns True if a code is a placeholder indicating the real code
    is embedded inside a media image and must be OCR-extracted.
    """
    if not code:
        return False
    c = code.strip().upper()
    if "#" in c and any(c.startswith(p) for p in _PLACEHOLDER_PREFIXES):
        return True
    if c == "CHECK_IMAGE_FOR_CODE" or c == "QZINO_PROMO":
        return True
    return False


def detect_event_from_message(text: str) -> Dict[str, Any]:
    """
    Extracts event metadata from a Telegram message text:
    - event_name: human-readable label (e.g. 'Weekly Boost', 'Bonus Drop')
    - event_type: canonical type string (e.g. 'WEEKLY BOOST', 'DROP')
    - event_datetime: parsed datetime from textual date mentions
    """
    result: Dict[str, Any] = {
        "event_name": None,
        "event_type": "DROP",
        "event_datetime": None,
    }
    if not text:
        return result

    for pattern, ev_type in _EVENT_TYPE_PATTERNS:
        if pattern.search(text):
            result["event_type"] = ev_type
            break

    for pattern, ev_name in _EVENT_NAME_PATTERNS:
        if pattern.search(text):
            result["event_name"] = ev_name
            break

    explicit_m = _RE_EVENT_NAME_EXPLICIT.search(text)
    if explicit_m:
        result["event_name"] = explicit_m.group(1).strip()

    event_dt = extract_event_datetime(text)
    if event_dt:
        result["event_datetime"] = event_dt

    return result


def extract_code_from_ocr_text(ocr_text: str) -> Optional[str]:
    """
    Extracts the most likely bonus code from OCR-extracted text.
    Returns None if no valid code candidate is found.
    """
    from scrapers.ocr import OCRClient
    return OCRClient().extract_code(ocr_text)


def resolve_placeholder_code(
    item: BonusCodeItem,
    ocr_client: Optional[OCRClient] = None,
    photo_bytes: Optional[bytes] = None,
) -> BonusCodeItem:
    """
    If the item's code is a placeholder (CHECK_IMAGE_FOR_CODE / DEGEN_DROP / QZINO_EVENT),
    attempts to OCR the attached image and replace the code with the extracted real code.
    If OCR fails or no code is found, the original placeholder code is preserved
    (the item remains valid and will still be tracked as an event).
    Returns the (possibly modified) BonusCodeItem.
    """
    if not should_ocr_code(item.code):
        return item

    client = ocr_client or get_ocr_client()
    if not client.is_available:
        logger.debug(f"OCR not available; preserving placeholder code '{item.code}' for {item.platform.value}")
        return item

    extracted = None
    if photo_bytes:
        extracted = client.ocr_code_from_bytes(photo_bytes)
    elif item.image_url:
        extracted = client.ocr_code(item.image_url)

    if extracted:
        logger.info(
            f"OCR resolved placeholder '{item.code}' -> '{extracted}' for {item.platform.value}"
        )
        item.code = extracted
    elif not item.image_url and not photo_bytes:
        logger.debug(f"No image available for OCR placeholder '{item.code}' on {item.platform.value}")
    else:
        logger.debug(f"OCR did not resolve a code for '{item.code}' on {item.platform.value}")

    return item
