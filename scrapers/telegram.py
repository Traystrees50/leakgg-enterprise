import re
import logging
import threading
import unicodedata
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from models import BonusCodeItem, Platform
from config import HTTP_HEADERS, REQUEST_TIMEOUT, TELEGRAM_CHANNELS, ENABLE_JITTER, ENABLE_PROXY_ROTATION, TELEGRAM_PRIVATE_SOURCES
from filters import extract_event_datetime, is_event_recent, is_valid_affiliate_code, MAX_EVENT_AGE_DAYS
from network_manager import ResilientSession

try:
    from bonus_code_detector import resolve_placeholder_code, should_ocr_code
except Exception:
    resolve_placeholder_code = None
    should_ocr_code = None

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for high-frequency parsing
_RE_CODE_GENERIC = re.compile(r"(?:code|promo\s*code|drop\s*code|claim\s*code|use\s*code)[:\s=]+([A-Za-z0-9_\-]+)", re.I)
_RE_CODE_STANDALONE = re.compile(r"\b([A-Z0-9]{5,20})\b")
_RE_CODE_CODESTATS = re.compile(
    r"(?:^|[\r\n])\s*(?:[-•]\s*)?Code\s*:\s*([A-Za-z0-9_\-]{4,35})\b",
    re.I
)
_RE_CODE_HASH = re.compile(r"\b(stake(?:com|us)[a-z0-9]{6,25})\b", re.I)
_RE_CODE_RAINBET = re.compile(r"(?:Click\s+Code\s+To\s+Copy|Code)[:\s]+([A-Za-z0-9_\-]+)", re.I)
_RE_CODE_QZINO_STANDALONE = re.compile(r"\n\s*([A-Za-z0-9]{4,16})\s*\n\s*-\s*(?:Value|Total|Requirement)", re.I)
_RE_VALUE_GENERIC = re.compile(r"(?:Claim\s*Amount|Amount|Reward|Value)[:\s]+(\$?[0-9.,]+(?:\s*USD|\s*SC|\%)?(?:\s*\+\s*\d+\s*FS)?)", re.I)
_RE_WAGER_GENERIC = re.compile(r"(?:7\s*Day\s*Wager\s*Requirement|Wager\s*Requirement|Wager\s*Required|Wager)[:\s]+(\$?[0-9,]+(?:\s*wagered)?)", re.I)
_RE_CLAIMS_GENERIC = re.compile(r"(?:Total\s*Claims|Claims|Claim\s*Limit)[:\s]+([0-9,]+)", re.I)
_RE_WAGER_ALT = re.compile(r"(\$[0-9,]+\s*(?:wagered|wager|rollover))", re.I)
_RE_VALUE_ALT = re.compile(r"(\$\d+(?:\.\d+)?\s*(?:USD|SC|FREE|BONUS)?)", re.I)
_RE_STAKE_US_LINK = re.compile(r"https?://(?:www\.)?stake\.us/settings/offers[^\s\)]+", re.I)
_RE_STAKE_COM_LINK = re.compile(r"https?://(?:www\.)?stake\.com/settings/offers[^\s\)]+", re.I)
_RE_SHUFFLE_LINK = re.compile(r"https?://(?:www\.)?shuffle\.(?:com|us)/[^\s\)]+", re.I)
_RE_QZINO_LINK = re.compile(r"https?://(?:qzino\.(?:com|ai)/[^\s]+|t\.me/[^\s]+)", re.I)
_RE_EMBED_LINKS = re.compile(r"https?://[^\s\)]+", re.I)

_PROMO_FOOTER_MARKERS = [
    "Active Codes – Codez.gg",
    "Use code JIM on Winna:",
    "JimmyMoney.gg",
]

def strip_promo_footer(text: str) -> str:
    if not text:
        return ""
    idx = len(text)
    for marker in _PROMO_FOOTER_MARKERS:
        m = text.find(marker)
        if m != -1:
            idx = min(idx, m)
    if idx < len(text):
        text = text[:idx]
    return text.strip()

def clean_codestats_promos(text: str) -> str:
    """
    Strips promotional headers, footers, autoclaimer URLs, and Cloud Claimer ads from CodeStats messages.
    """
    if not text:
        return ""
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        l_strip = line.strip()
        l_lower = l_strip.lower()
        if any(marker in l_lower for marker in [
            "codestats.gg",
            "autoclaimer",
            "cloud claimer",
            "no computer?",
            "missed it?",
            "claim more codes",
            "sign up for shuffle",
            "don't blink",
            "claim the code now at",
            "support the community share the codes"
        ]):
            continue
        cleaned_lines.append(l_strip)
    return "\n".join([ln for ln in cleaned_lines if ln]).strip()

