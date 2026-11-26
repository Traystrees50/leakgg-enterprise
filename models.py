from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import urllib.parse
from config import (
    COLOR_STAKE_COM, COLOR_STAKE_US, COLOR_SHUFFLE_COM, COLOR_SHUFFLE_US,
    COLOR_QZINO, COLOR_RAINBET, COLOR_DEGEN, COLOR_GOATED, COLOR_DUAL_STAKE,
    COLOR_DEFAULT, COLOR_STAKE_COM_VIP_NOTICES, COLOR_STAKE_US_VIP_NOTICES,
    COLOR_THRILL,
    COLOR_WINNA,
    COLOR_GAMBA,
    COLOR_RAZED,
    COLOR_RAINBET_US,
    AFFILIATE_SIGNUP_LINKS
)

class Platform(str, Enum):
    STAKE_COM = "Stake.com"
    STAKE_US = "Stake.us"
    STAKE_COM_VIP_NOTICES = "Stake.com - VIP Notices"
    STAKE_US_VIP_NOTICES = "Stake.us - VIP Notices"
    SHUFFLE_COM = "Shuffle.com"
    SHUFFLE_US = "Shuffle.us"
    QZINO = "Qzino"
    RAINBET = "Rainbet"
    RAINBET_US = "Rainbet.us"
    DEGEN = "Degen"
    GOATED = "Goated"
    DUAL_STAKE = "Stake.us & Stake.com"
    THRILL = "THRILL"
    WINNA = "WINNA"
    GAMBA = "GAMBA"
    RAZED = "Razed"
    UNKNOWN = "Unknown Platform"

    @classmethod
    def from_str(cls, text: str) -> "Platform":
        t = text.lower()
        # Step 1: Dual-platform must be checked first
        if "dual" in t or ("stake.us" in t and "stake.com" in t) or ("stake us" in t and "stake com" in t):
            return cls.DUAL_STAKE
        # Step 2: Explicit Stake VIP sub-platforms
        elif "stake.com - vip" in t or "stake.com vip" in t or "stakecom vip" in t:
            return cls.STAKE_COM_VIP_NOTICES
        elif "stake.us - vip" in t or "stake.us vip" in t or "stakeus vip" in t:
            return cls.STAKE_US_VIP_NOTICES
        # Step 3: Explicit Stake.us / Stake.com keywords — evaluated BEFORE Shuffle
        elif "stake.us" in t or "stakeus" in t or "stake-us" in t or "stake us" in t:
            return cls.STAKE_US
        elif "stake.com" in t or "stakecom" in t or "stake-com" in t or "stake com" in t or "stake" in t:
            return cls.STAKE_COM
        # Step 4: Non-Stake platforms
        elif "shuffle.us" in t or "shuffle us" in t or "shuffle_us" in t:
            return cls.SHUFFLE_US
        elif "shuffle.com" in t or "shuffle com" in t or "shuffle" in t:
            return cls.SHUFFLE_COM
        elif "qzino" in t:
            return cls.QZINO
        elif "rainbet.us" in t or "rainbetus" in t:
            return cls.RAINBET_US
        elif "rainbet" in t:
            return cls.RAINBET
        elif "degen" in t:
            return cls.DEGEN
        elif "goated" in t:
            return cls.GOATED
        elif "thrill" in t:
            return cls.THRILL
        elif "winna" in t:
            return cls.WINNA
        elif "gamba" in t:
            return cls.GAMBA
        elif "razed" in t:
            return cls.RAZED
        return cls.UNKNOWN

    @property
    def embed_color(self) -> int:
        colors = {
            Platform.STAKE_COM: COLOR_STAKE_COM,
            Platform.STAKE_US: COLOR_STAKE_US,
            Platform.STAKE_COM_VIP_NOTICES: COLOR_STAKE_COM_VIP_NOTICES,
            Platform.STAKE_US_VIP_NOTICES: COLOR_STAKE_US_VIP_NOTICES,
            Platform.SHUFFLE_COM: COLOR_SHUFFLE_COM,
            Platform.SHUFFLE_US: COLOR_SHUFFLE_US,
            Platform.QZINO: COLOR_QZINO,
            Platform.RAINBET: COLOR_RAINBET,
            Platform.RAINBET_US: COLOR_RAINBET_US,
            Platform.DEGEN: COLOR_DEGEN,
            Platform.GOATED: COLOR_GOATED,
            Platform.DUAL_STAKE: COLOR_DUAL_STAKE,
            Platform.THRILL: COLOR_THRILL,
            Platform.WINNA: COLOR_WINNA,
            Platform.GAMBA: COLOR_GAMBA,
            Platform.RAZED: COLOR_RAZED,
        }
        return colors.get(self, COLOR_DEFAULT)

    @property
    def emoji(self) -> str:
        emojis = {
            Platform.STAKE_COM: "🎰 🌍",
            Platform.STAKE_US: "🎰 🇺🇸",
            Platform.STAKE_COM_VIP_NOTICES: "👑 🌍",
            Platform.STAKE_US_VIP_NOTICES: "👑 🇺🇸",
            Platform.SHUFFLE_COM: "🔀 🌍",
            Platform.SHUFFLE_US: "🔀 🇺🇸",
            Platform.QZINO: "🎲 🤖",
            Platform.RAINBET: "🌧️ ⚡",
            Platform.RAINBET_US: "🌧️ 🇺🇸",
            Platform.DEGEN: "🔥 ⚡",
            Platform.GOATED: "🐐 👑",
            Platform.DUAL_STAKE: "🎰 🌐",
            Platform.THRILL: "🎢 ⚡",
            Platform.WINNA: "🏆 🎁",
            Platform.GAMBA: "🎲 🟢",
            Platform.RAZED: "⚔️ 🔥",
        }
        return emojis.get(self, "🎁")

    @property
    def role_tag(self) -> str:
        tags = {
            Platform.STAKE_COM: "<@&1423076922337792094>",
            Platform.STAKE_US: "<@&1268212613234298980>",
            Platform.STAKE_COM_VIP_NOTICES: "<@&1423076922337792094>",
            Platform.STAKE_US_VIP_NOTICES: "<@&1268212613234298980>",
            Platform.SHUFFLE_COM: "<@&1423077015954784276>",
            Platform.SHUFFLE_US: "<@&1423076971759403089>",
            Platform.QZINO: "<@&1547759979199467680>",
            Platform.RAINBET: "<@&1423077406234906635>",
            Platform.RAINBET_US: "<@&1423077406234906635>",
            Platform.DEGEN: "<@&1547761003775918130>",
            Platform.GOATED: "<@&1423077998805913680>",
            Platform.DUAL_STAKE: "<@&1268212613234298980> <@&1423076922337792094>",
            Platform.THRILL: "@THRILLCODES",
            Platform.WINNA: "@WINNACODES",
            Platform.GAMBA: "@GAMBACODES",
            Platform.RAZED: "@RAZEDCODES",
        }
        return tags.get(self, "")

    @property
    def base_url(self) -> str:
        urls = {
            Platform.STAKE_COM: "https://stake.com",
            Platform.STAKE_US: "https://stake.us",
            Platform.STAKE_COM_VIP_NOTICES: "https://stake.com",
            Platform.STAKE_US_VIP_NOTICES: "https://stake.us",
            Platform.SHUFFLE_COM: "https://shuffle.com",
            Platform.SHUFFLE_US: "https://shuffle.us",
            Platform.QZINO: "https://qzino.ai",
            Platform.RAINBET: "https://rainbet.com",
            Platform.RAINBET_US: "https://rainbet.us",
            Platform.DEGEN: "https://degen.com",
            Platform.GOATED: "https://goated.com",
            Platform.THRILL: "https://thrill.com",
            Platform.WINNA: "https://winna.com",
            Platform.GAMBA: "https://gamba.com",
            Platform.RAZED: "https://razed.com",
        }
        return urls.get(self, "https://stake.com")

