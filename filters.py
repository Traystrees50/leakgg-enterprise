import re
import datetime
from datetime import timezone
from typing import Optional, Tuple
from models import BonusCodeItem

MAX_EVENT_AGE_DAYS = 4

# Stop words and false positives from website UI elements, navigation, and static labels
STOP_WORDS = {
    "CODE", "CODES", "PROMO", "BONUS", "CLAIM", "COPIED", "COPY", "PLAY", "NOW",
    "HERE", "VISIT", "STAKE", "REVIEW", "REDEEM", "TERMS", "APPLY", "DETAILS",
    "CLICK", "TABLE", "ACTIVE", "EXPIRED", "LATEST", "TODAY", "NOT NEEDED",
    "NONE", "N/A", "UNKNOWN", "WAITING", "PENDING", "LOADING", "SELECT", "SUBMIT", "BUTTON", "DEPOSIT", "SIGNUP",
    "CASINO", "SWEEPSTAKES", "GAMBLING", "EXCLUSIVE", "UPDATE", "UPDATED", "TRUE",
    "FALSE", "NULL", "UNDEFINED", "VALUE", "EXPIRATION", "DATE", "CHANNEL",
    "TELEGRAM", "DISCORD", "TWITTER", "INSTAGRAM", "CODECOPY", "COPYCODE", "HOW",
    "WHAT", "WHEN", "WHY", "WHERE", "INFO", "FREE", "REWARD", "STATUS", "ACTION",
    "SUMMARY", "OFFER", "PROMOTIONS", "RULES", "VIP", "SOCIAL", "SITE", "TYPE",
    "ELIGIBILITY", "PLAYER", "PLAYERS", "GUIDE", "FAQS", "FAQ", "FACTS",
    "PROMOCODE", "BONUSCODE", "VOUCHERCODE", "NOCODE", "CLAIMCODE", "CLICKHERE",
    "CLAIMNOW", "PROMOTIONS", "EXCLUSIVECODE", "AFFILIATECODE", "COUPONCODE",
    "GETBONUS", "VISITSITE", "TERMSAPPLY", "PLAYRESPONSIBLY", "GENERALTERMS",
    "ROLLOVER", "CURRENCY", "AVAILABLE", "UNAVAILABLE", "SEPTEMBER", "BILINGUAL",
    "BILLION", "DISPLAY", "DISABLED", "BUTTON", "DROPS", "WELCOME", "REQUIREMENT",
    "PLAYTHROUGH", "OFFER", "REGISTER", "AFFILIATE", "PARTNER", "REVIEWS",
    "COMMUNITY", "WEBSITE", "ONLINE", "CASINOS", "STAKECASINO", "STAKEUS",
    "STAKECOM", "SHUFFLECOM", "SHUFFLEUS", "RAINBETCOM", "QZINOAI", "DEGENDOTCOM",
    "GOATEDCOM", "NEXTPAGE", "NEXTGEN", "PREVIOUS", "HEADER", "FOOTER", "NAVBAR",
    "DROPDOWN", "SIDEBAR", "CONTENT", "CONTAINER", "WRAPPER", "LAYOUT", "TEMPLATE",
    "ELEMENT", "MODULE", "COMPONENT", "WIDGET", "BANNER", "POPUP", "MODAL",
    "DIALOG", "OVERLAY", "BACKDROP", "TOOLTIP", "BADGE", "LABEL", "INPUT",
    "OPTION", "CHECKBOX", "RADIO", "SWITCH", "SLIDER", "LOADER", "SPINNER",
    "ICON", "IMAGE", "AVATAR", "THUMBNAIL", "MEDIA", "VIDEO", "AUDIO", "IFRAME",
    "CANVAS", "SVG", "SCRIPT", "STYLE", "NOSCRIPT", "METADATA", "LINK", "META",
    "TITLE", "HEAD", "BODY", "HTML", "LOGIN", "LOGOUT", "SETTINGS", "PROFILE",
    "ACCOUNT", "WALLET", "BALANCE", "TRANSACTIONS", "HISTORY", "NOTIFICATION",
    "NOTIFICATIONS", "MESSAGES", "ALERTS", "FEEDBACK", "SEARCH", "FILTER", "SORT",
    "CATEGORY", "TAGS", "TOPICS", "PAGES", "HOMEPAGE", "NAVIGATION", "MENU"
}

