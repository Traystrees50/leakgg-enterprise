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

    def _get_code_key(self, code: str) -> str:
        """Code-only key, case-sensitive. Dedup is by exact code string FIRST."""
        return f"CODE:{code.strip()}"

    def is_duplicate_code(self, code: str) -> bool:
        """True if this exact code string was already seen on ANY platform.
        This is what catches VERIFICATION FAILED re-posts in #stake-codes
        (same code, same minute, re-posted as USER SUBMITTED) and Rainbet
        vs Shuffle 8-char codes posted under two platforms."""
        with self._lock:
            self._sync_from_disk()
            c = code.strip()
            if self._get_code_key(c) in self.seen_codes:
                return True
            for k in self.seen_codes:
                if k.endswith(f":{c}"):
                    return True
            return False

    def replace_code(self, old_code: str, new_code: str) -> bool:
        """Gamba correction helper: a 'OOOOPS MY BAD' correction wins over
        the earlier code. Removes all tracked keys for old_code so the
        corrected code is not blocked by the superseded one."""
        with self._lock:
            old = old_code.strip()
            removed = [k for k in self.seen_codes if k.endswith(f":{old}") or k == self._get_code_key(old)]
            for k in removed:
                del self.seen_codes[k]
            if removed:
                self.save()
            return bool(removed)

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
        Dedup order: exact code string FIRST (any platform), then platform.
        Includes intelligent cross-platform deduplication:
        - Dual Stake vs Stake.us vs Stake.com (verified dual only)
        - Shuffle.us vs Shuffle.com
        - Rainbet / Rainbet.us vs Shuffle (shared 8-char format)
        - VIP / Event prefix matching
        """
        with self._lock:
            self._sync_from_disk()
            c = code.strip()
            p = platform.strip()
            c_upper = c.upper()

            # 0. Exact code string, ANY platform, first. A code seen as
            # Rainbet must not re-post as Shuffle, a Stake code must not
            # re-post as a VERIFICATION FAILED USER SUBMITTED copy, etc.
            # Event codes (CHECK_IMAGE / WEEKLY_BOOST / etc.) are exempt:
            # they use source_url as a discriminator and are checked below.
            _is_event = (
                "CHECK_IMAGE" in c_upper
                or c_upper.startswith("WEEKLY_BOOST")
                or c_upper.startswith("MONTHLY_BONUS")
                or c_upper.startswith("VIP_")
                or c_upper.startswith("DEGEN_DROP")
                or c_upper.startswith("QZINO_EVENT")
            )
            if not _is_event and self.is_duplicate_code(c):
                return True

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

            # 6. Cross-Platform Rainbet vs Shuffle Deduplication
            # Both use the shared 8-char uppercase format. A code seen as
            # Rainbet.us / Rainbet must not re-post as Shuffle, and vice versa.
            if p in ["Rainbet.us", "Rainbet", "Shuffle.us", "Shuffle.com"]:
                if (
                    f"Rainbet.us:{c}" in self.seen_codes
                    or f"Rainbet:{c}" in self.seen_codes
                    or f"Shuffle.us:{c}" in self.seen_codes
                    or f"Shuffle.com:{c}" in self.seen_codes
                ):
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
            # Code-only alias: the primary dedup key for is_duplicate_code.
            self.seen_codes[self._get_code_key(item.code)] = item_dict

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
            elif item.platform in (Platform.RAINBET, Platform.RAINBET_US):
                # Rainbet aliases also cover Shuffle: shared 8-char format.
                self.seen_codes[f"Rainbet:{c}"] = item_dict
                self.seen_codes[f"Rainbet.us:{c}"] = item_dict
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
