import logging
import re
import threading
import concurrent.futures
from typing import List, Dict, Any, Optional, Callable
from config import TARGET_SOURCES, TELEGRAM_CHANNELS, TELEGRAM_PRIVATE_SOURCES
from models import BonusCodeItem, Platform
from scrapers.sources import SiteScraper
from scrapers.telegram import TelegramScraper
from scrapers.stakestats import StakeStatsPoller
from scrapers.codestats import CodeStatsScraper
from tracker import CodeTracker
from discord_notifier import DiscordNotifier
from dashboard_manager import DashboardManager
from filters import is_valid_affiliate_code, is_event_recent, MAX_EVENT_AGE_DAYS
from scrapers.validator import StakeCodeValidator

logger = logging.getLogger(__name__)

class ScraperEngine:
    def __init__(
        self,
        sources: Optional[List[str]] = None,
        tracker: Optional[CodeTracker] = None,
        notifier: Optional[DiscordNotifier] = None,
        dashboard_manager: Optional[DashboardManager] = None,
        code_validator: Optional[StakeCodeValidator] = None
    ):
        self.dashboard_manager = dashboard_manager or (notifier.dashboard_manager if notifier and hasattr(notifier, "dashboard_manager") else DashboardManager())
        self.sources = sources or (self.dashboard_manager.get_web_sources() if self.dashboard_manager else TARGET_SOURCES)
        self.site_scraper = SiteScraper()
        telegram_api_client = None
        try:
            from scrapers.telegram_api import TelegramAPIClient
            telegram_api_client = TelegramAPIClient()
        except Exception as e:
            logger.debug(f"Telegram API client not initialized: {e}")
        self.telegram_scraper = TelegramScraper(
            channels=self.dashboard_manager.get_telegram_sources() if self.dashboard_manager else TELEGRAM_CHANNELS,
            telegram_api_client=telegram_api_client
        )
        self.stakestats_poller = StakeStatsPoller()
        self.codestats_scraper = CodeStatsScraper()
        self.tracker = tracker or CodeTracker()
        self.notifier = notifier or DiscordNotifier(dashboard_manager=self.dashboard_manager)
        self.code_validator = code_validator or StakeCodeValidator()
        self._process_lock = threading.RLock()

    def process_items(self, items: List[BonusCodeItem], notify: bool = True) -> List[BonusCodeItem]:
        """
        Validates event recency (<= 4 days), deduplicates candidate bonus codes against
        CodeTracker in a synchronized pass, persists unseen items, and dispatches Discord notifications
        with exact casing preserved without duplicates.
        """
        with self._process_lock:
            new_items: List[BonusCodeItem] = []
            batch_seen = set()

            for item in items:
                # 1. Enforce strict 4-day age limit across all pipeline items
                is_recent, age_reason = is_event_recent(
                    dt=item.event_datetime,
                    max_days=MAX_EVENT_AGE_DAYS,
                    text=item.description or ""
                )
                if not is_recent:
                    logger.debug(f"Skipping drop '{item.code}' in process_items: {age_reason}")
                    continue

                # 2. Basic validation for ALL items (not just affiliates): reject numeric-only codes, stop words, etc.
                _code_upper = item.code.strip().upper()
                if not re.search(r"[A-Z]", _code_upper):
                    logger.debug(f"Skipping code '{item.code}' for {item.platform.value}: no alphabetic characters")
                    continue
                if re.search(r"^[0-9]+$", _code_upper):
                    logger.debug(f"Skipping numeric-only code '{item.code}' for {item.platform.value}")
                    continue

                # 3. Affiliate validation
                if item.is_affiliate:
                    is_valid, val_reason = is_valid_affiliate_code(item, max_days=MAX_EVENT_AGE_DAYS)
                    if not is_valid:
                        logger.debug(f"Skipping invalid affiliate drop '{item.code}': {val_reason}")
                        continue

                # 3. In-batch cross-platform deduplication
                c_clean = item.code.strip()
                batch_key = self.tracker._get_key(item.platform.value, item.code, item.source_url)
                if batch_key in batch_seen:
                    continue

                # Cross-platform in-batch guards
                if item.platform in [Platform.STAKE_US, Platform.STAKE_COM, Platform.DUAL_STAKE, Platform.STAKE_US_VIP_NOTICES, Platform.STAKE_COM_VIP_NOTICES]:
                    if (f"Dual Stake:{c_clean}" in batch_seen or 
                        (item.platform == Platform.STAKE_US and f"Stake.us:{c_clean}" in batch_seen) or
                        (item.platform == Platform.STAKE_COM and f"Stake.com:{c_clean}" in batch_seen) or
                        (item.platform == Platform.DUAL_STAKE and (f"Stake.us:{c_clean}" in batch_seen or f"Stake.com:{c_clean}" in batch_seen)) or
                        (item.platform == Platform.STAKE_US_VIP_NOTICES and f"Stake.us:{c_clean}" in batch_seen) or
                        (item.platform == Platform.STAKE_COM_VIP_NOTICES and f"Stake.com:{c_clean}" in batch_seen)):
                        continue

                if item.platform in [Platform.SHUFFLE_US, Platform.SHUFFLE_COM]:
                    if f"Shuffle.us:{c_clean}" in batch_seen or f"Shuffle.com:{c_clean}" in batch_seen:
                        continue

                # 4. Atomically check if already seen and mark as seen (prevents race conditions)
                if self.tracker.mark_seen_if_new(item):
                    logger.info(f"🔥 NEW CODE FOUND! [{item.platform.value}] Code: {item.code} | Value: {item.amount_value} | Source: {item.source_name}")
                    
                    batch_key = self.tracker._get_key(item.platform.value, item.code, item.source_url)
                    batch_seen.add(batch_key)
                    if item.platform in [Platform.STAKE_US, Platform.STAKE_COM, Platform.DUAL_STAKE, Platform.STAKE_US_VIP_NOTICES, Platform.STAKE_COM_VIP_NOTICES]:
                        batch_seen.add(f"Dual Stake:{c_clean}")
                        batch_seen.add(f"Stake.us:{c_clean}")
                        batch_seen.add(f"Stake.com:{c_clean}")
                    if item.platform in [Platform.SHUFFLE_US, Platform.SHUFFLE_COM]:
                        batch_seen.add(f"Shuffle.us:{c_clean}")
                        batch_seen.add(f"Shuffle.com:{c_clean}")

                    # Validate Stake.us/Stake.com/Dual Stake codes via live GraphQL before broadcasting
                    if self.code_validator and item.platform in (
                        Platform.STAKE_US,
                        Platform.STAKE_COM,
                        Platform.DUAL_STAKE,
                        Platform.STAKE_US_VIP_NOTICES,
                        Platform.STAKE_COM_VIP_NOTICES,
                    ):
                        try:
                            vresult = self.code_validator.validate(c_clean, item.platform)
                            vstatus = vresult.get("status", "UNKNOWN")
                            if vstatus in ("FULLY_CLAIMED", "EXPIRED"):
                                logger.info(f"Skipping {vstatus} code '{c_clean}' for {item.platform.value} (validator)")
                                continue
                        except Exception as ve:
                            logger.debug(f"Validator check failed for {c_clean} on {item.platform.value}: {ve}")

                    new_items.append(item)

                    # Dispatch Discord notification in real-time
                    if notify:
                        self.notifier.send_notification(item)
                else:
                    batch_seen.add(batch_key)
                    logger.debug(f"Code already tracked: [{item.platform.value}] {item.code}")

            return new_items

    def _scrape_single_web_source(self, url: str) -> List[BonusCodeItem]:
        try:
            html = self.site_scraper.fetch_html(url)
            if not html:
                return []

            items = self.site_scraper.parse(url, html)
            valid_items = []
            for it in items:
                is_valid, reason = is_valid_affiliate_code(it)
                if is_valid:
                    valid_items.append(it)
                else:
                    logger.debug(f"Filtered candidate '{it.code}': {reason}")
            return valid_items
        except Exception as e:
            logger.error(f"Error scraping web source {url}: {e}")
            return []

    def fetch_web_candidates(self, max_workers: int = 8, on_site_items: Optional[Callable[[List[BonusCodeItem]], None]] = None) -> List[BonusCodeItem]:
        all_valid: List[BonusCodeItem] = []
        web_sources = self.dashboard_manager.get_web_sources() if self.dashboard_manager else self.sources
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(web_sources) or 1)) as executor:
            future_to_url = {executor.submit(self._scrape_single_web_source, url): url for url in web_sources}
            for future in concurrent.futures.as_completed(future_to_url):
                try:
                    site_items = future.result()
                    if site_items:
                        all_valid.extend(site_items)
                        if on_site_items:
                            try:
                                on_site_items(site_items)
                            except Exception as cb_err:
                                logger.error(f"Error in on_site_items callback: {cb_err}")
                except Exception as e:
                    logger.error(f"Error in web worker: {e}")
        return all_valid

    def fetch_telegram_candidates(self, on_channel_items: Optional[Callable[[List[BonusCodeItem]], None]] = None) -> List[BonusCodeItem]:
        try:
            if self.dashboard_manager:
                self.telegram_scraper.channels = self.dashboard_manager.get_telegram_sources()
            return self.telegram_scraper.scrape_all_channels(on_channel_items=on_channel_items, dashboard_manager=self.dashboard_manager)
        except Exception as e:
            logger.error(f"Error during Telegram channel sweep: {e}")
            return []

    def fetch_stakestats_candidates(self) -> List[BonusCodeItem]:
        try:
            active_us, active_com = self.stakestats_poller.get_active_codes()
            return active_us + active_com
        except Exception as e:
            logger.error(f"Error during StakeStats check: {e}")
            return []

    def fetch_codestats_candidates(self) -> List[BonusCodeItem]:
        try:
            return self.codestats_scraper.scrape_codes()
        except Exception as e:
            logger.error(f"Error during CodeStats check: {e}")
            return []

    def run_web_check(self, notify: bool = True, max_workers: int = 6) -> List[BonusCodeItem]:
        """
        Scrapes configured web review sources concurrently for affiliate promotional codes.
        """
        logger.info(f"Scanning {len(self.sources)} web affiliate sources concurrently...")
        all_new: List[BonusCodeItem] = []
        def on_items(items):
            new_it = self.process_items(items, notify=notify)
            all_new.extend(new_it)

        self.fetch_web_candidates(max_workers=max_workers, on_site_items=on_items)
        return all_new

    def run_telegram_check(self, notify: bool = True) -> List[BonusCodeItem]:
        """
        Scrapes Telegram channels for drop codes, low-wager drops, VIP boosts, and Rainbet/Degen drops.
        """
        logger.info("Scanning Telegram channels for bonus drop events...")
        all_new: List[BonusCodeItem] = []
        def on_items(items):
            new_it = self.process_items(items, notify=notify)
            all_new.extend(new_it)

        self.fetch_telegram_candidates(on_channel_items=on_items)
        return all_new

    def run_stakestats_check(self, notify: bool = True) -> List[BonusCodeItem]:
        """
        Polls StakeStats live API for active drops on Stake.us and Stake.com.
        """
        logger.info("Polling StakeStats.net live drop database...")
        candidates = self.fetch_stakestats_candidates()
        return self.process_items(candidates, notify=notify)

    def run_codestats_check(self, notify: bool = True) -> List[BonusCodeItem]:
        """
        Scrapes CodeStats.gg for Shuffle.us, Shuffle.com, and Stake drops.
        """
        logger.info("Scanning CodeStats.gg for Shuffle and Stake codes...")
        candidates = self.fetch_codestats_candidates()
        return self.process_items(candidates, notify=notify)

    def run_check(self, notify: bool = True) -> List[BonusCodeItem]:
        """
        Orchestrates an ultra-fast concurrent candidate gathering and real-time streaming phase across:
        1. StakeStats Live API
        2. Telegram Drop Channels
        3. CodeStats.gg Feeds
        4. Target Web Affiliate Review Pages
        Newly detected bonus drops are posted immediately to Discord in real-time as each source returns.
        """
        logger.info("Starting real-time multi-source bonus code monitoring sweep...")
        all_new: List[BonusCodeItem] = []
        res_lock = threading.Lock()

        def stream_items(candidates: List[BonusCodeItem]):
            if not candidates:
                return
            new_items = self.process_items(candidates, notify=notify)
            if new_items:
                with res_lock:
                    all_new.extend(new_items)

        def run_stakestats():
            items = self.fetch_stakestats_candidates()
            stream_items(items)
            return items

        def run_telegram():
            return self.fetch_telegram_candidates(on_channel_items=stream_items)

        def run_codestats():
            items = self.fetch_codestats_candidates()
            stream_items(items)
            return items

        def run_web():
            return self.fetch_web_candidates(on_site_items=stream_items)

        tasks = [
            ("StakeStats", run_stakestats),
            ("Telegram", run_telegram),
            ("CodeStats", run_codestats),
            ("WebReviews", run_web),
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_name = {executor.submit(func): name for name, func in tasks}
            for future in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error during {name} real-time check: {e}")

        logger.info(f"Sweep completed. Dispatched {len(all_new)} total new bonus codes across all sources in real-time.")
        return all_new