# Regex to detect random telegram drop hashes like 'stakecomeojzgaqsjc709j', 'stakeusnno26bfgqa8dz0'
TELEGRAM_DROP_HASH_REGEX = re.compile(r"^stake(?:com|us)[a-z0-9]{10,}$", re.IGNORECASE)

# Pre-compiled site-specific affiliate / low-wager drop patterns
_SITE_SPECIFIC_PATTERNS = [
    re.compile(r"^BIL[A-Z0-9]{7,10}$"),
    re.compile(r"^NEXT\d[A-Z0-9]{7,22}$"),
    re.compile(r"^DIMERS\d[A-Z0-9]{7,22}$"),
    re.compile(r"^(?:TGHSEPT|HAUSSEPT|GAMEHAUSSEPT|THEGAMESEPT|SEPTREWARD|BONUSSEPT|HAUSREWARD|HAUS\d|TGHSEPTCODE|SEPTTGH)\d*[A-Z0-9]{6,25}$"),
    re.compile(r"^(?:DSNDROP|DSNBONUS|DSN\d|DSBONUS|LATESTDROPS\d|BONUSDROPS\d|DROPSDSN\d|DROP\d+DSN)[A-Z0-9]{3,25}$"),
    re.compile(r"^(?:STAKEUS)?TLC\d{3,5}$"),
    re.compile(r"^(?:JVN|KRX|XPR|YLM)\d{2}[A-Z0-9]{6,25}$"),
]

# Known affiliate partner codes (exact match)
KNOWN_AFFILIATE_CODES = {
    "SPIKESOCIAL", "STFSOCIAL", "TGTSOCIAL", "VIBONUS", "WETSOCIAL",
    "BALLISLIFE", "DEADSPIN", "PROMOBOY", "GAMECHAMPIONS", "THELINES",
    "NEXT", "THEGAMEHAUS", "DIMERS", "JAXON", "SELFMADE",
    # Partner/Affiliate exclusive codes
    "SMKRFREE", "SMKRZE", "KICKFREE", "GAMBLEFREE", "CASINOFREE",
    "RAINBETFREE", "DEGENFREE", "GOATEDFREE", "THRILLFREE", "WINFREE",
}

# Prefixes that indicate image-check or platform-specific codes
_IMAGE_OR_PLATFORM_PREFIXES = ("CHECK_IMAGE", "QZINO_", "STAKE_", "DEGEN_")

def is_site_specific_drop_code(code: str) -> bool:
    """
    Validates whether a code matches known structured affiliate / low-wager drop patterns.
    """
    c = code.strip().upper()
    if c in KNOWN_AFFILIATE_CODES:
        return True
    for pat in _SITE_SPECIFIC_PATTERNS:
        if pat.match(c) and c not in STOP_WORDS:
            return True
    if any(c.startswith(p) for p in _IMAGE_OR_PLATFORM_PREFIXES):
        return True
    return False

# Regex to detect typical low value drop amounts like $1, $2, $3, 1 SC, 2 SC, 3 SC
LOW_VALUE_AMOUNT_REGEX = re.compile(r"^\s*(?:\$|€|£)?\s*(?:0\.[0-9]+|[1-3](?:\.00?)?)\s*(?:sc|stake cash|usd|\$)?\s*$", re.IGNORECASE)

# Regex to detect 7-day rolling wager requirements typical of hourly/daily telegram drops
TELEGRAM_7DAY_WAGER_REGEX = re.compile(r"\b(?:[3-9],\d{3}|[1-9]\d{4,})\s*(?:wagered|in the last 7 days|7-day)\b", re.IGNORECASE)

