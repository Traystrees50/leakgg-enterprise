import re
import logging
import datetime
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from models import BonusCodeItem, Platform
from config import CODESTATS_URL, HTTP_HEADERS, REQUEST_TIMEOUT, ENABLE_JITTER, ENABLE_PROXY_ROTATION
from filters import extract_event_datetime, is_event_recent, MAX_EVENT_AGE_DAYS, STOP_WORDS
from network_manager import ResilientSession

logger = logging.getLogger(__name__)

class CodeStatsScraper:
    """
    Scraper for CodeStats.gg covering Shuffle.com, Shuffle.us, and Stake drop feeds.
    Uses resilient networking with jitter, anti-rate-limiting backoff, and Cloudflare evasion.
    """
    def __init__(self, base_url: str = CODESTATS_URL, timeout: int = REQUEST_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
        self.session = ResilientSession(
            timeout=self.timeout,
            enable_jitter=ENABLE_JITTER,
            enable_proxy_rotation=ENABLE_PROXY_ROTATION
        )

    def scrape_codes(self) -> List[BonusCodeItem]:
        """
        Fetches codestats.gg and parses active bonus codes for Shuffle and Stake platforms.
        Enforces maximum age of 4 days.
        """
        items: List[BonusCodeItem] = []
        try:
            feed_items = self._scrape_live_feed()
            if feed_items:
                return feed_items

            html = self.session.fetch_text(self.base_url, headers=HTTP_HEADERS)
            if not html:
                logger.warning(f"Failed to fetch CodeStats.gg content")
                return items

            soup = BeautifulSoup(html, "html.parser")
            
            # Find code cards or table rows on CodeStats
            for row in soup.find_all(lambda tag: tag.name in ["div", "tr", "article"] and tag.has_attr("class") and any("code" in c.lower() or "drop" in c.lower() for c in tag.get("class", []))):
                text = " ".join(row.get_text().split())
                if not text:
                    continue

                # Check age / timestamp from row
                event_dt = extract_event_datetime(text)
                is_recent, reason = is_event_recent(dt=event_dt, max_days=MAX_EVENT_AGE_DAYS, text=text)
                if not is_recent:
                    logger.debug(f"Skipping outdated CodeStats card: {reason}")
                    continue

                # Determine platform
                if "shuffle.us" in text.lower():
                    platform = Platform.SHUFFLE_US
                elif "shuffle" in text.lower():
                    platform = Platform.SHUFFLE_COM
                elif "stake.us" in text.lower():
                    platform = Platform.STAKE_US
                elif "stake" in text.lower():
                    platform = Platform.STAKE_COM
                else:
                    continue

                # Extract code candidate
                code_m = re.search(r"(?:code|drop)[:\s]+([A-Za-z0-9_\-]+)", text, re.I)
                if not code_m:
                    code_m = re.search(r"\b([A-Z0-9]{6,20})\b", text)

                if not code_m:
                    continue

                code = code_m.group(1).strip()
                if code.upper() in STOP_WORDS or code.upper() in ["CODESTATS", "SHUFFLE", "STAKE", "DROP"]:
                    continue

                # Extract value & wager
                val_m = re.search(r"(\$?\d+(?:\.\d+)?\s*(?:SC|GC|USD|\$)?)", text, re.I)
                val = val_m.group(1).strip() if val_m else "Bonus Drop"

                wager_m = re.search(r"(\$?[0-9,]+\s*(?:wager|requirement|playthrough)[^\.]*)", text, re.I)
                wager = wager_m.group(1).strip() if wager_m else "Low Wager Requirement"

                item = BonusCodeItem(
                    code=code,
                    platform=platform,
                    amount_value=val,
                    wager_requirement=wager,
                    source_url=self.base_url,
                    source_name="CodeStats.gg",
                    is_affiliate=False,
                    event_datetime=event_dt,
                    description=text[:300]
                )
                items.append(item)

        except Exception as e:
            logger.error(f"Error scraping CodeStats.gg: {e}")

        return items

    def _scrape_live_feed(self) -> List[BonusCodeItem]:
        """Read CodeStats' public recent-feed API before falling back to HTML."""
        session_data = self.session.fetch_json(
            f"{self.base_url.rstrip('/')}/api/session",
            headers=HTTP_HEADERS
        )
        if not isinstance(session_data, dict) or not session_data.get("sessionId"):
            return []

        headers = dict(HTTP_HEADERS)
        headers["X-Session-Id"] = str(session_data["sessionId"])
        payload = self.session.fetch_json(
            f"{self.base_url.rstrip('/')}/api/discord-feed?limit=50",
            headers=headers
        )
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        if not isinstance(messages, list):
            return []

        items: List[BonusCodeItem] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            code = str(message.get("code") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{4,35}", code) or code.upper() in STOP_WORDS:
                continue

            platforms: List[Platform] = []
            if message.get("isShuffleUS"):
                platforms.append(Platform.SHUFFLE_US)
            elif message.get("isShuffleCom") or message.get("isShuffle"):
                platforms.append(Platform.SHUFFLE_COM)
            if message.get("isStakeUS"):
                platforms.append(Platform.STAKE_US)
            if message.get("isStakeCom"):
                platforms.append(Platform.STAKE_COM)
            if not platforms:
                continue

            event_dt = None
            timestamp = message.get("timestamp")
            if timestamp:
                try:
                    timestamp_value = float(timestamp)
                    if timestamp_value > 1e11:
                        timestamp_value /= 1000
                    event_dt = datetime.datetime.fromtimestamp(timestamp_value, tz=datetime.timezone.utc)
                except (TypeError, ValueError, OSError):
                    pass

            for platform in platforms:
                custom_link = None
                if platform == Platform.SHUFFLE_US:
                    custom_link = f"https://shuffle.us/?modal=c&md-code={code}"
                elif platform == Platform.SHUFFLE_COM:
                    custom_link = f"https://shuffle.com/?modal=c&md-code={code}"

                items.append(BonusCodeItem(
                    code=code,
                    platform=platform,
                    amount_value=str(message.get("amount") or "Bonus Drop"),
                    wager_requirement=str(message.get("wagerRequirement") or "Low Wager Requirement"),
                    claims_count=str(message.get("dropLimit") or "Unlimited / Open"),
                    source_url=self.base_url,
                    source_name="CodeStats.gg Live Feed",
                    is_affiliate=False,
                    custom_redeem_link=custom_link,
                    event_datetime=event_dt,
                    description=f"CodeStats live feed: {message.get('channelName') or 'community feed'}"
                ))
        return items
