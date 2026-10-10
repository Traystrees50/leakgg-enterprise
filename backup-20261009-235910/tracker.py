import os
import json
import logging
import threading
from typing import Dict, Any, List, Optional
from models import BonusCodeItem, Platform

logger = logging.getLogger(__name__)

class CodeTracker:
    def __init__(self, filepath: str = "seen_codes.json"):
        self.filepath = filepath
        self.seen_codes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._last_mtime: float = 0.0
        self.load()

    def _sync_from_disk(self) -> None:
        """
        Dynamically synchronizes in-memory seen_codes with disk if the state file was updated
        by another process or worker thread.
        """
        try:
            if os.path.exists(self.filepath):
                mtime = os.path.getmtime(self.filepath)
                if mtime > self._last_mtime:
                    with open(self.filepath, "r", encoding="utf-8") as f:
                        disk_data = json.load(f)
                        if isinstance(disk_data, dict):
                            self.seen_codes.update(disk_data)
                    self._last_mtime = mtime
        except Exception:
            pass

    def _get_key(self, platform: str, code: str, source_url: str = "") -> str:
        """
        Creates a case-sensitive tracking key preserving exact code casing.
        """
        c = code.strip()
        c_upper = c.upper()
        p = platform.strip()
        # Events without unique code token use source_url as discriminator
        if ("CHECK_IMAGE" in c_upper or c_upper.startswith("WEEKLY_BOOST") or c_upper.startswith("MONTHLY_BONUS") or c_upper.startswith("VIP_") or c_upper.startswith("DEGEN_DROP") or c_upper.startswith("QZINO_EVENT")) and source_url:
            return f"{p}:{c}:{source_url.strip()}"
        return f"{p}:{c}"

    def load(self) -> None:
        with self._lock:
            if os.path.exists(self.filepath):
                try:
                    with open(self.filepath, "r", encoding="utf-8") as f:
                        self.seen_codes = json.load(f)
                    logger.info(f"Loaded {len(self.seen_codes)} previously seen codes from {self.filepath}")
                except Exception as e:
                    logger.error(f"Error loading state from {self.filepath}: {e}. Initializing empty tracker.")
                    self.seen_codes = {}
            else:
                self.seen_codes = {}

    def save(self) -> None:
        with self._lock:
            try:
                # Write directly to file with UTF-8 encoding
                with open(self.filepath, "w", encoding="utf-8") as f:
                    json.dump(self.seen_codes, f, indent=2, ensure_ascii=False)
                logger.debug(f"Saved {len(self.seen_codes)} seen codes to {self.filepath}")
            except Exception as e:
                logger.error(f"Failed to save state to {self.filepath}: {e}")

    def is_seen(self, platform: str, code: str, source_url: str = "") -> bool:
        """
        Checks if a code has already been seen for a given platform (case-sensitive and thread-safe).
        Includes intelligent cross-platform deduplication:
        - Dual Stake vs Stake.us vs Stake.com
        - Shuffle.us vs Shuffle.com
        - VIP / Event prefix matching
        """
        with self._lock:
            self._sync_from_disk()
            c = code.strip()
            p = platform.strip()
            c_upper = c.upper()

            # 1. Exact key match
            exact_key = self._get_key(p, c, source_url)
            if exact_key in self.seen_codes:
                return True

            # 2. Base key match (if exact_key included source_url or vice versa)
            base_key = f"{p}:{c}"
            if base_key in self.seen_codes:
                return True

            # 3. For event codes, check if any key starts with base_key or matches source_url
            if "CHECK_IMAGE" in c_upper or c_upper.startswith("WEEKLY_BOOST") or c_upper.startswith("MONTHLY_BONUS") or c_upper.startswith("VIP_") or c_upper.startswith("DEGEN_DROP") or c_upper.startswith("QZINO_EVENT"):
                for k in self.seen_codes:
                    if k.startswith(f"{p}:{c}"):
                        return True
                    if source_url and source_url.strip() in k:
                        return True

            # 4. Cross-Platform Stake Deduplication
            # If code is already tracked for Dual Stake or single Stake platforms
            if p in ["Stake.us", "Stake.com", "Dual Stake", "Stake.us - VIP Notices", "Stake.com - VIP Notices"]:
                if f"Dual Stake:{c}" in self.seen_codes:
                    return True
                if p == "Stake.us" and f"Stake.us:{c}" in self.seen_codes:
                    return True
                if p == "Stake.com" and f"Stake.com:{c}" in self.seen_codes:
                    return True
                if p == "Dual Stake":
                    if f"Stake.us:{c}" in self.seen_codes or f"Stake.com:{c}" in self.seen_codes:
                        return True
                if p == "Stake.us - VIP Notices":
                    if f"Stake.us:{c}" in self.seen_codes:
                        return True
                if p == "Stake.com - VIP Notices":
                    if f"Stake.com:{c}" in self.seen_codes:
                        return True

            # 5. Cross-Platform Shuffle Deduplication
            # Prevents duplicate Shuffle drops across @anyclaimershuffle, @codestats2, codestats.gg
            if p in ["Shuffle.us", "Shuffle.com"]:
                if f"Shuffle.us:{c}" in self.seen_codes or f"Shuffle.com:{c}" in self.seen_codes:
                    return True

            return False

    def is_item_seen(self, item: BonusCodeItem) -> bool:
        """
        Helper to check if a BonusCodeItem is already tracked.
        """
        return self.is_seen(item.platform.value, item.code, item.source_url)

    def mark_seen_if_new(self, item: BonusCodeItem) -> bool:
        """
        Atomically checks if the item is already seen and marks it as seen if not.
        Returns True if newly marked (item was not previously seen), False if already seen.
        This prevents race conditions where two threads both see is_item_seen=False
        before either calls mark_seen.
        """
        with self._lock:
            if self.is_item_seen(item):
                return False
            self.mark_seen(item)
            return True

    def mark_seen(self, item: BonusCodeItem) -> bool:
        """
        Marks a bonus code as seen (preserving exact case and thread-safe).
        Also stores cross-platform aliases to prevent duplicate broadcasts.
        Returns True if newly added, False if already present.
        """
        with self._lock:
            if self.is_item_seen(item):
                return False

            key = self._get_key(item.platform.value, item.code, item.source_url)
            item_dict = item.to_dict()
            self.seen_codes[key] = item_dict

            # Store cross-platform keys to prevent duplicate detection across different source feeds
            c = item.code.strip()
            if item.platform == Platform.DUAL_STAKE or item.is_dual_stake:
                self.seen_codes[f"Dual Stake:{c}"] = item_dict
                self.seen_codes[f"Stake.us:{c}"] = item_dict
                self.seen_codes[f"Stake.com:{c}"] = item_dict
            elif item.platform == Platform.STAKE_US:
                self.seen_codes[f"Stake.us:{c}"] = item_dict
            elif item.platform == Platform.STAKE_COM:
                self.seen_codes[f"Stake.com:{c}"] = item_dict
            elif item.platform == Platform.STAKE_US_VIP_NOTICES:
                self.seen_codes[f"Stake.us - VIP Notices:{c}"] = item_dict
            elif item.platform == Platform.STAKE_COM_VIP_NOTICES:
                self.seen_codes[f"Stake.com - VIP Notices:{c}"] = item_dict
            elif item.platform in (Platform.SHUFFLE_US, Platform.SHUFFLE_COM):
                self.seen_codes[f"Shuffle.us:{c}"] = item_dict
                self.seen_codes[f"Shuffle.com:{c}"] = item_dict

            self.save()
            return True

    def get_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.seen_codes.values())

    def clear(self) -> None:
        with self._lock:
            self.seen_codes = {}
            self.save()
            logger.info("Cleared all seen codes.")