# Inactive / expired status indicators
EXPIRED_INDICATORS = [
    "expired", "inactive", "outdated", "no longer working", "no longer active",
    "ended", "past event", "not working", "invalid code", "code expired"
]

def extract_event_datetime(text: str) -> Optional[datetime.datetime]:
    """
    Attempts to parse date/timestamp from various string formats found across Telegram,
    HTML tables, and review cards.
    """
    if not text:
        return None

    # 1. ISO format: 2026-09-06T14:23:10+00:00 or 2026-09-06 14:23:10
    iso_m = re.search(r"\b(\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?(?:[Zz]|[\+\-]\d{2}:?\d{2})?)?)\b", text)
    if iso_m:
        val = iso_m.group(1).replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass

    # 2. US Date with optional time: e.g. 8/25/2026 3:03 PM or 08/25/2026 or 9/7/2026
    us_m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?)?\b", text, re.I)
    if us_m:
        month, day, year = int(us_m.group(1)), int(us_m.group(2)), int(us_m.group(3))
        hour = int(us_m.group(4)) if us_m.group(4) else 0
        minute = int(us_m.group(5)) if us_m.group(5) else 0
        second = int(us_m.group(6)) if us_m.group(6) else 0
        ampm = us_m.group(7)
        if ampm:
            if ampm.upper() == "PM" and hour < 12:
                hour += 12
            elif ampm.upper() == "AM" and hour == 12:
                hour = 0
        try:
            return datetime.datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        except Exception:
            pass

    # 3. Named month format: e.g. August 25, 2026 or Aug 25 2026 or 25 Aug 2026
    month_map = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
        "nov": 11, "november": 11, "dec": 12, "december": 12
    }
    month_pats = "|".join(month_map.keys())
    named_m = re.search(rf"\b({month_pats})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", text, re.I)
    if named_m:
        m_name = named_m.group(1).lower()
        month = month_map.get(m_name, 1)
        day = int(named_m.group(2))
        year = int(named_m.group(3))
        try:
            return datetime.datetime(year, month, day, tzinfo=timezone.utc)
        except Exception:
            pass

    return None

def is_event_recent(
    dt: Optional[datetime.datetime] = None,
    max_days: int = MAX_EVENT_AGE_DAYS,
    text: Optional[str] = None,
    reference_dt: Optional[datetime.datetime] = None
) -> Tuple[bool, str]:
    """
    Validates whether an event timestamp or textual date falls within the past `max_days` (default 4 days).
    Returns (True, "") if recent, or (False, reason) if older than 4 days or marked expired.
    """
    now = reference_dt or datetime.datetime.now(timezone.utc)

    # 1. Check explicit expired status in text
    if text:
        t_low = text.lower()
        for exp in EXPIRED_INDICATORS:
            if re.search(rf"\b{re.escape(exp)}\b", t_low):
                return False, f"Event marked as expired/inactive ('{exp}')"

        # Check relative age in text (e.g. '5 days ago', '2 weeks ago', '1 month ago')
        rel_days_m = re.search(r"\b(\d+)\s*days?\s*ago\b", t_low)
        if rel_days_m:
            days_count = int(rel_days_m.group(1))
            if days_count > max_days:
                return False, f"Event occurred {days_count} days ago (exceeds {max_days}-day limit)"

        if any(rel in t_low for rel in ["week ago", "weeks ago", "month ago", "months ago", "year ago", "years ago"]):
            return False, "Event relative date indicates it is older than 4 days"

    # 2. If datetime is not provided, try to extract from text
    target_dt = dt
    if target_dt is None and text:
        target_dt = extract_event_datetime(text)

    # 3. If a date is known, verify age
    if target_dt:
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)

        age_seconds = (now - target_dt).total_seconds()
        max_seconds = max_days * 86400

        # Discard if older than max_days (96 hours)
        if age_seconds > max_seconds:
            days_old = age_seconds / 86400.0
            return False, f"Event date ({target_dt.strftime('%Y-%m-%d %H:%M UTC')}) is {days_old:.1f} days old (exceeds {max_days}-day limit)"

    return True, ""

