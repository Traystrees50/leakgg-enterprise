from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import urllib.parse
from config import (
    COLOR_STAKE_COM, COLOR_STAKE_US, COLOR_SHUFFLE_COM, COLOR_SHUFFLE_US,
    COLOR_QZINO, COLOR_RAINBET, COLOR_DEGEN, COLOR_GOATED, COLOR_DUAL_STAKE,
    COLOR_DEFAULT, COLOR_STAKE_COM_VIP_NOTICES, COLOR_STAKE_US_VIP_NOTICES,
    COLOR_MYPRIZE_US, COLOR_CROWNSCOINS, COLOR_REALPRIZE, COLOR_ACEBET,
    COLOR_LONESTAR, COLOR_CHANCED, COLOR_PULSZ,
    COLOR_THRILL, COLOR_MODO, COLOR_BABA,
    COLOR_COOKED_US, COLOR_COOKED_COM, COLOR_WOWVEGAS, COLOR_YAYCASINO,
    COLOR_WINNA,
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
    DEGEN = "Degen"
    GOATED = "Goated"
    DUAL_STAKE = "Stake.us & Stake.com"
    MYPRIZE_US = "MYPRIZE.US"
    CROWNSCOINS = "CrownCoins"
    REALPRIZE = "RealPrize"
    ACEBET = "AceBet Casino"
    LONESTAR = "LoneStar Casino"
    CHANCED = "Chanced Casino"
    PULSZ = "PULSZ"
    THRILL = "THRILL"
    MODO = "MODO"
    BABA = "BABA"
    COOKED_US = "COOKED.US"
    COOKED_COM = "COOKED.COM"
    WOWVEGAS = "WOWVEGAS"
    YAYCASINO = "YAYCASINO"
    WINNA = "WINNA"
    UNKNOWN = "Unknown Platform"

    @classmethod
    def from_str(cls, text: str) -> "Platform":
        t = text.lower()
        if "dual" in t or ("stake.us" in t and "stake.com" in t) or ("stake us" in t and "stake com" in t):
            return cls.DUAL_STAKE
        elif "shuffle.us" in t or "shuffle us" in t or "shuffle_us" in t:
            return cls.SHUFFLE_US
        elif "shuffle.com" in t or "shuffle com" in t or "shuffle" in t:
            return cls.SHUFFLE_COM
        elif "qzino" in t:
            return cls.QZINO
        elif "rainbet" in t:
            return cls.RAINBET
        elif "degen" in t:
            return cls.DEGEN
        elif "goated" in t:
            return cls.GOATED
        elif "stake.com - vip" in t or "stake.com vip" in t or "stakecom vip" in t:
            return cls.STAKE_COM_VIP_NOTICES
        elif "stake.us - vip" in t or "stake.us vip" in t or "stakeus vip" in t:
            return cls.STAKE_US_VIP_NOTICES
        elif "stake-us" in t or "stake.us" in t or "stakeus" in t or "stake us" in t:
            return cls.STAKE_US
        elif "stake-com" in t or "stake.com" in t or "stakecom" in t or "stake com" in t or "stake" in t:
            return cls.STAKE_COM
        elif "myprize" in t or "myprize.us" in t:
            return cls.MYPRIZE_US
        elif "crown" in t or "crowncoins" in t:
            return cls.CROWNSCOINS
        elif "realprize" in t:
            return cls.REALPRIZE
        elif "acebet" in t:
            return cls.ACEBET
        elif "lonestar" in t:
            return cls.LONESTAR
        elif "chanced" in t:
            return cls.CHANCED
        elif "pulsz" in t:
            return cls.PULSZ
        elif "thrill" in t:
            return cls.THRILL
        elif "modo" in t:
            return cls.MODO
        elif "baba" in t or "babacasino" in t:
            return cls.BABA
        elif "cooked.us" in t or "cooked us" in t:
            return cls.COOKED_US
        elif "cooked.com" in t or "cooked com" in t or "cookedcom" in t:
            return cls.COOKED_COM
        elif "wowvegas" in t:
            return cls.WOWVEGAS
        elif "yaycasino" in t:
            return cls.YAYCASINO
        elif "winna" in t:
            return cls.WINNA
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
            Platform.DEGEN: COLOR_DEGEN,
            Platform.GOATED: COLOR_GOATED,
            Platform.DUAL_STAKE: COLOR_DUAL_STAKE,
            Platform.MYPRIZE_US: COLOR_MYPRIZE_US,
            Platform.CROWNSCOINS: COLOR_CROWNSCOINS,
            Platform.REALPRIZE: COLOR_REALPRIZE,
            Platform.ACEBET: COLOR_ACEBET,
            Platform.LONESTAR: COLOR_LONESTAR,
            Platform.CHANCED: COLOR_CHANCED,
            Platform.PULSZ: COLOR_PULSZ,
            Platform.THRILL: COLOR_THRILL,
            Platform.MODO: COLOR_MODO,
            Platform.BABA: COLOR_BABA,
            Platform.COOKED_US: COLOR_COOKED_US,
            Platform.COOKED_COM: COLOR_COOKED_COM,
            Platform.WOWVEGAS: COLOR_WOWVEGAS,
            Platform.YAYCASINO: COLOR_YAYCASINO,
            Platform.WINNA: COLOR_WINNA,
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
            Platform.DEGEN: "🔥 ⚡",
            Platform.GOATED: "🐐 👑",
            Platform.DUAL_STAKE: "🎰 🌐",
            Platform.MYPRIZE_US: "💎 🇺🇸",
            Platform.CROWNSCOINS: "👑 🏆",
            Platform.REALPRIZE: "🎁 🎉",
            Platform.ACEBET: "🎰 🃏",
            Platform.LONESTAR: "⭐ 🤠",
            Platform.CHANCED: "🍀 🎲",
            Platform.PULSZ: "💎 🎰",
            Platform.THRILL: "🎢 ⚡",
            Platform.MODO: "🎮 🪙",
            Platform.BABA: "🎰 🎪",
            Platform.COOKED_US: "🍳 🇺🇸",
            Platform.COOKED_COM: "🍳 🌍",
            Platform.WOWVEGAS: "🌟 🎰",
            Platform.YAYCASINO: "🎉 🎰",
            Platform.WINNA: "🏆 🎁",
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
            Platform.DEGEN: "<@&1547761003775918130>",
            Platform.GOATED: "<@&1423077998805913680>",
            Platform.DUAL_STAKE: "<@&1268212613234298980> <@&1423076922337792094>",
            Platform.MYPRIZE_US: "@MYPRIZEUSCODES",
            Platform.CROWNSCOINS: "@CROWNCOINSCODES",
            Platform.REALPRIZE: "@REALPRIZECODES",
            Platform.ACEBET: "@ACEBETCODES",
            Platform.LONESTAR: "@LONESTARCODES",
            Platform.CHANCED: "@CHANCEDCODES",
            Platform.PULSZ: "@PULSZCODES",
            Platform.THRILL: "@THRILLCODES",
            Platform.MODO: "@MODOCODES",
            Platform.BABA: "@BABACASINOCODES",
            Platform.COOKED_US: "@COOKEDUSCODES",
            Platform.COOKED_COM: "@COOKEDCOMCODES",
            Platform.WOWVEGAS: "@WOWVEGASCODES",
            Platform.YAYCASINO: "@YAYCASINOCODES",
            Platform.WINNA: "@WINNACODES",
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
            Platform.DEGEN: "https://degen.com",
            Platform.GOATED: "https://goated.com",
            Platform.MYPRIZE_US: "https://myprize.us",
            Platform.CROWNSCOINS: "https://crowncoinscasino.com",
            Platform.REALPRIZE: "https://www.realprize.com",
            Platform.ACEBET: "https://acebet.cc",
            Platform.LONESTAR: "https://lonestarcasino.com",
            Platform.CHANCED: "https://chanced.com",
            Platform.PULSZ: "https://www.pulsz.com",
            Platform.THRILL: "https://thrill.com",
            Platform.MODO: "https://modo.us",
            Platform.BABA: "https://play.babacasino.com",
            Platform.COOKED_US: "https://cooked.us",
            Platform.COOKED_COM: "https://cooked.com",
            Platform.WOWVEGAS: "https://www.wowvegas.com",
            Platform.YAYCASINO: "https://www.yaycasino.com",
            Platform.WINNA: "https://winna.com",
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
            return "https://rainbet.com/?r=murphy"
        elif self.platform == Platform.DEGEN:
            return "https://degen.com/r/selfmade"
        elif self.platform == Platform.GOATED:
            return "https://goated.com/?r=selfmade"
        elif self.platform == Platform.MYPRIZE_US:
            return "https://myprize.us/invite/Traystrees50"
        elif self.platform == Platform.CROWNSCOINS:
            return "https://crowncoinscasino.com/?utm_campaign=856db775-8290-42d7-93b4-76ddc67ddf4b&utm_source=friends"
        elif self.platform == Platform.REALPRIZE:
            return "https://www.realprize.com/refer/212990"
        elif self.platform == Platform.ACEBET:
            return "https://acebet.cc/welcome/r/selfmade"
        elif self.platform == Platform.LONESTAR:
            return "https://lonestarcasino.com/refer/869128"
        elif self.platform == Platform.CHANCED:
            return "https://chanced.com/c/v5a5yh"
        elif self.platform == Platform.PULSZ:
            return "https://www.pulsz.com/?invited_by=ga1vnk"
        elif self.platform == Platform.THRILL:
            return "https://thrill.com/?r=selfmade"
        elif self.platform == Platform.MODO:
            return "https://modo.us/?referralCode=Z901K9"
        elif self.platform == Platform.BABA:
            return "https://play.babacasino.com/#/?referral_id=5403a829ac9926527b94e7c068708e07&inv_referral=true&fb_source=invite"
        elif self.platform == Platform.COOKED_US:
            return "https://cooked.us/?auth=register&referral_source=SELFMADE"
        elif self.platform == Platform.COOKED_COM:
            return "https://cooked.com/?auth=register&referral_source=SELFMADE"
        elif self.platform == Platform.WOWVEGAS:
            return "https://www.wowvegas.com/?raf=1274028"
        elif self.platform == Platform.YAYCASINO:
            return "https://www.yaycasino.com/signup/7ab97436-a07a-4514-9506-bcbbcd2495e8"
        elif self.platform == Platform.WINNA:
            return "https://winna.com/?bonus-center=true&SELFMADE"
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
