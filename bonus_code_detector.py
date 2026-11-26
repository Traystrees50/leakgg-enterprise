import re
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from models import BonusCodeItem, Platform
from filters import extract_event_datetime
from scrapers.ocr import OCRClient, get_ocr_client, extract_banner_drop_details

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
    "GOATED_DROP_",
)

# Platforms that use banner images and need two-pass OCR + banner parser
_BANNER_PLATFORMS = {Platform.GOATED, Platform.DEGEN}

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

# Placeholder text patterns to suppress in embed descriptions
_PLACEHOLDER_TEXT_PATTERNS = re.compile(
    r"(?:check\s+(?:the\s+)?image\s+for\s+code"
    r"|see\s+image\s+for\s+code"
    r"|code\s+in\s+image"
    r"|view\s+(?:attached\s+)?(?:event\s+)?graphic)",
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
    if c in ("CHECK_IMAGE_FOR_CODE", "QZINO_PROMO"):
        return True
    return False


def is_banner_platform(platform: Platform) -> bool:
    """Returns True for platforms that use event banner images (Goated, Degen)."""
    return platform in _BANNER_PLATFORMS


def detect_event_from_message(text: str) -> Dict[str, Any]:
    """
    Extracts event metadata from a Telegram message text.
    Returns: event_name, event_type, event_datetime
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
    """Extracts the most likely bonus code from OCR-extracted text."""
    return OCRClient().extract_code(ocr_text)


def _suppress_placeholder_text(description: Optional[str]) -> Optional[str]:
    """Remove placeholder strings from embed description."""
    if not description:
        return description
    cleaned = _PLACEHOLDER_TEXT_PATTERNS.sub("", description).strip()
    # Collapse multiple blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned if cleaned else None


def resolve_placeholder_code(
    item: BonusCodeItem,
    ocr_client: Optional[OCRClient] = None,
    photo_bytes: Optional[bytes] = None,
) -> BonusCodeItem:
    """
    Resolves placeholder codes for ALL platforms via OCR.

    For Goated and Degen (banner platforms):
    - Uses two-pass OCR (engine=2 first, engine=1 fallback)
    - Runs extract_banner_drop_details to get code, amount, and wager
    - Suppresses all placeholder description text when a real code is found
    - Always preserves item.image_url (embed.setImage equivalent)
    - Only shows fallback message if BOTH passes fail

    For all other platforms:
    - Standard single-pass OCR as before
    """
    if not should_ocr_code(item.code):
        return item

    client = ocr_client or get_ocr_client()
    if not client.is_available:
        logger.debug(
            f"OCR not available; preserving placeholder '{item.code}' "
            f"for {item.platform.value}"
        )
        return item

    # ── Banner platforms: two-pass OCR + banner parser ──────────────────────
    if is_banner_platform(item.platform):
        ocr_text = None
        if photo_bytes:
            ocr_text = client.ocr_image_two_pass(image_bytes=photo_bytes)
        elif item.image_url:
            ocr_text = client.ocr_image_two_pass(image_url=item.image_url)

        if ocr_text:
            logger.debug(
                f"[OCR banner] Raw text for {item.platform.value}: "
                f"{ocr_text[:200]!r}"
            )
            details = extract_banner_drop_details(
                ocr_text, caption_text=item.description or ""
            )
            extracted_code = details.get("code")

            if extracted_code:
                logger.info(
                    f"[OCR banner] Resolved '{item.code}' -> '{extracted_code}' "
                    f"for {item.platform.value}"
                )
                item.code = extracted_code
                # Suppress placeholder description text
                item.description = _suppress_placeholder_text(item.description)
                # Enrich amount/wager if not already set
                if details.get("amount") and (
                    not item.amount_value
                    or item.amount_value.lower().endswith("drop")
                ):
                    item.amount_value = details["amount"]
                if details.get("wager") and (
                    not item.wager_requirement
                    or item.wager_requirement == "Not specified"
                ):
                    item.wager_requirement = details["wager"]
            else:
                # Both passes failed — log raw OCR and set informative fallback
                logger.warning(
                    f"[OCR banner] Could not extract code for "
                    f"'{item.code}' on {item.platform.value}. "
                    f"Raw OCR: {ocr_text[:300]!r}"
                )
                item.description = (
                    "Auto-OCR could not read code \u2014 "
                    "view attached event graphic"
                )
                # image_url is preserved (item.image_url unchanged)
        else:
            logger.debug(
                f"[OCR banner] No OCR text returned for "
                f"'{item.code}' on {item.platform.value}"
            )
            item.description = (
                "Auto-OCR could not read code \u2014 "
                "view attached event graphic"
            )

        return item

    # ── Standard single-pass OCR for all other platforms ────────────────────
    extracted = None
    if photo_bytes:
        extracted = client.ocr_code_from_bytes(photo_bytes)
    elif item.image_url:
        extracted = client.ocr_code(item.image_url)

    if extracted:
        logger.info(
            f"OCR resolved placeholder '{item.code}' -> '{extracted}' "
            f"for {item.platform.value}"
        )
        item.code = extracted
        item.description = _suppress_placeholder_text(item.description)
    elif not item.image_url and not photo_bytes:
        logger.debug(
            f"No image available for OCR placeholder '{item.code}' "
            f"on {item.platform.value}"
        )
    else:
        logger.debug(
            f"OCR did not resolve a code for '{item.code}' "
            f"on {item.platform.value}"
        )

    return item