def is_telegram_or_low_value_drop(code: str, amount: str = "", wager: str = "", context: str = "") -> Tuple[bool, str]:
    """
    Returns (True, reason) if the code is a generic Telegram/social bonus drop hash pasted on web pages,
    or (False, "") if it is an affiliate/exclusive low-wager bonus code.
    """
    c = code.strip()

    # If code matches a known site-specific / affiliate low-wager pattern, keep it
    if is_site_specific_drop_code(c):
        if not TELEGRAM_DROP_HASH_REGEX.match(c):
            return False, ""

    # 1. Matches automated Stake drop hash format (e.g., stakecommp30u9tyrkd2d1)
    if TELEGRAM_DROP_HASH_REGEX.match(c):
        return True, "Automated Telegram/Social drop hash format (stakecom... / stakeus...)"

    # 2. Check low value drops (e.g. $1, $2, $3, 1 SC) paired with telegram/7-day wager patterns
    if amount and LOW_VALUE_AMOUNT_REGEX.match(amount.strip()) and ("telegram" in context.lower() or "t.me" in context.lower()):
        return True, f"Telegram drop low value amount ({amount})"

    # 3. Check for telegram drop specific requirements (e.g. $12,000 wagered in last 7 days for small drop)
    if wager and TELEGRAM_7DAY_WAGER_REGEX.search(wager) and ("telegram" in context.lower() or "t.me" in context.lower()):
        return True, f"Telegram drop high 7-day wager constraint ({wager})"

    # 4. Check context indicators
    ctx_lower = context.lower()
    if ("telegram" in ctx_lower or "t.me/" in ctx_lower) and ("$1" in ctx_lower or "$2" in ctx_lower or "$3" in ctx_lower):
        # Only reject if it's clearly a social/automatic drop (hash format + low value)
        if TELEGRAM_DROP_HASH_REGEX.match(c):
            return True, "Context indicates Telegram social drop table"
        if wager and TELEGRAM_7DAY_WAGER_REGEX.search(wager):
            return True, f"Low value Telegram drop with 7-day wager constraint"

    return False, ""

