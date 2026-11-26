import re
import logging
import time
import urllib.parse
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from models import BonusCodeItem, Platform
from scrapers.base import BaseScraper
from filters import extract_event_datetime, is_event_recent, is_valid_affiliate_code, MAX_EVENT_AGE_DAYS, STOP_WORDS
from config import HTTP_HEADERS, REQUEST_TIMEOUT, ENABLE_JITTER, ENABLE_PROXY_ROTATION
from network_manager import ResilientSession

logger = logging.getLogger(__name__)

class CodezGGScraper(BaseScraper):
    """Scraper for codez.gg - covers Stake.US, Stake, Winna, Rainbet, Shuffle.us, Shuffle, Thrill"""
    
    BASE_URL = "https://codez.gg"
    
    def __init__(self, timeout=15):
        super().__init__(headers=HTTP_HEADERS, timeout=timeout)
        self.session = ResilientSession(
            timeout=timeout,
            enable_jitter=ENABLE_JITTER,
            enable_proxy_rotation=ENABLE_PROXY_ROTATION
        )
    
    def scrape_all(self) -> List[BonusCodeItem]:
        items = []
        try:
            html = self.session.fetch_text(self.BASE_URL, headers=self.headers)
            if not html:
                return items
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all code cards
            code_cards = soup.find_all(['div', 'article', 'tr'], 
                class_=re.compile(r'code|drop|promo|bonus|offer', re.I))
            
            for card in code_cards:
                text = " ".join(card.get_text().split())
                if not text or len(text) < 10:
                    continue
                
                # Determine platform from text
                platform = self._detect_platform(text)
                if not platform:
                    continue
                
                # Extract code
                code_match = re.search(r'(?:code|promo|drop|use)[:\s]+([A-Za-z0-9_\-]{4,30})', text, re.I)
                if not code_match:
                    code_match = re.search(r'\b([A-Z0-9]{6,20})\b', text)
                
                if not code_match:
                    continue
                
                code = code_match.group(1).strip()
                if code.upper() in STOP_WORDS:
                    continue
                
                # Extract value
                val_match = re.search(r'(?:value|reward|amount|bonus)[:\s]+(\$?\d+(?:\.\d+)?\s*(?:SC|GC|USD|\$)?)', text, re.I)
                val = val_match.group(1).strip() if val_match else "Bonus Drop"
                
                # Extract wager
                wager_match = re.search(r'(?:wager|requirement|playthrough)[:\s]+([\d,]+\s*(?:x|SC|GC|USD)?)', text, re.I)
                wager = wager_match.group(1).strip() if wager_match else "Not specified"
                
                # Extract image
                img_tag = card.find('img')
                image_url = img_tag.get('src') if img_tag and img_tag.get('src', '').startswith('http') else None
                
                item = BonusCodeItem(
                    code=code,
                    platform=platform,
                    amount_value=val,
                    wager_requirement=wager,
                    source_url=self.BASE_URL,
                    source_name="Codez.gg",
                    is_affiliate=True,
                    image_url=image_url,
                    description=text[:300]
                )
                
                is_valid, _ = is_valid_affiliate_code(item)
                if is_valid:
                    items.append(item)
                    
        except Exception as e:
            logger.error(f"Error scraping Codez.gg: {e}")
        
        return items
    
    def _detect_platform(self, text: str) -> Optional[Platform]:
        text_lower = text.lower()
        if 'stake.us' in text_lower:
            return Platform.STAKE_US
        elif 'stake.com' in text_lower or ('stake' in text_lower and 'us' not in text_lower):
            return Platform.STAKE_COM
        elif 'winna' in text_lower:
            return Platform.WINNA
        elif 'rainbet' in text_lower:
            return Platform.RAINBET
        elif 'shuffle.us' in text_lower:
            return Platform.SHUFFLE_US
        elif 'shuffle' in text_lower:
            return Platform.SHUFFLE_COM
        elif 'thrill' in text_lower:
            return Platform.THRILL
        return None


