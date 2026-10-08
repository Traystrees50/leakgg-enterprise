import logging
import datetime
from typing import List, Dict, Any, Optional, Tuple
from models import BonusCodeItem, Platform
from config import STAKESTATS_API_URL, STAKESTATS_CODE_URL, HTTP_HEADERS, REQUEST_TIMEOUT, ENABLE_JITTER, ENABLE_PROXY_ROTATION
from filters import is_event_recent, MAX_EVENT_AGE_DAYS
from network_manager import ResilientSession

logger = logging.getLogger(__name__)

class StakeStatsPoller:
    """
    Real-time poller for https://stakestats.net/stake/tools/code and its live API.
    Always refreshes live data on each invocation to ensure 100% up-to-date accuracy.
    Uses resilient networking with jitter, anti-rate-limiting backoff, and Cloudflare evasion.
    """
    def __init__(self, api_url: str = STAKESTATS_API_URL, page_url: str = STAKESTATS_CODE_URL, timeout: int = REQUEST_TIMEOUT):
        self.api_url = api_url
        self.page_url = page_url
        self.timeout = timeout
        self.session = ResilientSession(
            timeout=self.timeout,
            enable_jitter=ENABLE_JITTER,
            enable_proxy_rotation=ENABLE_PROXY_ROTATION
        )

    def fetch_live_codes(self) -> List[Dict[str, Any]]:
        """
        Polls https://stakestats.net/api/codes in real time.
        """
        try:
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://stakestats.net/stake/tools/code"
            }
            data = self.session.fetch_json(self.api_url, headers=headers)
            if data and isinstance(data, list):
                logger.info(f"Successfully polled StakeStats live API: retrieved {len(data)} total records.")
                return data
        except Exception as e:
            logger.error(f"Error fetching live codes from StakeStats API: {e}")

        return []

    def get_active_codes(self) -> Tuple[List[BonusCodeItem], List[BonusCodeItem]]:
        """
        Polls StakeStats and returns (active_stake_us_codes, active_stake_com_codes).
        """
        raw_codes = self.fetch_live_codes()
        active_us: List[BonusCodeItem] = []
        active_com: List[BonusCodeItem] = []

        for item in raw_codes:
            code = str(item.get("code") or item.get("id") or "").strip()
            if not code:
                continue

            status = item.get("status", {})
            is_us_avail = status.get("US", "").lower() == "available"
            is_com_avail = status.get("COM", "").lower() == "available"

            tag = str(item.get("tag") or "").upper()
            val_num = str(item.get("value") or "0")
            wager_num = str(item.get("wager") or "0")
            dropped_ts = item.get("droppedAt")

            # Human-formatted drop time & age check
            drop_str = "Recently"
            drop_dt = None
            if dropped_ts:
                try:
                    ts_val = float(dropped_ts)
                    if ts_val > 1e11:  # milliseconds timestamp
                        ts_val = ts_val / 1000.0
                    drop_dt = datetime.datetime.fromtimestamp(ts_val, tz=datetime.timezone.utc)
                    drop_str = drop_dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    pass

            # Strictly enforce maximum age of past 4 days (96 hours)
            if drop_dt:
                is_recent, reason = is_event_recent(dt=drop_dt, max_days=MAX_EVENT_AGE_DAYS)
                if not is_recent:
                    logger.debug(f"Skipping StakeStats drop '{code}' due to age ({drop_str}): {reason}")
                    continue

            # Format value & wager strings
            val_formatted = f"${val_num}" if not val_num.startswith("$") else val_num
            try:
                wager_val = int(wager_num.replace(",", "").replace("$", ""))
                wager_formatted = f"${wager_val:,.0f} (7-Day Wager)"
            except Exception:
                wager_formatted = f"${wager_num} (7-Day Wager)"

            is_hr = (tag == "HR") or (val_num in ["12.50", "25", "50", "100"]) or ("50000" in wager_num or "100000" in wager_num)

            # Stake.us item
            if is_us_avail:
                item_us = BonusCodeItem(
                    code=code,
                    platform=Platform.STAKE_US,
                    amount_value=f"{val_formatted} SC",
                    wager_requirement=wager_formatted,
                    source_url=self.page_url,
                    source_name="StakeStats.net (Live)",
                    is_affiliate=False,
                    is_highroller=is_hr,
                    currency="sweeps",
                    event_datetime=drop_dt,
                    description=f"Active drop on Stake.us • Dropped at {drop_str}"
                )
                active_us.append(item_us)

            # Stake.com item
            if is_com_avail:
                item_com = BonusCodeItem(
                    code=code,
                    platform=Platform.STAKE_COM,
                    amount_value=f"{val_formatted} USD",
                    wager_requirement=wager_formatted,
                    source_url=self.page_url,
                    source_name="StakeStats.net (Live)",
                    is_affiliate=False,
                    is_highroller=is_hr,
                    currency="ltc",
                    event_datetime=drop_dt,
                    description=f"Active drop on Stake.com • Dropped at {drop_str}"
                )
                active_com.append(item_com)

        return active_us, active_com

    def verify_code_active(self, code: str, platform: Platform) -> bool:
        """
        Verifies if a specific code is currently active on StakeStats for the given platform.
        Returns True if the code is found and available for the platform.
        """
        try:
            raw_codes = self.fetch_live_codes()
            if not raw_codes:
                return False

            code_upper = code.strip().upper()
            for item in raw_codes:
                item_code = str(item.get("code") or item.get("id") or "").strip().upper()
                if item_code != code_upper:
                    continue

                status = item.get("status", {})
                if platform == Platform.STAKE_US:
                    return status.get("US", "").lower() == "available"
                elif platform == Platform.STAKE_COM:
                    return status.get("COM", "").lower() == "available"
                elif platform == Platform.DUAL_STAKE:
                    us_avail = status.get("US", "").lower() == "available"
                    com_avail = status.get("COM", "").lower() == "available"
                    return us_avail or com_avail
            return False
        except Exception as e:
            logger.error(f"Error verifying code '{code}' on StakeStats: {e}")
            return False

    def format_discord_active_list(self, platform: Optional[Platform] = None) -> List[Dict[str, Any]]:
        """
        Builds a single combined Discord embed displaying all active codes
        for Stake.us and Stake.com, sorted by value from low to high,
        organized by platform within the embed.
        """
        import re as _re
        active_us, active_com = self.get_active_codes()

        if platform == Platform.STAKE_US:
            active_com = []
        elif platform == Platform.STAKE_COM:
            active_us = []

        all_items = active_us + active_com

        def _extract_numeric(val_str: str) -> float:
            m = _re.search(r"\$?([\d.]+)", val_str or "")
            return float(m.group(1)) if m else 0.0

        all_items.sort(key=lambda item: _extract_numeric(item.amount_value))

        fields = []

        def add_platform_fields(items: List[BonusCodeItem], heading: str) -> None:
            if not items:
                return
            fields.append({
                "name": heading,
                "value": "\u200b",
                "inline": False
            })
            for item in items:
                badge = "🔥 HIGHROLLER • " if item.is_highroller else "⚡ "
                value_str = (
                    f"`{item.clean_code}`\n"
                    f"**VALUE** `{item.amount_value}`  •  **WAGER** `{item.wager_requirement}`\n"
                    f"[CLAIM CODE]({item.redeem_link})  •  [SIGN UP]({item.affiliate_signup_link})  •  [DISCORD](https://discord.gg/TvJe6BV7ge)"
                )
                fields.append({
                    "name": f"{badge}{item.clean_code}",
                    "value": value_str,
                    "inline": False
                })

        add_platform_fields(
            [i for i in all_items if i.platform == Platform.STAKE_US],
            "🇺🇸 STAKE.US ACTIVE DROPS"
        )
        add_platform_fields(
            [i for i in all_items if i.platform == Platform.STAKE_COM],
            "🌍 STAKE.COM ACTIVE DROPS"
        )

        if not active_us and not active_com:
            fields.append({
                "name": "No Active Codes",
                "value": "There are currently no active drops reported for Stake.us or Stake.com. Check back soon!",
                "inline": False
            })

        total = len(active_us) + len(active_com)
        title = "🎰 ACTIVE BONUS DROPS | LIVE"
        description = (
            f"**{total} ACTIVE CODES**  •  🇺🇸 {len(active_us)} STAKE.US  •  🌍 {len(active_com)} STAKE.COM\n"
            "Verified live availability • Sorted by value, lowest first • Codes preserve exact casing"
        )
        polled_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Discord limits embeds to 25 fields and 6,000 total characters. Keep
        # headroom for formatting changes and split large live-code responses.
        def field_size(field: Dict[str, Any]) -> int:
            return len(str(field.get("name", ""))) + len(str(field.get("value", "")))

        pages: List[Dict[str, Any]] = []
        current_fields: List[Dict[str, Any]] = []
        current_size = len(title) + len(description) + len(polled_at)
        for field in fields:
            proposed_size = current_size + field_size(field)
            if current_fields and (len(current_fields) >= 24 or proposed_size > 5600):
                pages.append({"fields": current_fields, "size": current_size})
                current_fields = []
                current_size = len(title) + len(description) + len(polled_at)
            current_fields.append(field)
            current_size += field_size(field)
        if current_fields or not pages:
            pages.append({"fields": current_fields, "size": current_size})

        result: List[Dict[str, Any]] = []
        page_count = len(pages)
        for page_number, page in enumerate(pages, start=1):
            page_title = title if page_count == 1 else f"{title} - Page {page_number}/{page_count}"
            result.append({
                "title": page_title,
                "description": description,
                "color": 0x1475E1,
                "fields": page["fields"],
                "footer": {
                    "text": f"Leaked.GG Code Monitoring - Polled at {polled_at}"
                }
            })
        return result