def is_valid_affiliate_code(item: BonusCodeItem, max_days: int = MAX_EVENT_AGE_DAYS, reference_dt: Optional[datetime.datetime] = None) -> Tuple[bool, str]:
    """
    Validates whether a BonusCodeItem represents a genuine affiliate / promotional bonus code
    and falls strictly within the past 4 days.
    """
    code = item.clean_code.upper()

    # 1. Age check (no longer than past 4 days)
    is_recent, reason = is_event_recent(
        dt=item.event_datetime,
        max_days=max_days,
        text=item.description or "",
        reference_dt=reference_dt
    )
    if not is_recent:
        return False, f"Event too old: {reason}"

    # 2. Length sanity check
    if len(code) < 3 or len(code) > 35:
        return False, f"Invalid code length ({len(code)})"

    # 3. Stop words
    if code in STOP_WORDS:
        return False, f"Code matches stop-word '{code}'"

    # Check if it's a known affiliate code (allow even without numbers)
    if code in KNOWN_AFFILIATE_CODES:
        return True, "Valid known affiliate code"

     # 4. Must contain at least one letter and not only special chars
    if not re.search(r"[A-Z]", code):
        return False, "Code does not contain alphabetic characters"

    if re.search(r"^[0-9]+$", code):
        return False, "Numeric only code"

    # Reject codes with special characters (spaces, unicode symbols, etc.)
    # Real bonus codes are alphanumeric with at most hyphens/underscores
    if not re.match(r"^[A-Za-z0-9_\-]+$", code):
        return False, f"Code contains special characters: '{code}'"

    # 5. Check if it's a common lowercase dictionary word or static UI text without numbers
    # (unless it's in KNOWN_AFFILIATE_CODES or is_site_specific_drop_code)
    # Platform names that have dedicated parsers and are always valid when detected
    _PLATFORM_CODE_EXCEPTIONS = {"THRILL", "WINNA", "GOATED", "DEGEN", "QZINO", "RAINBET", "SHUFFLE", "STAKE"}
    if not is_site_specific_drop_code(code):
        if not re.search(r"\d", code):
            # Allow platform-related alpha codes for platforms with dedicated parsers
            if code.upper() in _PLATFORM_CODE_EXCEPTIONS:
                pass
            elif len(code) < 5:
                return False, f"Non-numeric token '{code}' rejected as static text (too short)"
            elif code.upper() in STOP_WORDS:
                return False, f"Non-numeric token '{code}' rejected as static text (stop word)"
            else:
                # Use a dictionary check for longer alpha-only strings
                _COMMON_DICT_WORDS = {
                    "BILINGUAL", "BILLING", "BILLION", "NEXTPAGE", "NEXTGEN", "DISABLED", "DISPLAY",
                    "DISCUSSION", "SEPTEMBER", "BUTTON", "PROMOCODE", "BONUSCODE", "CLICKHERE",
                    "CLAIMNOW", "EXCLUSIVE", "CONTENT", "STAKECASINO", "FOOTER", "HEADER", "MENU",
                    "NEXTPAGE", "FOOTER", "SIDEBAR", "NAVBAR", "CONTAINER", "WRAPPER", "TEMPLATE",
                    "ELEMENT", "MODULE", "COMPONENT", "WIDGET", "BANNER", "POPUP", "MODAL",
                    "DIALOG", "OVERLAY", "BACKDROP", "TOOLTIP", "BADGE", "LABEL", "INPUT",
                    "OPTION", "CHECKBOX", "RADIO", "SWITCH", "SLIDER", "LOADER", "SPINNER",
                    "ICON", "IMAGE", "AVATAR", "THUMBNAIL", "MEDIA", "VIDEO", "AUDIO", "IFRAME",
                    "CANVAS", "SVG", "SCRIPT", "STYLE", "NOSCRIPT", "METADATA", "LINK", "META",
                    "TITLE", "HEAD", "BODY", "HTML", "LOGIN", "LOGOUT", "SETTINGS", "PROFILE",
                    "ACCOUNT", "WALLET", "BALANCE", "TRANSACTIONS", "HISTORY", "NOTIFICATION",
                    "NOTIFICATIONS", "MESSAGES", "ALERTS", "FEEDBACK", "SEARCH", "FILTER", "SORT",
                    "CATEGORY", "TAGS", "TOPICS", "PAGES", "HOMEPAGE", "NAVIGATION", "MENU",
                    "AVAILABLE", "UNAVAILABLE", "PLAYERS", "PLAYER", "GUIDE", "FAQS", "FAQ",
                    "FACTS", "PROMOTIONS", "RULES", "SOCIAL", "SITE", "TYPE", "ELIGIBILITY",
                    # Strafe.com UI labels falsely extracted as codes
                    "STRAFECASVIP", "STRAFECASINO", "STRAFESPORT", "STFSPOGLO",
                }
                if code.upper() in _COMMON_DICT_WORDS:
                    return False, f"Alpha-only token '{code}' rejected as common dictionary word"

    # 6. Check Telegram / low-value drop filter
    is_tg, reason = is_telegram_or_low_value_drop(
        code=item.code,
        amount=item.amount_value,
        wager=item.wager_requirement,
        context=item.description or ""
    )
    if is_tg:
        return False, f"Filtered as Telegram/Low-value drop: {reason}"

    return True, "Valid affiliate bonus code"