class StakeCodeClaimerScraper(BaseScraper):
    """Scraper for stakecodeclaimer.com - Stake code resources"""
    
    BASE_URL = "https://stakecodeclaimer.com"
    
    def __init__(self, timeout=15):
        super().__init__(headers=HTTP_HEADERS, timeout=timeout)
        self.session = ResilientSession(
            timeout=timeout,
            enable_jitter=ENABLE_JITTER,
            enable_proxy_rotation=ENABLE_PROXY_ROTATION
        )
    
    def scrape_all(self) -> List[BonusCodeItem]:
        items = []
        try:
            html = self.session.fetch_text(self.BASE_URL, headers=self.headers)
            if not html:
                return items
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find code elements
            code_elements = soup.find_all(['div', 'tr', 'li', 'article'], 
                class_=re.compile(r'code|drop|promo|bonus|offer|claim', re.I))
            
            for elem in code_elements:
                text = " ".join(elem.get_text().split())
                if not text or len(text) < 10:
                    continue
                
                # Extract code
                code_match = re.search(r'(?:code|promo|drop|use|claim)[:\s]+([A-Za-z0-9_\-]{4,30})', text, re.I)
                if not code_match:
                    code_match = re.search(r'\b([A-Z0-9]{6,20})\b', text)
                
                if not code_match:
                    continue
                
                code = code_match.group(1).strip()
                if code.upper() in STOP_WORDS:
                    continue
                
                # Determine platform
                platform = Platform.STAKE_US if 'stake.us' in text.lower() else Platform.STAKE_COM
                
                # Extract value
                val_match = re.search(r'(?:value|reward|amount|bonus)[:\s]+(\$?\d+(?:\.\d+)?\s*(?:SC|GC|USD|\$)?)', text, re.I)
                val = val_match.group(1).strip() if val_match else "Bonus Drop"
                
                # Extract wager
                wager_match = re.search(r'(?:wager|requirement|playthrough)[:\s]+([\d,]+\s*(?:x|SC|GC|USD)?)', text, re.I)
                wager = wager_match.group(1).strip() if wager_match else "Not specified"
                
                # Extract image
                img_tag = elem.find('img')
                image_url = img_tag.get('src') if img_tag and img_tag.get('src', '').startswith('http') else None
                
                item = BonusCodeItem(
                    code=code,
                    platform=platform,
                    amount_value=val,
                    wager_requirement=wager,
                    source_url=self.BASE_URL,
                    source_name="StakeCodeClaimer.com",
                    is_affiliate=True,
                    image_url=image_url,
                    description=text[:300]
                )
                
                is_valid, _ = is_valid_affiliate_code(item)
                if is_valid:
                    items.append(item)
                    
        except Exception as e:
            logger.error(f"Error scraping StakeCodeClaimer.com: {e}")
        
        return items


class AnyTimeShuffleScraper(BaseScraper):
    """Scraper for anytimeshuffle sources"""
    
    BASE_URLS = [
        "https://anytimeshuffle.com",
        "https://anytimeshuffle.com/codes",
    ]
    
    def __init__(self, timeout=15):
        super().__init__(headers=HTTP_HEADERS, timeout=timeout)
        self.session = ResilientSession(
            timeout=timeout,
            enable_jitter=ENABLE_JITTER,
            enable_proxy_rotation=ENABLE_PROXY_ROTATION
        )
    
    def scrape_all(self) -> List[BonusCodeItem]:
        items = []
        for url in self.BASE_URLS:
            try:
                html = self.session.fetch_text(url, headers=self.headers)
                if not html:
                    continue
                
                soup = BeautifulSoup(html, 'html.parser')
                code_elements = soup.find_all(['div', 'tr', 'li', 'article'], 
                    class_=re.compile(r'code|drop|promo|bonus|offer', re.I))
                
                for elem in code_elements:
                    text = " ".join(elem.get_text().split())
                    if not text or len(text) < 10:
                        continue
                    
                    code_match = re.search(r'(?:code|promo|drop|use)[:\s]+([A-Za-z0-9_\-]{4,30})', text, re.I)
                    if not code_match:
                        code_match = re.search(r'\b([A-Z0-9]{6,20})\b', text)
                    
                    if not code_match:
                        continue
                    
                    code = code_match.group(1).strip()
                    if code.upper() in STOP_WORDS:
                        continue
                    
                    platform = Platform.SHUFFLE_US if 'shuffle.us' in text.lower() else Platform.SHUFFLE_COM
                    
                    val_match = re.search(r'(?:value|reward|amount|bonus)[:\s]+(\$?\d+(?:\.\d+)?\s*(?:SC|GC|USD|\$)?)', text, re.I)
                    val = val_match.group(1).strip() if val_match else "Shuffle Drop"
                    
                    wager_match = re.search(r'(?:wager|requirement|playthrough)[:\s]+([\d,]+\s*(?:x|SC|GC|USD)?)', text, re.I)
                    wager = wager_match.group(1).strip() if wager_match else "Not specified"
                    
                    img_tag = elem.find('img')
                    image_url = img_tag.get('src') if img_tag and img_tag.get('src', '').startswith('http') else None
                    
                    item = BonusCodeItem(
                        code=code,
                        platform=platform,
                        amount_value=val,
                        wager_requirement=wager,
                        source_url=url,
                        source_name="AnyTimeShuffle",
                        is_affiliate=True,
                        image_url=image_url,
                        description=text[:300]
                    )
                    
                    is_valid, _ = is_valid_affiliate_code(item)
                    if is_valid:
                        items.append(item)
                        
            except Exception as e:
                logger.error(f"Error scraping AnyTimeShuffle ({url}): {e}")
        
        return items