@dataclass
class BonusCodeItem:
    code: str
    platform: Platform
    amount_value: str
    wager_requirement: str
    source_url: str
    source_name: str
    is_affiliate: bool = True
    is_highroller: bool = False
    is_dual_stake: bool = False
    claims_count: Optional[str] = None
    currency: Optional[str] = None
    custom_redeem_link: Optional[str] = None
    custom_redeem_link_us: Optional[str] = None
    custom_redeem_link_com: Optional[str] = None
    image_url: Optional[str] = None
    event_type: Optional[str] = "DROP"  # "DROP", "WEEKLY BOOST", "MONTHLY BONUS", "VIP EVENT", "AFFILIATE"
    description: Optional[str] = None
    event_datetime: Optional[datetime] = None
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))

    @property
    def clean_code(self) -> str:
        """
        Preserves exact case of the bonus code (strip outer whitespace only).
        """
        return self.code.strip()

    @property
    def redeem_link(self) -> str:
        """
        Generates direct case-preserved redemption URL for the respective platform.
        """
        if self.custom_redeem_link:
            return self.custom_redeem_link

        # Preserve exact case in URL encoding
        encoded_code = urllib.parse.quote(self.clean_code, safe="")

        if self.platform == Platform.STAKE_COM:
            curr = self.currency or "ltc"
            return f"https://stake.com/settings/offers?type=drop&code={encoded_code}&currency={curr}&modal=redeemBonus"
        elif self.platform == Platform.STAKE_US:
            curr = self.currency or "sweeps"
            return f"https://stake.us/settings/offers?currency={curr}&type=drop&code={encoded_code}&modal=redeemBonus"
        elif self.platform == Platform.SHUFFLE_COM:
            return f"https://shuffle.com/?modal=c&md-code={encoded_code}"
        elif self.platform == Platform.SHUFFLE_US:
            return f"https://shuffle.us/?modal=c&md-code={encoded_code}"
        elif self.platform == Platform.RAINBET:
            return "https://rainbet.com/affiliates?modal=wallet&tab=redeem"
        elif self.platform == Platform.RAINBET_US:
            return "https://rainbet.us"
        elif self.platform == Platform.QZINO:
            return "https://qzino.ai/?r=SELFMADE"
        elif self.platform == Platform.DEGEN:
            return "https://degen.com/r/selfmade"
        elif self.platform == Platform.GOATED:
            return "https://goated.com/?r=selfmade"
        elif self.platform == Platform.DUAL_STAKE:
            return f"https://stake.us/settings/offers?currency=sweeps&type=drop&code={encoded_code}&modal=redeemBonus"
        elif self.platform == Platform.THRILL:
            return "https://thrill.com/?r=selfmade"
        elif self.platform == Platform.WINNA:
            return "https://winna.com/?bonus-center=true&SELFMADE"
        elif self.platform == Platform.GAMBA:
            return "https://gamba.com"
        elif self.platform == Platform.RAZED:
            return "https://razed.com"
        else:
            return f"https://stake.com/settings/offers?type=drop&code={encoded_code}&currency=ltc&modal=redeemBonus"

    @property
    def redeem_link_us(self) -> str:
        """
        Explicit Stake.us redemption link with case preservation.
        """
        if self.custom_redeem_link_us:
            return self.custom_redeem_link_us
        encoded_code = urllib.parse.quote(self.clean_code, safe="")
        return f"https://stake.us/settings/offers?currency=sweeps&type=drop&code={encoded_code}&modal=redeemBonus"

    @property
    def redeem_link_com(self) -> str:
        """
        Explicit Stake.com redemption link with case preservation.
        """
        if self.custom_redeem_link_com:
            return self.custom_redeem_link_com
        encoded_code = urllib.parse.quote(self.clean_code, safe="")
        return f"https://stake.com/settings/offers?type=drop&code={encoded_code}&currency=ltc&modal=redeemBonus"

    @property
    def affiliate_signup_link(self) -> str:
        """
        Returns configured dedicated platform affiliate registration link.
        """
        plat_key = self.platform.value
        if plat_key in AFFILIATE_SIGNUP_LINKS:
            return AFFILIATE_SIGNUP_LINKS[plat_key]
        
        # Fallback builders
        encoded_code = urllib.parse.quote(self.clean_code, safe="")
        if self.platform == Platform.STAKE_US:
            return "https://www.stake.us/?c=selfmade"
        elif self.platform == Platform.SHUFFLE_COM:
            return "https://shuffle.com/?r=selfmade"
        elif self.platform == Platform.SHUFFLE_US:
            return "https://shuffle.us/?r=selfmade"
        elif self.platform == Platform.QZINO:
            return "https://qzino.ai/?r=SELFMADE"
        elif self.platform == Platform.RAINBET:
            return "https://rainbet.com/?r=smokerzsektion"
        elif self.platform == Platform.RAINBET_US:
            return "https://rainbet.us"
        elif self.platform == Platform.DEGEN:
            return "https://degen.com/r/selfmade"
        elif self.platform == Platform.GOATED:
            return "https://goated.com/?r=selfmade"
        elif self.platform == Platform.THRILL:
            return "https://thrill.com/?r=selfmade"
        elif self.platform == Platform.WINNA:
            return "https://winna.com/?bonus-center=true&SELFMADE"
        elif self.platform == Platform.GAMBA:
            return AFFILIATE_SIGNUP_LINKS[Platform.GAMBA.value]
        elif self.platform == Platform.RAZED:
            return AFFILIATE_SIGNUP_LINKS.get(Platform.RAZED.value, "https://razed.com")
        return "https://stake.com/?c=SELFMADE"

    def to_stake_us_item(self) -> "BonusCodeItem":
        """
        Derives a dedicated Stake.us BonusCodeItem from a dual-platform drop.
        """
        val = self.amount_value
        if val and "USD" in val and "SC" not in val:
            val = val.replace("USD", "SC")
        return BonusCodeItem(
            code=self.code,
            platform=Platform.STAKE_US,
            amount_value=val or "Stake.us Bonus Drop",
            wager_requirement=self.wager_requirement,
            source_url=self.source_url,
            source_name=self.source_name,
            is_affiliate=self.is_affiliate,
            is_highroller=self.is_highroller,
            is_dual_stake=False,
            claims_count=self.claims_count,
            currency="sweeps",
            custom_redeem_link=self.custom_redeem_link_us or self.redeem_link_us,
            image_url=self.image_url,
            event_type=self.event_type,
            description=self.description or "Active drop on Stake.us",
            event_datetime=self.event_datetime,
            detected_at=self.detected_at
        )

    def to_stake_com_item(self) -> "BonusCodeItem":
        """
        Derives a dedicated Stake.com BonusCodeItem from a dual-platform drop.
        """
        val = self.amount_value
        if val and "SC" in val and "USD" not in val:
            val = val.replace("SC", "USD")
        return BonusCodeItem(
            code=self.code,
            platform=Platform.STAKE_COM,
            amount_value=val or "Stake.com Bonus Drop",
            wager_requirement=self.wager_requirement,
            source_url=self.source_url,
            source_name=self.source_name,
            is_affiliate=self.is_affiliate,
            is_highroller=self.is_highroller,
            is_dual_stake=False,
            claims_count=self.claims_count,
            currency="ltc",
            custom_redeem_link=self.custom_redeem_link_com or self.redeem_link_com,
            image_url=self.image_url,
            event_type=self.event_type,
            description=self.description or "Active drop on Stake.com",
            event_datetime=self.event_datetime,
            detected_at=self.detected_at
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "platform": self.platform.value,
            "amount_value": self.amount_value,
            "wager_requirement": self.wager_requirement,
            "claims_count": self.claims_count,
            "is_highroller": self.is_highroller,
            "is_dual_stake": self.is_dual_stake,
            "redeem_link": self.redeem_link,
            "redeem_link_us": self.redeem_link_us if self.is_dual_stake or self.platform == Platform.DUAL_STAKE else None,
            "redeem_link_com": self.redeem_link_com if self.is_dual_stake or self.platform == Platform.DUAL_STAKE else None,
            "affiliate_signup_link": self.affiliate_signup_link,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "is_affiliate": self.is_affiliate,
            "image_url": self.image_url,
            "event_type": self.event_type,
            "description": self.description,
            "detected_at": self.detected_at
        }
