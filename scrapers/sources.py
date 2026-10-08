import re
import time
import urllib.parse
from typing import List, Dict, Set, Tuple, Optional
from bs4 import BeautifulSoup
from models import BonusCodeItem, Platform
from scrapers.base import BaseScraper
from filters import is_telegram_or_low_value_drop, is_valid_affiliate_code, extract_event_datetime, is_event_recent, STOP_WORDS

SOURCE_CODE_PATTERNS: List[Tuple[re.Pattern, Platform, str]] = [
    # Ballislife: BIL7M0C5T8, BIL4D9V3L1, BIL0R8W6Q2, BILGPK11VL, BILGXLPOKQ, BILGXT8U1V, BILJKABDYH, BILJVUOA5R
    # Must start with BIL, length 8 to 15 chars, containing numbers
    (re.compile(r"\b(BIL(?:\d[A-Za-z0-9]{6,12}|[A-Z0-9]{7,12}))\b"), Platform.STAKE_US, "Ballislife"),

    # NEXT.io: NEXT1V7QPK3XLMR, NEXT8T2KRV9LQXP, NEXT5Q4XLM7PRVK, NEXT4R7KQ2M9LXP, NEXT9T3WJ6N8KZR, NEXT2P8XM5Q7LKC
    # Must start with NEXT followed by a digit and alphanumeric chars (length 10-25)
    (re.compile(r"\b(NEXT\d[A-Za-z0-9]{7,22})\b", re.I), Platform.STAKE_US, "NEXT.io"),

    # Dimers: DIMERS4Q2VRX9LKP, DIMERS7L5KXM3QPT, DIMERS7Q3KX9L2PM, DIMERS2M8WP4K7QX
    # Must start with DIMERS followed by a digit and alphanumeric chars (length 12-25)
    (re.compile(r"\b(DIMERS\d[A-Za-z0-9]{7,22})\b", re.I), Platform.STAKE_US, "Dimers"),

    # TheGameHaus: TGHSEPT26BONUS7NQ4XZ, SEPTREWARD926K8V3MP, Haus26SeptPrizeR5T9LW, BonusSEPT26DropsX2M7QK, HAUSSEPT26RewardV8C4ZN, THEGAMESEPT2026P6Y3KT, GameHausSEPT26Q9L5RX, TGHSEPTCode26M4Z8VN, SEPTTGH26DropsW7K2PC, HausRewardSEPT26B9X5QM
    # Specific drop codes with numbers, length 14-30
    (re.compile(r"\b((?:TGHSEPT|HAUSSEPT|GAMEHAUSSEPT|THEGAMESEPT|SEPTREWARD|BonusSEPT|HausReward|Haus\d|TGHSEPTCode|SEPTTGH)\d*[A-Za-z0-9]{6,25})\b", re.I), Platform.STAKE_US, "TheGameHaus"),

    # Deadspin: DSNDrop980aUS, DSNbonusDROPS93850S, DSN2983DSN3BONUSdrop, DSbonusD902130DDROP, LatestDrops502sj0, BonusDROPS2031, DropsDSN3019, Drop3394DSNCODE
    # Specific Deadspin drop prefixes, length 8-28
    (re.compile(r"\b((?:DSNDrop|DSNbonus|DSN\d|DSbonus|LatestDrops\d|BonusDROPS\d|DropsDSN\d|Drop\d+DSN)[A-Za-z0-9]{3,25})\b", re.I), Platform.STAKE_US, "Deadspin"),

    # TheLines: STAKEUSTLC007, STAKEUSTLC006, STAKEUSTLC003, STAKEUSTLC001, STAKEUSTLC002
    (re.compile(r"\b((?:STAKEUS)?TLC\d{3,5})\b", re.I), Platform.STAKE_US, "TheLines"),

    # GameChampions US: JVN23GMETITAN4L, KRX81BONUSINFERNO9B
    (re.compile(r"\b((?:JVN|KRX)\d{2}[A-Za-z0-9]{6,25})\b", re.I), Platform.STAKE_US, "GameChampions US"),

    # GameChampions: XPR24DRPECLIPSE7B, YLM52STKIGNITE8N
    (re.compile(r"\b((?:XPR|YLM)\d{2}[A-Za-z0-9]{6,25})\b", re.I), Platform.STAKE_COM, "GameChampions"),

    # Affiliate Specific Drop / Review Codes
    (re.compile(r"\b(SPIKESOCIAL|STFSOCIAL|TGTSOCIAL|VIBONUS|WETSOCIAL|BALLISLIFE|DEADSPIN|PROMOBOY|GAMECHAMPIONS|THELINES)\b", re.I), Platform.STAKE_US, "Affiliate Review")
]