class BrokeChubbScraper(BaseScraper):
    """Scraper for brokechubb sources"""
    
    BASE_URL = "https://brokechubb.com"
    
    def __init__(self, timeout=15):
        super().__init__(headers=HTTP_HEADERS, timeout=timeout)
        self.session = ResilientSession(
            timeout=timeout,
            enable_jitter=ENABLE_JITTER,
            enable_proxy_rotation=ENABLE_PROXY_ROTATION
        )
    
    def scrape_all(self) -> List[BonusCodeItem]:
        items = []
        try:
            html = self.session.fetch_text(self.BASE_URL, headers=self.headers)
            if not html:
                return items
            
            soup = BeautifulSoup(html, 'html.parser')
            code_elements = soup.find_all(['div', 'tr', 'li', 'article'], 
                class_=re.compile(r'code|drop|promo|bonus|offer', re.I))
            
            for elem in code_elements:
                text = " ".join(elem.get_text().split())
                if not text or len(text) < 10:
                    continue
                
                code_match = re.search(r'(?:code|promo|drop|use)[:\s]+([A-Za-z0-9_\-]{4,30})', text, re.I)
                if not code_match:
                    code_match = re.search(r'\b([A-Z0-9]{6,20})\b', text)
                
                if not code_match:
                    continue
                
                code = code_match.group(1).strip()
                if code.upper() in STOP_WORDS:
                    continue
                
                platform = Platform.STAKE_US if 'stake.us' in text.lower() else Platform.STAKE_COM
                
                val_match = re.search(r'(?:value|reward|amount|bonus)[:\s]+(\$?\d+(?:\.\d+)?\s*(?:SC|GC|USD|\$)?)', text, re.I)
                val = val_match.group(1).strip() if val_match else "Bonus Drop"
                
                wager_match = re.search(r'(?:wager|requirement|playthrough)[:\s]+([\d,]+\s*(?:x|SC|GC|USD)?)', text, re.I)
                wager = wager_match.group(1).strip() if wager_match else "Not specified"
                
                img_tag = elem.find('img')
                image_url = img_tag.get('src') if img_tag and img_tag.get('src', '').startswith('http') else None
                
                item = BonusCodeItem(
                    code=code,
                    platform=platform,
                    amount_value=val,
                    wager_requirement=wager,
                    source_url=self.BASE_URL,
                    source_name="BrokeChubb",
                    is_affiliate=True,
                    image_url=image_url,
                    description=text[:300]
                )
                
                is_valid, _ = is_valid_affiliate_code(item)
                if is_valid:
                    items.append(item)
                    
        except Exception as e:
            logger.error(f"Error scraping BrokeChubb: {e}")
        
        return items


class GreasyForkStakeClaimerScraper(BaseScraper):
    """Scraper for GreasyFork StakeClaimer userscript - extracts code sources from script metadata"""
    
    BASE_URL = "https://greasyfork.org/en/scripts/585972-stakeclaimer-stake-reload-and-telegram-code-claimer"
    
    def __init__(self, timeout=15):
        super().__init__(headers=HTTP_HEADERS, timeout=timeout)
        self.session = ResilientSession(
            timeout=timeout,
            enable_jitter=ENABLE_JITTER,
            enable_proxy_rotation=ENABLE_PROXY_ROTATION
        )
    
    def scrape_all(self) -> List[BonusCodeItem]:
        """Extract Telegram channels and sources mentioned in the userscript"""
        items = []
        try:
            html = self.session.fetch_text(self.BASE_URL, headers=self.headers)
            if not html:
                return items
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Get script code/content
            script_content = soup.get_text()
            
            # Look for Telegram channel references in the script
            tg_channels = re.findall(r'@[a-zA-Z0-9_]{3,30}', script_content)
            tg_channels += re.findall(r't\.me/([a-zA-Z0-9_]{3,30})', script_content)
            
            for ch in set(tg_channels):
                if ch.lower() not in ['the', 'and', 'for', 'you', 'your', 'our', 'get', 'use', 'code', 'bonus', 'drop', 'claim', 'stake', 'shuffle', 'rainbet', 'winna', 'thrill', 'qzino', 'degen', 'goated']:
                    # Create a reference item for the channel
                    item = BonusCodeItem(
                        code=f"TG_CHANNEL:{ch}",
                        platform=Platform.UNKNOWN,
                        amount_value="Telegram Channel Source",
                        wager_requirement="N/A",
                        source_url=f"https://t.me/{ch}",
                        source_name=f"GreasyFork StakeClaimer: @{ch}",
                        is_affiliate=False,
                        description=f"Telegram channel discovered from StakeClaimer userscript: @{ch}"
                    )
                    items.append(item)
                    
        except Exception as e:
            logger.error(f"Error scraping GreasyFork StakeClaimer: {e}")
        
        return items


def scrape_all_new_sources() -> List[BonusCodeItem]:
    """Scrape all new sources and return combined items"""
    all_items = []
    
    scrapers = [
        CodezGGScraper(),
        StakeCodeClaimerScraper(),
        AnyTimeShuffleScraper(),
        BrokeChubbScraper(),
        GreasyForkStakeClaimerScraper(),
    ]
    
    for scraper in scrapers:
        try:
            items = scraper.scrape_all()
            all_items.extend(items)
            logger.info(f"Scraped {len(items)} items from {scraper.__class__.__name__}")
        except Exception as e:
            logger.error(f"Error in {scraper.__class__.__name__}: {e}")
    
    return all_items