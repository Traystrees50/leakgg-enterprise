import logging
import re
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
from models import BonusCodeItem, Platform
from config import HTTP_HEADERS, REQUEST_TIMEOUT, ENABLE_JITTER, ENABLE_PROXY_ROTATION
from filters import is_telegram_or_low_value_drop
from network_manager import ResilientSession, get_resilient_session

logger = logging.getLogger(__name__)

class BaseScraper:
    def __init__(self, headers: Optional[dict] = None, timeout: int = REQUEST_TIMEOUT):
        self.headers = headers or HTTP_HEADERS
        self.timeout = timeout
        self.session = ResilientSession(
            timeout=self.timeout,
            enable_jitter=ENABLE_JITTER,
            enable_proxy_rotation=ENABLE_PROXY_ROTATION
        )

    def fetch_html(self, url: str) -> Optional[str]:
        try:
            return self.session.fetch_text(url, headers=self.headers)
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {e}")
            return None

    def detect_platform_from_url_or_text(self, url: str, text: str = "") -> Platform:
        u = url.lower()
        t = text.lower()
        if "stake-us" in u or "stake.us" in u or "stakeus" in u or "stake-us" in t or "stake.us" in t:
            return Platform.STAKE_US
        elif "stake-com" in u or "stake.com" in u or "stakecom" in u or "stake-com" in t or "stake.com" in t:
            return Platform.STAKE_COM
        return Platform.from_str(u + " " + t)

    def extract_value_and_wager_from_text(self, text: str) -> Tuple[str, str]:
        """
        Extracts human-readable bonus value/amount and wagering requirement from surrounding text context.
        """
        # Value patterns
        val_patterns = [
            r"(\$?\d+(?:\.\d+)?\s*(?:SC|Free SC|Stake Cash)\s*\+\s*\d+(?:,\d+)?k?\s*(?:GC|Gold Coins)(?:\s*\+\s*\d+%\s*Rakeback)?)",
            r"(\d+(?:,\d+)?k?\s*GC\s*\+\s*\$?\d+(?:\.\d+)?\s*(?:FREE\s+SC|SC)(?:\s*\+\s*\d+\s*SC\s*daily)?)",
            r"(200%\s*(?:Deposit\s+Match|Bonus)?\s*(?:up\s+to\s+\$?\d+(?:,\d+)?)?)",
            r"(\$?\d+(?:,\d+)?\s*(?:Bonus|No Deposit Bonus|Free Coins))",
            r"(\d+%\s*Rakeback(?:\s*\+\s*\$?\d+\s*SC)?)",
            r"(up\s+to\s+\$?\d+(?:,\d+)?(?:\s*SC|\s*GC)?)"
        ]
        
        extracted_value = ""
        for p in val_patterns:
            m = re.search(p, text, re.I)
            if m:
                extracted_value = m.group(1).strip()
                break

        if not extracted_value:
            # Fallback check for SC / GC mentions
            m_simple = re.search(r"(\d+\s*SC|\d+k\s*GC|\$\d+|\d+%\s*Rakeback)", text, re.I)
            if m_simple:
                extracted_value = m_simple.group(1).strip()
            else:
                extracted_value = "Exclusive Affiliate Bonus & Rakeback"

        # Wager patterns
        wager_patterns = [
            r"(\d+x\s*(?:wager|wagering|rollover|playthrough))",
            r"(no\s+wager(?:ing)?|0x\s*rollover|zero\s+wager)",
            r"(\d+x\s*on\s*deposit)",
            r"(3x\s*playthrough)"
        ]
        
        extracted_wager = ""
        for wp in wager_patterns:
            wm = re.search(wp, text, re.I)
            if wm:
                extracted_wager = wm.group(1).strip()
                break

        if not extracted_wager:
            if "3x" in text.lower():
                extracted_wager = "3x Rollover (Standard)"
            elif "no wager" in text.lower() or "0x" in text.lower():
                extracted_wager = "0x (No Wagering)"
            else:
                extracted_wager = "Standard Playthrough (3x SC)"

        return extracted_value, extracted_wager

    def parse(self, url: str, html: str) -> List[BonusCodeItem]:
        """
        Should be implemented by subclasses or generic parser.
        """
        raise NotImplementedError