class SiteScraper(BaseScraper):
    def __init__(self, headers=None, timeout=15):
        super().__init__(headers=headers, timeout=timeout)
        self._html_cache: Dict[str, Tuple[float, Optional[str]]] = {}
        self._cache_ttl = 60.0

    def _get_cached_html(self, url: str) -> Optional[str]:
        cached_time, cached_html = self._html_cache.get(url, (0.0, None))
        if cached_html and (time.time() - cached_time) < self._cache_ttl:
            return cached_html
        return None

    def _set_cached_html(self, url: str, html: Optional[str]) -> None:
        if html:
            self._html_cache[url] = (time.time(), html)

    def fetch_html(self, url: str) -> Optional[str]:
        cached = self._get_cached_html(url)
        if cached is not None:
            return cached
        html = super().fetch_html(url)
        self._set_cached_html(url, html)
        return html

    def extract_from_data_attributes(self, soup: BeautifulSoup, url: str, platform: Platform, source_name: str) -> List[BonusCodeItem]:
        items: List[BonusCodeItem] = []
        seen_codes: Set[str] = set()

        # Find all tags with code data attributes
        code_tags = soup.find_all(lambda tag: (
            tag.has_attr('data-code') or
            tag.has_attr('data-promo') or
            tag.has_attr('data-promocode') or
            tag.has_attr('data-bonus-code') or
            tag.has_attr('data-clipboard-text') or
            tag.has_attr('data-coupon')
        ))

        for tag in code_tags:
            code = (
                tag.get('data-code') or
                tag.get('data-promo') or
                tag.get('data-promocode') or
                tag.get('data-bonus-code') or
                tag.get('data-clipboard-text') or
                tag.get('data-coupon') or
                ''
            ).strip()

            if not code or code.upper() in STOP_WORDS or code.upper() in seen_codes:
                continue

            # Check context around tag
            parent = tag
            for _ in range(4):
                if parent and parent.parent:
                    parent = parent.parent
            context_text = ' '.join(parent.get_text().split()) if parent else ''

            # Check if this element or parent belongs to a different casino review on the same page
            if any(competitor in context_text.lower() for competitor in ['betrivers', 'fanduel', 'draftkings', 'pulsz', 'mcluck', 'chumba', 'crowncoins', 'myprize', 'lonestar', 'acebet']):
                if not any(st in context_text.lower() for st in ['stake.us', 'stake.com', 'stake us', 'stake com', 'stake']):
                    continue

            # Extract value and wager
            val, wager = self.extract_value_and_wager_from_text(context_text)
            event_dt = extract_event_datetime(context_text)

            item = BonusCodeItem(
                code=code,
                platform=platform,
                amount_value=val,
                wager_requirement=wager,
                source_url=url,
                source_name=source_name,
                is_affiliate=True,
                event_datetime=event_dt,
                description=context_text[:250]
            )

            is_valid, _ = is_valid_affiliate_code(item)
            if is_valid:
                seen_codes.add(code.upper())
                items.append(item)

        return items

    def extract_from_promo_classes(self, soup: BeautifulSoup, url: str, platform: Platform, source_name: str) -> List[BonusCodeItem]:
        items: List[BonusCodeItem] = []
        seen_codes: Set[str] = set()

        # Target class names often containing promo badges/codes
        selectors = [
            '[class*="code-field"]',
            '[class*="promocode"]',
            '[class*="promo-code"]',
            '[class*="bonus-code"]',
            '[class*="coupon-code"]',
            '[class*="affiliate-code"]',
            '[class*="exclusive-code"]',
            '[class*="voucher"]'
        ]
        
        for sel in selectors:
            for tag in soup.select(sel):
                txt = tag.get_text(strip=True)
                # Code candidate is usually 3-30 alphanumeric chars
                if 3 <= len(txt) <= 30 and re.match(r"^[A-Za-z0-9_\-]+$", txt):
                    if txt.upper() in STOP_WORDS or txt.upper() in seen_codes:
                        continue
                    
                    parent = tag.parent.parent if tag.parent and tag.parent.parent else tag
                    context_text = ' '.join(parent.get_text().split())

                    val, wager = self.extract_value_and_wager_from_text(context_text)
                    event_dt = extract_event_datetime(context_text)

                    item = BonusCodeItem(
                        code=txt,
                        platform=platform,
                        amount_value=val,
                        wager_requirement=wager,
                        source_url=url,
                        source_name=source_name,
                        is_affiliate=True,
                        event_datetime=event_dt,
                        description=context_text[:250]
                    )
                    is_valid, _ = is_valid_affiliate_code(item)
                    if is_valid:
                        seen_codes.add(txt.upper())
                        items.append(item)

        return items

    def extract_from_tables(self, soup: BeautifulSoup, url: str, platform: Platform, source_name: str) -> List[BonusCodeItem]:
        items: List[BonusCodeItem] = []
        seen_codes: Set[str] = set()

        for table in soup.find_all('table'):
            for tr in table.find_all('tr'):
                # Ignore table header rows
                if tr.find_all('th') and not tr.find_all('td'):
                    continue

                cells = [c.get_text(strip=True) for c in tr.find_all('td')]
                if not cells or len(cells) < 2:
                    continue
                
                row_text = " | ".join(cells)

                # Check if row mentions expired status
                if any(exp in row_text.lower() for exp in ["expired", "inactive", "ended", "not active", "not working"]):
                    continue

                # Find candidate code in first or second column
                for idx in [0, 1]:
                    if idx < len(cells):
                        cand = cells[idx].strip("‘'\"“” \n\r\t✓")
                        # Clean out trailing action text like 'CodeCopy' or 'Copy'
                        cand = re.sub(r'(?:Copy|Copied|Click|Redeem)$', '', cand, flags=re.I).strip()

                        if 3 <= len(cand) <= 30 and re.match(r"^[A-Za-z0-9_\-]+$", cand):
                            if cand.upper() in STOP_WORDS or cand.upper() in seen_codes:
                                continue
                            
                            val, wager = self.extract_value_and_wager_from_text(row_text)
                            event_dt = extract_event_datetime(row_text)

                            item = BonusCodeItem(
                                code=cand,
                                platform=platform,
                                amount_value=val,
                                wager_requirement=wager,
                                source_url=url,
                                source_name=source_name,
                                is_affiliate=True,
                                event_datetime=event_dt,
                                description=row_text[:250]
                            )
                            is_valid, _ = is_valid_affiliate_code(item)
                            if is_valid:
                                seen_codes.add(cand.upper())
                                items.append(item)

        return items

    def extract_from_regex_patterns(self, soup: BeautifulSoup, html: str, url: str, platform: Platform, source_name: str) -> List[BonusCodeItem]:
        items: List[BonusCodeItem] = []
        seen_codes: Set[str] = set()

        text_content = soup.get_text(separator=" ")

        for pattern, pat_platform, pat_source in SOURCE_CODE_PATTERNS:
            for match in pattern.finditer(text_content):
                code = match.group(1).strip()
                if not code or code.upper() in STOP_WORDS or code.upper() in seen_codes:
                    continue

                # Context around match
                idx = text_content.find(code)
                if idx != -1:
                    start = max(0, idx - 150)
                    end = min(len(text_content), idx + len(code) + 150)
                    context_snippet = " ".join(text_content[start:end].split())
                else:
                    context_snippet = f"Low wager drop code detected from {pat_source}"

                val, wager = self.extract_value_and_wager_from_text(context_snippet)
                if val == "Exclusive Bonus":
                    # Check for explicit amount like $5, $3, $2, $1, $5000 in context
                    m_val = re.search(r"(\$(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?|\b\d+\s*SC\b)", context_snippet, re.I)
                    if m_val:
                        val = m_val.group(1)

                target_plat = pat_platform if pat_platform else platform
                target_src = pat_source if pat_source else source_name
                event_dt = extract_event_datetime(context_snippet)

                item = BonusCodeItem(
                    code=code,
                    platform=target_plat,
                    amount_value=val,
                    wager_requirement=wager,
                    source_url=url,
                    source_name=target_src,
                    is_affiliate=True,
                    event_datetime=event_dt,
                    description=context_snippet[:250]
                )

                is_valid, _ = is_valid_affiliate_code(item)
                if is_valid:
                    seen_codes.add(code.upper())
                    items.append(item)

        return items

    def parse(self, url: str, html: str) -> List[BonusCodeItem]:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Determine source name from domain
        parsed = urllib.parse.urlparse(url)
        source_name = parsed.netloc.replace('www.', '').capitalize()
        
        # Determine target platform
        platform = self.detect_platform_from_url_or_text(url, soup.get_text()[:1000])

        all_items: List[BonusCodeItem] = []
        seen_codes: Set[str] = set()

        # 1. Primary: Targeted Regex Patterns for known Low-Wager Review sites
        regex_items = self.extract_from_regex_patterns(soup, html, url, platform, source_name)
        for it in regex_items:
            if it.code.upper() not in seen_codes:
                seen_codes.add(it.code.upper())
                all_items.append(it)

        # 2. Secondary: Data attribute elements (highest fidelity for affiliate codes)
        data_attr_items = self.extract_from_data_attributes(soup, url, platform, source_name)
        for it in data_attr_items:
            if it.code.upper() not in seen_codes:
                seen_codes.add(it.code.upper())
                all_items.append(it)

        # 3. Tertiary: Promo classes
        class_items = self.extract_from_promo_classes(soup, url, platform, source_name)
        for it in class_items:
            if it.code.upper() not in seen_codes:
                seen_codes.add(it.code.upper())
                all_items.append(it)

        # 4. Quaternary: Tables (with telegram drop exclusion)
        table_items = self.extract_from_tables(soup, url, platform, source_name)
        for it in table_items:
            if it.code.upper() not in seen_codes:
                seen_codes.add(it.code.upper())
                all_items.append(it)

        # Fallback known partner codes if present in body copy (e.g. for sites with heavy client side JS)
        known_site_codes = {
            "thelines.com": ("THELINES", "$25 SC + 25k GC Signup Bonus", "3x Rollover"),
            "thespike.gg": ("SPIKESOCIAL", "25,000 GC + 25 FREE SC + 1 SC Daily", "3x Rollover"),
            "strafe.com": ("STFSOCIAL", "250,000 GC + $25 Stake Cash + 5% Rakeback", "3x Rollover"),
            "thegruelingtruth.com": ("TGTSOCIAL", "$55 Stake Cash + 260K GC + 5% Rakeback", "3x Rollover"),
            "vegasinsider.com": ("VIBONUS", "$25 Free SC + 250,000 GC", "3x Rollover"),
            "wetten.com": ("WETSOCIAL", "$25 Free SC + 250,000 GC + 5% Rakeback", "3x Rollover"),
            "ballislife.com": ("BALLISLIFE", "250k GC + 25 SC + 5% Rakeback", "3x Rollover"),
            "deadspin.com": ("DEADSPIN", "56 SC + 560k GC + 5% Rakeback", "3x Rollover"),
            "promoguy.us": ("PROMOBOY", "250,000 GC + 25 SC Free", "3x Rollover"),
            "gamechampions.com": ("GAMECHAMPIONS", "200% Deposit Match up to $3,000 + 10% Rakeback", "40x Playthrough"),
            "dimers.com": ("DIMERS", "250,000 GC + 25 SC Free + 5% Rakeback", "3x Rollover"),
            "next.io": ("NEXT", "$5 Free SC + 5% Rakeback", "3x Rollover"),
            "thegamehaus.com": ("THEGAMEHAUS", "$5 Stake Cash + 5% Rakeback", "3x Rollover")
        }

        domain = parsed.netloc.replace('www.', '').lower()
        if not all_items and domain in known_site_codes:
            k_code, k_val, k_wager = known_site_codes[domain]
            if k_code.lower() in html.lower():
                fallback_item = BonusCodeItem(
                    code=k_code,
                    platform=platform,
                    amount_value=k_val,
                    wager_requirement=k_wager,
                    source_url=url,
                    source_name=source_name,
                    is_affiliate=True,
                    description=f"Verified exclusive affiliate partner code for {source_name}"
                )
                all_items.append(fallback_item)

        return all_items