class TelegramScraper:
    def __init__(self, channels: Optional[Dict[str, List[str]]] = None, timeout: int = REQUEST_TIMEOUT, telegram_api_client: Optional[Any] = None):
        self.channels = channels or TELEGRAM_CHANNELS
        self.timeout = timeout
        self.session = ResilientSession(
            timeout=self.timeout,
            enable_jitter=ENABLE_JITTER,
            enable_proxy_rotation=ENABLE_PROXY_ROTATION
        )
        self.telegram_api_client = telegram_api_client
        if self.telegram_api_client and not getattr(self.telegram_api_client, "is_available", False):
            err = getattr(self.telegram_api_client, "error_message", "Telegram API client unavailable")
            logger.warning(f"Telegram API client not available: {err}")

    def fetch_channel_html(self, channel_name: str) -> Optional[str]:
        """
        Fetches the public preview page for a Telegram channel (https://t.me/s/{channel_name}).
        Uses resilient session with jitter, UA rotation, and backoff.
        """
        clean_name = channel_name.replace("@", "").replace("https://t.me/s/", "").replace("https://t.me/", "").strip()
        # If it's a private join link like c/1542279201, preview is not web-accessible without auth, but we handle gracefully
        if clean_name.startswith("c/") or clean_name.startswith("+"):
            logger.info(f"Telegram channel '{channel_name}' is private. For private groups, use Telegram client credentials in .env.")
            return None

        url = f"https://t.me/s/{clean_name}"
        try:
            return self.session.fetch_text(url, headers=HTTP_HEADERS)
        except Exception as e:
            logger.warning(f"Failed to fetch Telegram preview for @{clean_name}: {e}")
            return None

    @staticmethod
    def is_avatar_or_profile_url(url: str) -> bool:
        """
        Detects if a URL is a Telegram profile/avatar/userpic image rather than message media content.
        """
        if not url:
            return True
        u_lower = url.lower()
        if any(marker in u_lower for marker in [
            "userpic", "avatar", "profile_photos", "tgme_page_photo",
            "channel_avatar", "user_avatar", "emoji"
        ]):
            return True
        return False

    def extract_image_url_from_wrap(self, wrap_tag) -> Optional[str]:
        """
        Extracts image or video thumbnail URL strictly from Telegram post media elements.
        Strictly ignores channel profile pictures, user avatars, and emojis.
        """
        if not wrap_tag:
            return None

        # Ignore if the wrap tag itself is an avatar/profile container
        tag_classes = wrap_tag.get("class", [])
        if any(cls in tag_classes for cls in [
            "tgme_widget_message_user_photo", "tgme_widget_message_user",
            "tgme_widget_message_avatar", "tgme_widget_message_author_photo",
            "tgme_page_photo", "tgme_channel_info_avatar"
        ]):
            return None

        # 1. Look for explicit Telegram post media containers
        media_selectors = [
            ".tgme_widget_message_photo_wrap",
            ".tgme_widget_message_photo",
            ".tgme_widget_message_video_wrap",
            ".tgme_widget_message_video_thumb",
            ".tgme_widget_message_inline_image",
            ".tgme_widget_message_roundvideo_thumb",
            ".tgme_widget_message_grouped_thumb",
            ".link_preview_image",
            ".link_preview_right_image",
            ".tgme_widget_message_link_preview"
        ]

        for selector in media_selectors:
            for el in wrap_tag.select(selector):
                # Check background-image style
                style = el.get("style", "")
                m = re.search(r"background-image:url\(['\"]?([^'\")]+)['\"]?\)", style)
                if m and m.group(1).startswith("http") and not self.is_avatar_or_profile_url(m.group(1)):
                    return m.group(1)

                # Check img tags inside media container
                for img in el.find_all("img"):
                    src = img.get("src")
                    if src and src.startswith("http") and not self.is_avatar_or_profile_url(src):
                        return src

                # Check video poster
                for video in el.find_all("video"):
                    poster = video.get("poster")
                    if poster and poster.startswith("http") and not self.is_avatar_or_profile_url(poster):
                        return poster

        # 2. Check message bubble specifically (where text and post media reside, excluding user avatar)
        bubble = wrap_tag.find(class_="tgme_widget_message_bubble")
        if bubble:
            # Check any background-image inside bubble that is not in author or avatar elements
            for el in bubble.find_all(style=True):
                el_classes = el.get("class", [])
                if any("author" in c or "user" in c or "avatar" in c for c in el_classes):
                    continue
                style = el.get("style", "")
                m = re.search(r"background-image:url\(['\"]?([^'\")]+)['\"]?\)", style)
                if m and m.group(1).startswith("http") and not self.is_avatar_or_profile_url(m.group(1)):
                    return m.group(1)

            for img in bubble.find_all("img"):
                img_classes = img.get("class", [])
                if any("author" in c or "user" in c or "avatar" in c or "emoji" in c for c in img_classes):
                    continue
                src = img.get("src")
                if src and src.startswith("http") and not self.is_avatar_or_profile_url(src):
                    return src

            for video in bubble.find_all("video"):
                poster = video.get("poster")
                if poster and poster.startswith("http") and not self.is_avatar_or_profile_url(poster):
                    return poster

        return None

    def parse_rainbet_message(self, text: str, msg_url: str, image_url: Optional[str] = None, event_datetime: Optional[Any] = None) -> Optional[BonusCodeItem]:
        """
        Parses Rainbet drop format:
        1. Click Code To Copy: MFQP3DSN
        2. Redeem Here: https://rainbet.com/affiliates?modal=wallet&tab=redeem
        Reward: $1 / $10
        Wager Required: $4,000
        Claims: 600
        """
        code_match = _RE_CODE_RAINBET.search(text)
        if not code_match:
            code_match = _RE_CODE_STANDALONE.search(text)
        if not code_match:
            return None

        code = code_match.group(1).strip()
        if code.upper() in ["RAINBET", "BONUS", "DROP", "HERE", "REDEEM", "CLICK", "WALLET"]:
            return None

        reward_m = _RE_VALUE_GENERIC.search(text)
        reward = reward_m.group(1).strip() if reward_m else "$1.00 Drop"

        wager_m = _RE_WAGER_GENERIC.search(text)
        wager = wager_m.group(1).strip() if wager_m else "$4,000 Wager Requirement"

        claims_m = _RE_CLAIMS_GENERIC.search(text)
        claims = claims_m.group(1).strip() if claims_m else None

        return BonusCodeItem(
            code=code,
            platform=Platform.RAINBET,
            amount_value=reward,
            wager_requirement=wager,
            claims_count=claims,
            source_url=msg_url,
            source_name="@EddiesCodesRainbet",
            is_affiliate=False,
            custom_redeem_link="https://rainbet.com/affiliates?modal=wallet&tab=redeem",
            image_url=image_url,
            event_datetime=event_datetime,
            description=strip_promo_footer(text[:400])
        )

    def parse_winna_message(self, text: str, msg_url: str, image_url: Optional[str] = None, event_datetime: Optional[Any] = None) -> Optional[BonusCodeItem]:
        code_match = _RE_CODE_RAINBET.search(text)
        if not code_match:
            code_match = _RE_CODE_STANDALONE.search(text)
        if not code_match:
            return None

        code = code_match.group(1).strip()
        if code.upper() in ["WINNA", "BONUS", "DROP", "HERE", "REDEEM", "CLICK", "CODE"]:
            return None

        reward_m = _RE_VALUE_GENERIC.search(text)
        reward = reward_m.group(1).strip() if reward_m else "$1.00 Drop"

        wager_m = _RE_WAGER_GENERIC.search(text)
        wager = wager_m.group(1).strip() if wager_m else "$4,000 Wager Requirement"

        claims_m = _RE_CLAIMS_GENERIC.search(text)
        claims = claims_m.group(1).strip() if claims_m else None

        clean_text = strip_promo_footer(text.strip())

        return BonusCodeItem(
            code=code,
            platform=Platform.WINNA,
            amount_value=reward,
            wager_requirement=wager,
            claims_count=claims,
            source_url=msg_url,
            source_name="@EddiesCodesWinna",
            is_affiliate=False,
            custom_redeem_link="https://winna.com/?bonus-center=true&SELFMADE",
            image_url=image_url,
            event_datetime=event_datetime,
            description=clean_text
        )

    def parse_thrill_message(self, text: str, msg_url: str, image_url: Optional[str] = None, event_datetime: Optional[Any] = None) -> Optional[BonusCodeItem]:
        """
        Parses THRILL drop format from @thrillcodes channel.
        Uses Rainbet-style code extraction: 'Click Code To Copy: XXX' or standalone code.
        Forces platform to THRILL regardless of message text content.
        """
        code_match = _RE_CODE_RAINBET.search(text)
        if not code_match:
            code_match = _RE_CODE_STANDALONE.search(text)
        if not code_match:
            return None

        code = code_match.group(1).strip()
        if code.upper() in ["THRILL", "BONUS", "DROP", "HERE", "REDEEM", "CLICK", "CODE"]:
            return None

        reward_m = _RE_VALUE_GENERIC.search(text)
        reward = reward_m.group(1).strip() if reward_m else "$1.00 Drop"

        wager_m = _RE_WAGER_GENERIC.search(text)
        wager = wager_m.group(1).strip() if wager_m else "$4,000 Wager Requirement"

        claims_m = _RE_CLAIMS_GENERIC.search(text)
        claims = claims_m.group(1).strip() if claims_m else None

        clean_text = strip_promo_footer(text.strip())

        return BonusCodeItem(
            code=code,
            platform=Platform.THRILL,
            amount_value=reward,
            wager_requirement=wager,
            claims_count=claims,
            source_url=msg_url,
            source_name="@thrillcodes",
            is_affiliate=False,
            custom_redeem_link="https://thrill.com/?r=selfmade",
            image_url=image_url,
            event_datetime=event_datetime,
            description=clean_text
        )

    def parse_degen_message(self, text: str, msg_url: str, image_url: Optional[str] = None, event_datetime: Optional[Any] = None) -> Optional[BonusCodeItem]:
        """
        Parses Degen.com drops from @degendotcom.
        Promo codes are frequently embedded inside the image graphic.
        Captures the entire event description, claims, wager, amount, and media URL.
        """
        msg_id = msg_url.split("/")[-1] if "/" in msg_url else "drop"

        code = ""
        code_m = _RE_CODE_GENERIC.search(text)
        if code_m:
            candidate = code_m.group(1).strip()
            if candidate.upper() not in ["DROP", "DROPS", "IS", "FOR", "THE", "HERE", "NOW", "DEGEN", "REQUIREMENT", "AMOUNT", "CLAIMS", "CODE"]:
                code = candidate

        if not code:
            stopwords = {
                "DEGEN", "DOTCOM", "BONUS", "CLAIM", "DROP", "DROPS", "HTTP", "HTTPS",
                "TELEGRAM", "POST", "CODE", "WAGER", "REQUIRED", "REQUIREMENT", "AMOUNT",
                "TOTAL", "CLAIMS", "ENJOY", "GOOD", "LUCK", "DEGENS", "FREE", "PROMO",
                "DAY", "DAYS", "AND", "WITH", "YOUR", "HAVE", "FROM", "THIS", "LINK"
            }
            words = [w.strip("!?:;,. ") for w in text.split() if 4 <= len(w.strip("!?:;,. ")) <= 20 and w.strip("!?:;,. ").isalnum()]
            for w in words:
                if w.upper() not in stopwords:
                    code = w
                    break

        if not code and (image_url or "PROMO" in text.upper() or "DROP" in text.upper()):
            code = f"CHECK_IMAGE_FOR_CODE_#{msg_id}" if msg_id != "drop" else "CHECK_IMAGE_FOR_CODE"

        if not code and not image_url and not text:
            return None

        if not code:
            code = f"DEGEN_DROP_{msg_id}"

        val_m = _RE_VALUE_GENERIC.search(text)
        if val_m:
            val = val_m.group(1).strip()
        else:
            v_alt = _RE_VALUE_ALT.search(text)
            val = v_alt.group(1).strip() if v_alt else "$5.00 Degen Drop"

        wager_m = _RE_WAGER_GENERIC.search(text)
        if wager_m:
            wager = wager_m.group(1).strip()
        else:
            w_alt = _RE_WAGER_ALT.search(text)
            wager = w_alt.group(1).strip() if w_alt else "Standard Low Wager"

        claims_m = _RE_CLAIMS_GENERIC.search(text)
        claims = claims_m.group(1).strip() if claims_m else None

        description = strip_promo_footer(text.strip()) if text else "Degen bonus drop code posted with media."

        return BonusCodeItem(
            code=code,
            platform=Platform.DEGEN,
            amount_value=val,
            wager_requirement=wager,
            claims_count=claims,
            source_url=msg_url,
            source_name="@degendotcom",
            is_affiliate=False,
            image_url=image_url,
            custom_redeem_link="https://degen.com/r/selfmade",
            event_datetime=event_datetime,
            description=description
        )

    def parse_qzino_message(self, text: str, msg_url: str, image_url: Optional[str] = None, event_datetime: Optional[Any] = None, channel_name: str = "qzino_code") -> Optional[BonusCodeItem]:
        """
        Parses Qzino events and drops from Telegram channels (e.g. @qzino_code, @qzino).
        Extracts promo code, wager requirement, reward amount, claims, media image, and full event description.
        """
        clean_text = text.strip()
        if clean_text.lower() in ["channel created", "channel photo updated"] and not image_url:
            return None

        msg_id = msg_url.split("/")[-1] if "/" in msg_url else "event"

        code = ""
        m_standalone = _RE_CODE_QZINO_STANDALONE.search(text)
        if m_standalone:
            cand = m_standalone.group(1).strip()
            if cand.upper() not in ["QZINO", "AI", "DROP", "DROPS", "BONUS", "IS", "FOR", "THE", "HERE", "NOW", "CODE", "EXTRA", "URGENT", "WEBSITE"]:
                code = cand

        if not code:
            code_m = _RE_CODE_GENERIC.search(text)
            if code_m:
                candidate = code_m.group(1).strip()
                if candidate.upper() not in ["QZINO", "AI", "DROP", "DROPS", "BONUS", "IS", "FOR", "THE", "HERE", "NOW", "CODE", "EXTRA", "TO"]:
                    code = candidate

        if not code and (image_url or "QZINO" in text.upper() or "BONUS" in text.upper() or "DROP" in text.upper()):
            code = f"CHECK_IMAGE_FOR_CODE_#{msg_id}" if msg_id != "event" else "QZINO_PROMO"

        if not code and not image_url and not text:
            return None

        if not code:
            code = f"QZINO_EVENT_{msg_id}"

        val_m = re.search(r"-\s*Value[:\s]+([^\n\r]+)", text, re.I)
        if not val_m:
            val_m = re.search(r"(?:^|\n)\s*(?:Value|Claim\s*Amount|Reward|Amount|Bonus\s*Amount)[:\s]+([^\n\r]+)", text, re.I)
        if not val_m:
            val_m = _RE_VALUE_GENERIC.search(text)

        if val_m:
            val = val_m.group(1).strip()
        else:
            v_alt = re.search(r"(\d+%\s*(?:\+\s*\d+\s*FS)?|\$?\d+(?:\.\d+)?\s*(?:USD|SC|FREE|BONUS)?)", text, re.I)
            val = v_alt.group(1).strip() if v_alt else "Standard Bonus"

        wager_m = re.search(r"(?:-\s*)?(?:Requirements|Requirement|Wager\s*Requirement|Wager\s*Required|Wager|Playthrough)[:\s]+([^\n\r]+)", text, re.I)
        wager = wager_m.group(1).strip() if wager_m else "Standard Low Wager"

        claims_m = re.search(r"(?:-\s*)?(?:Total\s*Drop|Total\s*Claims|Claims|Claim\s*Limit)[:\s]+([^\n\r]+)", text, re.I)
        claims = claims_m.group(1).strip() if claims_m else None

        link_m = _RE_QZINO_LINK.search(text)
        custom_link = link_m.group(0) if link_m else "https://qzino.com/bonuses"

        clean_ch = channel_name.replace("@", "").strip() if channel_name else "qzino_code"

        return BonusCodeItem(
            code=code,
            platform=Platform.QZINO,
            amount_value=val,
            wager_requirement=wager,
            claims_count=claims,
            source_url=msg_url,
            source_name=f"@{clean_ch}",
            is_affiliate=False,
            image_url=image_url,
            custom_redeem_link=custom_link,
            event_datetime=event_datetime,
            description=strip_promo_footer(clean_text) if clean_text else "Qzino bonus event with media attachment."
        )

    def parse_codestats_message(self, text: str, msg_url: str, image_url: Optional[str] = None, event_datetime: Optional[Any] = None) -> Optional[BonusCodeItem]:
        """
        Parses multi-platform bonus drops from @codestats2 (https://t.me/codestats2).
        Supports:
        - User Submitted Stake Codes: Defaults to Dual Stake (Stake.us & Stake.com) unless explicitly noted as US only or COM only.
        - Stake.us Bonus Drop Alerts (SC drops, wager requirements, claims limit)
        - Stake.com Bonus Drop Alerts (USD drops, wager requirements, claims limit)
        - Shuffle.us Bonus Drop Alerts (SC drops, wager requirements)
        - Shuffle.com Chat Code / Bonus Drop Alerts
        - Rainbet, Qzino, Degen, Goated, and other multi-platform drops
        - Explicitly filters out all CodeStats promotional and affiliate ads.
        """
        if not text:
            return None

        clean_text = clean_codestats_promos(text)
        normalized_text = unicodedata.normalize('NFKD', text)
        t_upper = normalized_text.upper()
        t_lower = normalized_text.lower()

        code = None
        code_m = _RE_CODE_CODESTATS.search(text)
        if not code_m:
            code_m = re.search(r"(?:code|drop|redeem=)([A-Za-z0-9_\-]{4,25})", text, re.I)
        if not code_m:
            hash_m = _RE_CODE_HASH.search(text)
            if hash_m:
                code_m = hash_m

        if not code_m:
            return None

        code = code_m.group(1).strip()
        if code.upper() in ["ALERT", "BONUS", "DROP", "CLAIM", "STAKE", "HERE", "CODE", "SHUFFLE"]:
            return None

        val = None
        val_m = re.search(r"(?:Value|VALUE|Amount|Reward)\s*:\s*([^\n\r]+)", text, re.I)
        if val_m:
            val = val_m.group(1).strip()

        wager = None
        wager_m = re.search(r"(?:Requirements?|REQUIREMENTS?|7-DAY\s*WAGER|7-Day\s*Wager|Wager\s*Required|Wager)[\s:]+([^\n\r]+)", text, re.I)
        if wager_m:
            wager = wager_m.group(1).strip()

        claims = None
        claims_m = re.search(r"(?:Claims?|CLAIMS?|Total\s*Drop\s*Limit|Claim\s*Limit)\s*:\s*([^\n\r]+)", text, re.I)
        if claims_m:
            claims = claims_m.group(1).strip()

        custom_link_us = None
        custom_link_com = None
        custom_link = None

        stake_us_links = _RE_STAKE_US_LINK.findall(text)
        if stake_us_links:
            custom_link_us = stake_us_links[0]

        stake_com_links = _RE_STAKE_COM_LINK.findall(text)
        if stake_com_links:
            custom_link_com = stake_com_links[0]

        shuffle_links = _RE_SHUFFLE_LINK.findall(text)
        if shuffle_links:
            custom_link = shuffle_links[0]

        platform = Platform.UNKNOWN
        is_dual = False

        if "USER SUBMITTED" in t_upper:
            t_without_user = t_upper.replace("USER", "")
            has_us = bool(stake_us_links) or bool(re.search(r"(?:\bUS\b|🇺🇸|STAKE\.US)", t_without_user))
            has_com = bool(stake_com_links) or bool(re.search(r"(?:\bCOM\b|🌏|STAKE\.COM)", t_without_user))

            if has_com and not has_us:
                platform = Platform.STAKE_COM
                is_dual = False
                if not val:
                    val = "User Submitted Stake.com Drop"
            elif has_us and not has_com:
                platform = Platform.STAKE_US
                is_dual = False
                if not val:
                    val = "User Submitted Stake.us Drop"
            else:
                platform = Platform.DUAL_STAKE
                is_dual = True
                if not val:
                    val = "User Submitted (US & COM)"

            if not wager:
                wager = "Standard 7-Day Requirement"

        elif "SHUFFLE.US" in t_upper or ("SHUFFLE" in t_upper and "US" in t_upper and "SC" in t_upper):
            platform = Platform.SHUFFLE_US
            if not val:
                val = "Shuffle.us Bonus Drop"
            if not wager:
                wager = "7-Day Wager Requirement"

        elif "SHUFFLE" in t_upper or "SHUFFLE.COM" in t_upper:
            platform = Platform.SHUFFLE_COM
            if not val:
                val = "Shuffle.com Bonus Drop"
            if not wager:
                wager = "7-Day Wager Requirement"

        elif "STAKE US" in t_upper or "STAKE.US" in t_upper or code.lower().startswith("stakeus"):
            platform = Platform.STAKE_US
            if not val:
                val = "Stake.us Bonus Drop"
            if not wager:
                wager = "Standard 7-Day Requirement"

        elif "STAKE BONUS" in t_upper or "STAKE.COM" in t_upper or code.lower().startswith("stakecom"):
            platform = Platform.STAKE_COM
            if not val:
                val = "Stake.com Bonus Drop"
            if not wager:
                wager = "Standard 7-Day Requirement"

        elif "RAINBET" in t_upper:
            platform = Platform.RAINBET
            if not val:
                val = "Rainbet Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "QZINO" in t_upper:
            platform = Platform.QZINO
            if not val:
                val = "Qzino Bonus Drop"
            if not wager:
                wager = "Standard Low Wager"

        elif "DEGEN" in t_upper:
            platform = Platform.DEGEN
            if not val:
                val = "Degen Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "GOATED" in t_upper:
            platform = Platform.GOATED
            if not val:
                val = "Goated Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "THRILL" in t_upper:
            platform = Platform.THRILL
            if not val:
                val = "Thrill Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "WINNA" in t_upper:
            platform = Platform.WINNA
            if not val:
                val = "Winna Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "PULSZ" in t_upper:
            platform = Platform.PULSZ
            if not val:
                val = "PULSZ Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "MODO" in t_upper:
            platform = Platform.MODO
            if not val:
                val = "MODO Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "BABA" in t_upper or "BABACASINO" in t_upper:
            platform = Platform.BABA
            if not val:
                val = "BABA Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "COOKED.US" in t_upper or "COOKED US" in t_upper:
            platform = Platform.COOKED_US
            if not val:
                val = "COOKED.US Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "COOKED.COM" in t_upper or "COOKED COM" in t_upper:
            platform = Platform.COOKED_COM
            if not val:
                val = "COOKED.COM Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "WOWVEGAS" in t_upper:
            platform = Platform.WOWVEGAS
            if not val:
                val = "WOWVEGAS Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        elif "YAYCASINO" in t_upper:
            platform = Platform.YAYCASINO
            if not val:
                val = "YAYCASINO Bonus Drop"
            if not wager:
                wager = "Standard Wager Requirement"

        else:
            if "sc" in t_lower:
                platform = Platform.STAKE_US
            else:
                platform = Platform.STAKE_COM
            if not val:
                val = "Bonus Drop"
            if not wager:
                wager = "Standard Requirement"

        is_hr = (
            "HIGH ROLLER" in t_upper or
            "HIGHROLLER" in t_upper or
            (wager and any(w in wager.lower() for w in ["50,000", "100,000", "200,000", "50000", "100000"])) or
            (val and any(v in val.lower() for v in ["$12.50", "$25", "$50", "$100", "12.50", "25 sc", "50 sc"]))
        )

        if platform == Platform.THRILL:
            custom_link = "https://thrill.com/?r=selfmade"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.WINNA:
            custom_link = "https://winna.com/?bonus-center=true&SELFMADE"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.PULSZ:
            custom_link = "https://www.pulsz.com/?invited_by=ga1vnk"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.MODO:
            custom_link = "https://modo.us/?referralCode=Z901K9"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.BABA:
            custom_link = "https://play.babacasino.com/#/?referral_id=5403a829ac9926527b94e7c068708e07&inv_referral=true&fb_source=invite"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.COOKED_US:
            custom_link = "https://cooked.us/?auth=register&referral_source=SELFMADE"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.COOKED_COM:
            custom_link = "https://cooked.com/?auth=register&referral_source=SELFMADE"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.WOWVEGAS:
            custom_link = "https://www.wowvegas.com/?raf=1274028"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.YAYCASINO:
            custom_link = "https://www.yaycasino.com/signup/7ab97436-a07a-4514-9506-bcbbcd2495e8"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.MYPRIZE_US:
            custom_link = "https://myprize.us/invite/Traystrees50"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.CROWNSCOINS:
            custom_link = "https://crowncoinscasino.com/?utm_campaign=856db775-8290-42d7-93b4-76ddc67ddf4b&utm_source=friends"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.REALPRIZE:
            custom_link = "https://www.realprize.com/refer/212990"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.ACEBET:
            custom_link = "https://acebet.cc/welcome/r/selfmade"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.LONESTAR:
            custom_link = "https://lonestarcasino.com/refer/869128"
            custom_link_us = None
            custom_link_com = None
        elif platform == Platform.CHANCED:
            custom_link = "https://chanced.com/c/v5a5yh"
            custom_link_us = None
            custom_link_com = None

        return BonusCodeItem(
            code=code,
            platform=platform,
            amount_value=val,
            wager_requirement=wager,
            claims_count=claims,
            source_url=msg_url,
            source_name="@codestats2",
            is_affiliate=False,
            is_highroller=is_hr,
            is_dual_stake=is_dual,
            custom_redeem_link=custom_link,
            custom_redeem_link_us=custom_link_us,
            custom_redeem_link_com=custom_link_com,
            image_url=image_url,
            event_datetime=event_datetime,
            description=strip_promo_footer(clean_text) if clean_text else f"Bonus drop for {platform.value}"
        )

    def parse_stake_message(self, text: str, msg_url: str, channel_name: str, image_url: Optional[str] = None, event_datetime: Optional[Any] = None) -> Optional[BonusCodeItem]:
        """
        Parses drops and VIP events from Telegram channels:
        - Stake.us drops & VIP Weekly/Monthly Boosts (e.g. from @dailybonuscodeUS, @highrollerscodeUS, t.me/c/1542279201/257)
        - Stake.com drops & VIP Weekly/Monthly Boosts (e.g. from @dailybonuscodes, @highrollerscode, t.me/c/2922581483/61)
        - Shuffle.us & Shuffle.com (e.g. from @anyclaimershuffle, @codestats2)
        - Dual Stake drops (US & COM)
        - Captures full event description, media attachments, and clickable redeem URLs.
        """
        normalized_text = unicodedata.normalize('NFKD', text)
        t_upper = normalized_text.upper()
        msg_id = msg_url.split("/")[-1] if "/" in msg_url else "event"

        if "WEEKLY BOOST" in t_upper or "WEEKLY BONUS" in t_upper or "MONTHLY BONUS" in t_upper or "VIP EVENT" in t_upper or "VIP NOTICE" in t_upper:
            is_us = (
                "1542279201" in channel_name or
                "1542279201" in msg_url or
                "1542279201" in text or
                "highrollerscodeus" in channel_name.lower() or
                "dailybonuscodeus" in channel_name.lower() or
                "stake.us" in text.lower() or
                "stakeus" in text.lower() or
                "US" in channel_name.upper()
            )
            is_com = (
                "2922581483" in channel_name or
                "2922581483" in msg_url or
                "2922581483" in text or
                "highrollerscode" in channel_name.lower() or
                "dailybonuscodes" in channel_name.lower() or
                "stake.com" in text.lower() or
                "stakecom" in text.lower()
            )
            if is_us and not is_com:
                plat = Platform.STAKE_US_VIP_NOTICES
            elif is_com and not is_us:
                plat = Platform.STAKE_COM_VIP_NOTICES
            elif is_us and is_com:
                plat = Platform.STAKE_US_VIP_NOTICES
            else:
                plat = Platform.STAKE_COM_VIP_NOTICES
            
            if "WEEKLY BOOST" in t_upper or "WEEKLY BONUS" in t_upper:
                ev_type = "weekly_bonus"
                code_name = f"STAKE_{'US' if plat == Platform.STAKE_US_VIP_NOTICES else 'COM'}_WEEKLY_BOOST_#{msg_id}"
                amount = "VIP Weekly Boost Claim Link"
            elif "POST MONTHLY" in t_upper:
                ev_type = "post_monthly_bonus"
                code_name = f"STAKE_{'US' if plat == Platform.STAKE_US_VIP_NOTICES else 'COM'}_POST_MONTHLY_BONUS_#{msg_id}"
                amount = "Post Monthly Bonus Claim Link"
            elif "MONTHLY BONUS" in t_upper:
                ev_type = "monthly_bonus"
                code_name = f"STAKE_{'US' if plat == Platform.STAKE_US_VIP_NOTICES else 'COM'}_MONTHLY_BONUS_#{msg_id}"
                amount = "VIP Monthly Bonus Claim Link"
            else:
                ev_type = "vip_notice"
                code_name = f"STAKE_{'US' if plat == Platform.STAKE_US_VIP_NOTICES else 'COM'}_VIP_NOTICE_#{msg_id}"
                amount = "VIP Exclusive Notice"

            links = _RE_EMBED_LINKS.findall(text)
            claim_link = links[0] if links else (plat.base_url)

            return BonusCodeItem(
                code=code_name,
                platform=plat,
                amount_value=amount,
                wager_requirement="VIP Tier Based",
                source_url=msg_url,
                source_name=f"@{channel_name}",
                is_affiliate=False,
                event_type=ev_type,
                image_url=image_url,
                custom_redeem_link=claim_link,
                event_datetime=event_datetime,
                description=strip_promo_footer(text.strip())
            )

        if "SHUFFLE.US" in t_upper or ("SHUFFLE" in t_upper and "US" in t_upper and "SC" in t_upper):
            code_m = _RE_CODE_CODESTATS.search(text)
            if not code_m:
                code_m = re.search(r"\b([A-Z0-9]{6,16})\b", text)
            if code_m:
                val_m = re.search(r"Value\s*:\s*([^\n]+)", text, re.I)
                wager_m = re.search(r"(?:Requirements?|REQUIREMENTS?|7-DAY\s*WAGER|7-Day\s*Wager|Wager\s*Required|Wager)[\s:]+([^\n\r]+)", text, re.I)
                claims_m = re.search(r"Claims?\s*:\s*([0-9,]+)", text, re.I)
                return BonusCodeItem(
                    code=code_m.group(1).strip(),
                    platform=Platform.SHUFFLE_US,
                    amount_value=val_m.group(1).strip() if val_m else "Shuffle.us Drop",
                    wager_requirement=wager_m.group(1).strip() if wager_m else "7-Day Wager Requirement",
                    claims_count=claims_m.group(1).strip() if claims_m else None,
                    source_url=msg_url,
                    source_name=f"@{channel_name}",
                    is_affiliate=False,
                    image_url=image_url,
                    event_datetime=event_datetime,
                    description=strip_promo_footer(text.strip())
                )

        if ("SHUFFLE" in t_upper and "STAKE" not in t_upper) or "ANYCLAIMERSHUFFLE" in channel_name.upper():
            code_m = _RE_CODE_CODESTATS.search(text)
            if not code_m:
                code_m = re.search(r"\b([A-Z0-9]{6,16})\b", text)
            if code_m:
                val_m = re.search(r"Value\s*:\s*([^\n]+)", text, re.I)
                wager_m = re.search(r"(?:Requirements?|REQUIREMENTS?|7-DAY\s*WAGER|7-Day\s*Wager|Wager\s*Required|Wager)[\s:]+([^\n\r]+)", text, re.I)
                claims_m = re.search(r"Claims?\s*:\s*([0-9,]+)", text, re.I)
                return BonusCodeItem(
                    code=code_m.group(1).strip(),
                    platform=Platform.SHUFFLE_COM,
                    amount_value=val_m.group(1).strip() if val_m else "Shuffle.com Drop",
                    wager_requirement=wager_m.group(1).strip() if wager_m else "7-Day Wager Requirement",
                    claims_count=claims_m.group(1).strip() if claims_m else None,
                    source_url=msg_url,
                    source_name=f"@{channel_name}",
                    is_affiliate=False,
                    image_url=image_url,
                    event_datetime=event_datetime,
                    description=strip_promo_footer(text.strip())
                )

        is_dual = False
        t_without_user = t_upper.replace("USER", "")
        stake_us_links = _RE_STAKE_US_LINK.findall(text)
        stake_com_links = _RE_STAKE_COM_LINK.findall(text)

        has_stake_us = bool(stake_us_links) or "stake.us" in text.lower() or "us" in channel_name.lower() or bool(re.search(r"(?:\bUS\b|🇺🇸)", t_without_user))
        has_stake_com = bool(stake_com_links) or "stake.com" in text.lower() or ("com" in channel_name.lower() and "us" not in channel_name.lower()) or bool(re.search(r"(?:\bCOM\b|🌏)", t_without_user))
        
        if ("stake.us" in text.lower() and "stake.com" in text.lower()) or ("🇺🇸" in text and "🌏" in text):
            is_dual = True
        elif "USER SUBMITTED" in t_upper:
            if has_stake_com and not has_stake_us:
                is_dual = False
            elif has_stake_us and not has_stake_com:
                is_dual = False
            else:
                is_dual = True

        code_m = _RE_CODE_CODESTATS.search(text)
        if not code_m:
            code_m = re.search(r"(?:code|drop|redeem=)([A-Za-z0-9_\-]{4,25})", text, re.I)
        if not code_m:
            hash_m = _RE_CODE_HASH.search(text)
            if hash_m:
                code_m = hash_m

        if not code_m:
            return None

        code = code_m.group(1).strip()
        if code.upper() in ["ALERT", "BONUS", "DROP", "CLAIM", "STAKE", "HERE"]:
            return None

        val_m = re.search(r"Value\s*:\s*([^\n\r]+)", text, re.I)
        val = val_m.group(1).strip() if val_m else ""
        if not val:
            v_alt = re.search(r"(\$?\d+(?:\.\d+)?\s*(?:SC|Stake Cash|USD)?)", text, re.I)
            val = v_alt.group(1).strip() if v_alt else "Bonus Drop"

        wager_m = re.search(r"(?:Requirements?|REQUIREMENTS?|7-DAY\s*WAGER|7-Day\s*Wager|Wager\s*Required|Wager)[\s:]+([^\n\r]+)", text, re.I)
        wager = wager_m.group(1).strip() if wager_m else ""
        if not wager:
            w_alt = re.search(r"([0-9,]+\s*(?:SC|USD|\$)?\s*(?:played|wagered)[^\n]*)", text, re.I)
            wager = w_alt.group(1).strip() if w_alt else "Standard 7-Day Requirement"

        claims_m = re.search(r"(?:Claim Limit|Total Drop Limit|Claims)\s*:\s*([^\n\r]+)", text, re.I)
        claims = claims_m.group(1).strip() if claims_m else None

        is_hr = (
            "highroller" in channel_name.lower() or
            "HIGH ROLLER" in t_upper or
            "HIGHROLLER" in t_upper or
            any(w in wager.lower() for w in ["50,000", "100,000", "200,000", "50000", "100000"]) or
            any(v in val.lower() for v in ["$12.50", "$25", "$50", "$100", "12.50", "25 sc", "50 sc"])
        )

        if is_dual:
            platform = Platform.DUAL_STAKE
        elif "highrollerscodeus" in channel_name.lower() or "dailybonuscodeus" in channel_name.lower() or "stake.us" in text.lower():
            platform = Platform.STAKE_US
        elif "stake.com" in text.lower() or "dailybonuscodes" in channel_name.lower() or "highrollerscode" in channel_name.lower():
            platform = Platform.STAKE_COM
        else:
            platform = Platform.STAKE_US if "sc" in text.lower() else Platform.STAKE_COM

        return BonusCodeItem(
            code=code,
            platform=platform,
            amount_value=val,
            wager_requirement=wager,
            claims_count=claims,
            source_url=msg_url,
            source_name=f"@{channel_name}",
            is_affiliate=False,
            is_highroller=is_hr,
            is_dual_stake=is_dual,
            image_url=image_url,
            event_datetime=event_datetime,
            description=text.strip()
        )

    def scrape_channel(self, channel_name: str) -> List[BonusCodeItem]:
        """
        Scrapes a single Telegram channel for bonus codes and drops.
        Enforces maximum age of 4 days for all events.
        """
        clean_name = channel_name.replace("@", "").strip()
        html = self.fetch_channel_html(clean_name)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        items: List[BonusCodeItem] = []

        message_wraps = soup.find_all(class_="tgme_widget_message_wrap")
        for wrap in message_wraps:
            text_el = wrap.find(class_="tgme_widget_message_text")
            date_el = wrap.find(class_="tgme_widget_message_date")
            time_el = wrap.find("time")

            msg_url = date_el.get("href") if date_el else f"https://t.me/{clean_name}"
            msg_text = text_el.get_text(separator="\n").strip() if text_el else ""
            img_url = self.extract_image_url_from_wrap(wrap)

            if not msg_text and not img_url:
                continue

            # Extract message timestamp from <time datetime="..."> tag
            msg_dt = None
            if time_el and time_el.get("datetime"):
                msg_dt = extract_event_datetime(time_el.get("datetime"))
            if not msg_dt:
                msg_dt = extract_event_datetime(msg_text)

            # Enforce 4-day maximum age window
            if msg_dt or msg_text:
                is_recent, reason = is_event_recent(dt=msg_dt, max_days=MAX_EVENT_AGE_DAYS, text=msg_text)
                if not is_recent:
                    logger.debug(f"Skipping outdated Telegram drop in @{clean_name}: {reason}")
                    continue

            item: Optional[BonusCodeItem] = None
            if "eddiescodesrainbet" in clean_name.lower():
                item = self.parse_rainbet_message(msg_text, msg_url, img_url, event_datetime=msg_dt)
            elif "winna" in clean_name.lower():
                item = self.parse_winna_message(msg_text, msg_url, img_url, event_datetime=msg_dt)
            elif "thrill" in clean_name.lower():
                item = self.parse_thrill_message(msg_text, msg_url, img_url, event_datetime=msg_dt)
            elif "degendotcom" in clean_name.lower():
                item = self.parse_degen_message(msg_text, msg_url, img_url, event_datetime=msg_dt)
            elif "qzino" in clean_name.lower() or "qzino" in msg_text.lower():
                item = self.parse_qzino_message(msg_text, msg_url, img_url, event_datetime=msg_dt, channel_name=clean_name)
            elif "codestats" in clean_name.lower():
                item = self.parse_codestats_message(msg_text, msg_url, img_url, event_datetime=msg_dt)
            else:
                item = self.parse_stake_message(msg_text, msg_url, clean_name, img_url, event_datetime=msg_dt)

            if item:
                # Validate item
                is_valid, val_reason = is_valid_affiliate_code(item, max_days=MAX_EVENT_AGE_DAYS)
                if is_valid or not item.is_affiliate:
                    # Attempt OCR fallback for placeholder codes (e.g. CHECK_IMAGE_FOR_CODE)
                    if resolve_placeholder_code is not None:
                        item = resolve_placeholder_code(item)
                    # Final age check
                    is_rec, rec_reason = is_event_recent(dt=item.event_datetime, max_days=MAX_EVENT_AGE_DAYS, text=item.description)
                    if is_rec:
                        items.append(item)
                    else:
                        logger.debug(f"Skipping drop '{item.code}' due to age: {rec_reason}")

        return items

    def scrape_all_channels(self, max_workers: int = 6, on_channel_items: Optional[Any] = None, dashboard_manager: Optional[Any] = None) -> List[BonusCodeItem]:
        """
        Sweeps all configured Telegram channels concurrently and returns detected drops.
        Streams newly detected items to `on_channel_items` callback immediately as each channel finishes.
        Deduplicates items across channels in the batch before returning.
        """
        import concurrent.futures

        all_items: List[BonusCodeItem] = []
        unique_channels = set()
        for ch_list in self.channels.values():
            for ch in ch_list:
                unique_channels.add(ch)

        # Add private Telegram sources if dashboard_manager is provided
        private_sources: Dict[str, Dict[str, Any]] = {}
        if dashboard_manager:
            private_sources = dashboard_manager.get_telegram_private_sources()
            for chat_id, meta in private_sources.items():
                unique_channels.add(f"__private__{chat_id}")

        logger.info(f"Scanning {len(unique_channels)} Telegram sources concurrently for drops and low-wager codes...")
        seen_keys = set()
        dedup_lock = threading.Lock()
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(unique_channels) or 1)) as executor:
            future_to_ch = {}
            for ch in unique_channels:
                if ch.startswith("__private__"):
                    chat_id = ch.replace("__private__", "")
                    future_to_ch[executor.submit(self.scrape_private_channel, chat_id)] = ch
                else:
                    future_to_ch[executor.submit(self.scrape_channel, ch)] = ch

            for future in concurrent.futures.as_completed(future_to_ch):
                ch = future_to_ch[future]
                try:
                    items = future.result()
                    display_name = private_sources.get(ch.replace("__private__", ""), {}).get("label", ch) if ch.startswith("__private__") else f"@{ch}"
                    logger.info(f"Scraped Telegram {display_name}: found {len(items)} items")
                    channel_new = []
                    with dedup_lock:
                        for it in items:
                            c_clean = it.code.strip()
                            key = f"{it.platform.value}:{c_clean}"
                            if key not in seen_keys:
                                # Cross-platform in-batch check
                                if it.platform in [Platform.STAKE_US, Platform.STAKE_COM, Platform.DUAL_STAKE, Platform.STAKE_US_VIP_NOTICES, Platform.STAKE_COM_VIP_NOTICES]:
                                    if f"Dual Stake:{c_clean}" in seen_keys or (it.platform == Platform.STAKE_US and f"Stake.us:{c_clean}" in seen_keys) or (it.platform == Platform.STAKE_COM and f"Stake.com:{c_clean}" in seen_keys):
                                        continue
                                    seen_keys.add(f"Dual Stake:{c_clean}")
                                    seen_keys.add(f"Stake.us:{c_clean}")
                                    seen_keys.add(f"Stake.com:{c_clean}")
                                elif it.platform in [Platform.SHUFFLE_US, Platform.SHUFFLE_COM]:
                                    if f"Shuffle.us:{c_clean}" in seen_keys or f"Shuffle.com:{c_clean}" in seen_keys:
                                        continue
                                    seen_keys.add(f"Shuffle.us:{c_clean}")
                                    seen_keys.add(f"Shuffle.com:{c_clean}")

                                seen_keys.add(key)
                                channel_new.append(it)
                                all_items.append(it)
                    if channel_new and on_channel_items:
                        try:
                            on_channel_items(channel_new)
                        except Exception as cb_err:
                            logger.error(f"Error in on_channel_items callback for {display_name}: {cb_err}")
                except Exception as e:
                    logger.error(f"Error scraping Telegram source {ch}: {e}")

        return all_items

    def scrape_private_channel(self, chat_id: str) -> List[BonusCodeItem]:
        """
        Scrapes a private Telegram channel/chat using the Telegram API client if available.
        Falls back to empty list if API client is not configured.
        """
        items: List[BonusCodeItem] = []
        if not self.telegram_api_client or not getattr(self.telegram_api_client, "is_available", False):
            logger.debug(f"Private Telegram source {chat_id} skipped: API client not available")
            return items

        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                coro = self._async_scrape_private_channel(chat_id)
                fut = asyncio.run_coroutine_threadsafe(coro, loop)
                items = fut.result(timeout=30)
            else:
                items = loop.run_until_complete(self._async_scrape_private_channel(chat_id))
        except Exception as e:
            logger.error(f"Error scraping private Telegram chat {chat_id}: {e}")
        return items

    async def _async_scrape_private_channel(self, chat_id: str) -> List[BonusCodeItem]:
        """
        Async implementation of private channel scraping.
        """
        items: List[BonusCodeItem] = []
        chat_id_int = int(chat_id)
        meta = TELEGRAM_PRIVATE_SOURCES.get(chat_id, {})
        label = meta.get("label", chat_id)
        ref_msg_id = meta.get("reference_msg_id")
        source_url = meta.get("source_url", f"https://t.me/c/{chat_id.lstrip('-')}/{ref_msg_id or ''}").rstrip("/")

        messages = await self.telegram_api_client.fetch_messages(chat_id_int, limit=50, offset_id=ref_msg_id)
        if not messages:
            logger.debug(f"No messages fetched from private Telegram chat {chat_id}")
            return items

        for msg in messages:
            msg_text = msg.get("text", "")
            msg_id = msg.get("id", "event")
            msg_url = f"https://t.me/c/{chat_id.lstrip('-')}/{msg_id}"
            msg_date = msg.get("date")
            event_datetime = None
            if msg_date:
                try:
                    from datetime import datetime
                    event_datetime = datetime.fromisoformat(msg_date.replace("Z", "+00:00"))
                except Exception:
                    pass

            # Determine channel label for parser routing
            ch_name = label.lower()
            if "stake.com" in ch_name or "stakecom" in ch_name or "com vip" in ch_name:
                ch_name_for_parser = "highrollerscode"
            elif "stake.us" in ch_name or "stakeus" in ch_name or "us vip" in ch_name:
                ch_name_for_parser = "highrollerscodeus"
            else:
                ch_name_for_parser = label

            msg_image_url = msg.get("photo_url") if isinstance(msg, dict) else None
            item: Optional[BonusCodeItem] = None
            if "rainbet" in ch_name_for_parser.lower():
                item = self.parse_rainbet_message(msg_text, msg_url, image_url=msg_image_url, event_datetime=event_datetime)
            elif "winna" in ch_name_for_parser.lower():
                item = self.parse_winna_message(msg_text, msg_url, image_url=msg_image_url, event_datetime=event_datetime)
            elif "degen" in ch_name_for_parser.lower():
                item = self.parse_degen_message(msg_text, msg_url, image_url=msg_image_url, event_datetime=event_datetime)
            elif "qzino" in ch_name_for_parser.lower():
                item = self.parse_qzino_message(msg_text, msg_url, image_url=msg_image_url, event_datetime=event_datetime, channel_name=label)
            elif "codestats" in ch_name_for_parser.lower():
                item = self.parse_codestats_message(msg_text, msg_url, image_url=msg_image_url, event_datetime=event_datetime)
            else:
                item = self.parse_stake_message(msg_text, msg_url, ch_name_for_parser, image_url=msg_image_url, event_datetime=event_datetime)

            if item:
                is_valid, val_reason = is_valid_affiliate_code(item, max_days=MAX_EVENT_AGE_DAYS)
                if is_valid or not item.is_affiliate:
                    photo_bytes = None
                    if resolve_placeholder_code is not None and should_ocr_code and should_ocr_code(item.code):
                        photo_bytes = await self.telegram_api_client.download_message_media(
                            int(chat_id), int(msg.get("id", 0))
                        )
                    if resolve_placeholder_code is not None:
                        item = resolve_placeholder_code(item, photo_bytes=photo_bytes)
                    is_rec, rec_reason = is_event_recent(dt=item.event_datetime, max_days=MAX_EVENT_AGE_DAYS, text=item.description)
                    if is_rec:
                        items.append(item)
                    else:
                        logger.debug(f"Skipping private Telegram drop '{item.code}' due to age: {rec_reason}")
        return items
