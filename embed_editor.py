import json
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from models import BonusCodeItem, Platform
from config import BOT_NAME, BOT_AVATAR_URL, KICK_STREAM_LINKS, DEFAULT_KICK_LINK, KICK_STREAM_LABELS, DEFAULT_KICK_LABEL, PLATFORM_SOURCE_OVERRIDES

logger = logging.getLogger(__name__)

EMBED_TEMPLATES_FILE = "embed_templates.json"


class EmbedTemplateManager:
    def __init__(self, templates_file: str = EMBED_TEMPLATES_FILE):
        self.templates_file = templates_file
        self.templates: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self):
        if os.path.exists(self.templates_file):
            try:
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    self.templates = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load embed templates: {e}")
                self.templates = {}
        if not self.templates:
            self.templates = self._generate_defaults()
            self.save()

    def save(self):
        try:
            with open(self.templates_file, 'w', encoding='utf-8') as f:
                json.dump(self.templates, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save embed templates: {e}")

    def get_template(self, platform: str) -> Dict[str, Any]:
        if platform not in self.templates:
            self.templates[platform] = self._get_empty_template()
            self.save()
        return self.templates[platform]

    def get_all_platforms(self) -> List[str]:
        return list(self.templates.keys())

    def update_template(self, platform: str, template_data: Dict[str, Any]):
        if platform in self.templates and isinstance(self.templates[platform], dict):
            self.templates[platform].update(template_data)
        else:
            self.templates[platform] = dict(template_data)
        self.save()

    def reset_template(self, platform: str, item: BonusCodeItem) -> Dict[str, Any]:
        template = self._build_template_for_item(item)
        self.templates[platform] = template
        self.save()
        return template

    def _get_empty_template(self) -> Dict[str, Any]:
        return {
            "title": "",
            "description": "",
            "color": "#5865F2",
            "thumbnail_url": "",
            "image_url": "",
            "footer_text": "",
            "footer_icon": "",
            "author_name": "",
            "author_icon": "",
            "fields": []
        }

    def _build_template_for_item(self, item: BonusCodeItem) -> Dict[str, Any]:
        platform_name = item.platform.value.upper()
        emoji = item.platform.emoji
        color = item.platform.embed_color

        if item.is_highroller:
            title = f"🔥 HIGHROLLER CODE DETECTED: {item.platform.value} {emoji}"
        elif item.platform in (Platform.STAKE_COM_VIP_NOTICES, Platform.STAKE_US_VIP_NOTICES):
            title = f"👑 VIP NOTICE: {item.platform.value} {emoji}"
        elif item.event_type == "WEEKLY BOOST":
            title = f"🎉 WEEKLY BOOST DETECTED: {item.platform.value} {emoji}"
        elif item.event_type == "MONTHLY BONUS":
            title = f"💰 MONTHLY BONUS DETECTED: {item.platform.value} {emoji}"
        elif item.event_type == "VIP EVENT":
            title = f"👑 VIP EVENT DETECTED: {item.platform.value} {emoji}"
        elif item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
            title = f"🚨 NEW DUAL STAKE CODE DETECTED (US & COM) {emoji}"
        elif item.platform != Platform.UNKNOWN:
            title = f"🚨 NEW {platform_name} CODE DETECTED {emoji}"
        else:
            title = "🚨 NEW PLATFORM CODE DETECTED 🎁"

        source_display = f"[{item.source_name}]({item.source_url})" if item.source_url else f"`{item.source_name}`"
        if item.platform.value in PLATFORM_SOURCE_OVERRIDES:
            override_name, override_url = PLATFORM_SOURCE_OVERRIDES[item.platform.value]
            source_display = f"[{override_name}]({override_url})"
        fields = [
            {
                "name": "🎰 Platform",
                "value": f"`{item.platform.value}` {emoji}",
                "inline": True
            },
            {
                "name": "🌐 Source",
                "value": source_display,
                "inline": True
            },
            {
                "name": "🎁 Bonus Code (Tap to Copy)",
                "value": f"```{item.clean_code}```",
                "inline": False
            },
            {
                "name": "💰 Value / Amount",
                "value": f"**{item.amount_value or 'Exclusive Offer'}**",
                "inline": True
            },
            {
                "name": "🔄 Wager Required",
                "value": f"**{item.wager_requirement or 'None / 0x'}**",
                "inline": True
            },
            {
                "name": "👥 Claims / Limit",
                "value": f"**{item.claims_count or 'Unlimited / Open'}**",
                "inline": True
            }
        ]

        if item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
            fields.append({
                "name": "🔗 Direct Redeem Links (Dual Platform)",
                "value": (
                    f"🇺🇸 **Stake.us:** [CLICK HERE TO CLAIM]({item.redeem_link_us})\n"
                    f"🌏 **Stake.com:** [CLICK HERE TO CLAIM]({item.redeem_link_com})"
                ),
                "inline": False
            })
        else:
            redeem_url = item.redeem_link
            fields.append({
                "name": "🔗 Direct Redeem Link",
                "value": f"[CLICK HERE TO CLAIM]({redeem_url})",
                "inline": False
            })

        kick_url = KICK_STREAM_LINKS.get(item.platform.value, DEFAULT_KICK_LINK)
        fields.extend([
            {
                "name": "📝 Direct Signup Link",
                "value": f"[SIGNUP HERE]({item.affiliate_signup_link})",
                "inline": True
            },
            {
                "name": "💬 Official Community",
                "value": "[JOIN DISCORD](https://discord.gg/TvJe6BV7ge)",
                "inline": True
            },
            {
                "name": KICK_STREAM_LABELS.get(item.platform.value, DEFAULT_KICK_LABEL),
                "value": f"[KICK]({kick_url})",
                "inline": True
            }
        ])

        if item.is_highroller:
            embed_desc = f"🔥 **High Roller Bonus Drop** • Instant claim detected for **{item.platform.value}**!"
        elif item.platform in (Platform.STAKE_COM_VIP_NOTICES, Platform.STAKE_US_VIP_NOTICES):
            embed_desc = f"👑 **Official VIP Notice** • Event details and claim links for **{item.platform.value}**!"
        elif item.event_type in ["WEEKLY BOOST", "MONTHLY BONUS", "VIP EVENT"]:
            embed_desc = f"👑 **Official {item.event_type}** • Direct claim links ready for **{item.platform.value}**!"
        elif item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
            embed_desc = "🚨 **Dual-Platform Bonus Drop** • Valid on both **Stake.us** and **Stake.com**!"
        elif item.is_affiliate:
            embed_desc = f"🎁 **Exclusive Partner / Affiliate Bonus** • Register or claim on **{item.platform.value}**!"
        else:
            embed_desc = f"⚡ **Verified Bonus Drop** • Instant claim for **{item.platform.value}**!"

        template: Dict[str, Any] = {
            "title": title,
            "description": embed_desc,
            "color": f"#{color:06X}",
            "fields": fields,
            "footer_text": f"{BOT_NAME} • Detected at {item.detected_at}",
            "footer_icon": "",
            "author_name": "",
            "author_icon": "",
            "thumbnail_url": "",
            "image_url": item.image_url or ""
        }

        return template

    def _generate_defaults(self) -> Dict[str, Dict[str, Any]]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        sample_items = {
            Platform.STAKE_COM: BonusCodeItem(
                code="stakecom20isfwl8h12zwe",
                platform=Platform.STAKE_COM,
                amount_value="$12.50 USD",
                wager_requirement="$50,000 wagered in last 7 days",
                source_url="https://t.me/highrollerscode/451",
                source_name="@highrollerscode",
                is_affiliate=False,
                is_highroller=True,
                currency="ltc",
                claims_count="$50,000 Total Drop Limit",
                description="[TEST EVENT] High Roller Stake.com drop.",
                detected_at=now
            ),
            Platform.STAKE_US: BonusCodeItem(
                code="stakeusdqzndszza8v2nq",
                platform=Platform.STAKE_US,
                amount_value="2 SC + 20,000 GC",
                wager_requirement="8,000 SC played in last 7 days",
                source_url="https://t.me/dailybonuscodeUS/575",
                source_name="@dailybonuscodeUS",
                is_affiliate=False,
                currency="sweeps",
                claims_count="2,000 SC Limit",
                description="[TEST EVENT] Fresh Stake.us verified bonus drop.",
                detected_at=now
            ),
            Platform.STAKE_COM_VIP_NOTICES: BonusCodeItem(
                code="STAKE_COM_WEEKLY_BOOST_#123",
                platform=Platform.STAKE_COM_VIP_NOTICES,
                amount_value="VIP Weekly Boost Claim Link",
                wager_requirement="VIP Tier Based",
                source_url="https://t.me/c/2922581483/61",
                source_name="Stake.com VIP Notices",
                is_affiliate=False,
                event_type="WEEKLY BOOST",
                description="[TEST EVENT] Stake.com VIP Weekly Boost notice with claim link.",
                detected_at=now
            ),
            Platform.STAKE_US_VIP_NOTICES: BonusCodeItem(
                code="STAKE_US_WEEKLY_BOOST_#456",
                platform=Platform.STAKE_US_VIP_NOTICES,
                amount_value="VIP Weekly Boost Claim Link",
                wager_requirement="VIP Tier Based",
                source_url="https://t.me/c/1542279201/257",
                source_name="Stake.us VIP Notices",
                is_affiliate=False,
                event_type="WEEKLY BOOST",
                description="[TEST EVENT] Stake.us VIP Weekly Boost notice with claim link.",
                detected_at=now
            ),
            Platform.SHUFFLE_COM: BonusCodeItem(
                code="KZU80TZA",
                platform=Platform.SHUFFLE_COM,
                amount_value="$25.00 USD",
                wager_requirement="$100,000 wager past 7 days",
                source_url="https://t.me/codestats2/26027",
                source_name="@codestats2",
                is_affiliate=False,
                claims_count="150 Claims",
                description="[TEST EVENT] Shuffle.com verified bonus drop.",
                detected_at=now
            ),
            Platform.SHUFFLE_US: BonusCodeItem(
                code="NK60ZYU0",
                platform=Platform.SHUFFLE_US,
                amount_value="1.5 SC + 15,000 GC",
                wager_requirement="2,500 SC played in last 7 days",
                source_url="https://t.me/codestats2/26029",
                source_name="@codestats2",
                is_affiliate=False,
                claims_count="500 Claims",
                description="[TEST EVENT] Shuffle.us social casino drop.",
                detected_at=now
            ),
            Platform.RAINBET: BonusCodeItem(
                code="MFQP3DSN",
                platform=Platform.RAINBET,
                amount_value="$10.00",
                wager_requirement="$4,000 Wager Required",
                source_url="https://t.me/EddiesCodesRainbet/2083",
                source_name="@EddiesCodesRainbet",
                is_affiliate=False,
                claims_count="600 Claims",
                description="[TEST EVENT] Rainbet instant drop code.",
                detected_at=now
            ),
            Platform.DEGEN: BonusCodeItem(
                code="DEGENVIP88",
                platform=Platform.DEGEN,
                amount_value="$5.00 Bonus Drop",
                wager_requirement="$2,500 Wager",
                source_url="https://t.me/degendotcom",
                source_name="@degendotcom",
                is_affiliate=False,
                image_url="https://i.imgur.com/8Q9Z5bF.png",
                description="[TEST EVENT] Degen drop with media verification.",
                detected_at=now
            ),
            Platform.QZINO: BonusCodeItem(
                code="QZINOMAX",
                platform=Platform.QZINO,
                amount_value="100% Match + AI Rakeback",
                wager_requirement="10x Playthrough",
                source_url="https://qzino.ai",
                source_name="Qzino AI",
                is_affiliate=True,
                description="[TEST EVENT] Exclusive Qzino promotion.",
                detected_at=now
            ),
            Platform.GOATED: BonusCodeItem(
                code="GOATEDVIP",
                platform=Platform.GOATED,
                amount_value="100% Deposit Match + 5% Rakeback",
                wager_requirement="30x Playthrough",
                source_url="https://goated.com",
                source_name="Goated VIP",
                is_affiliate=True,
                description="[TEST EVENT] Goated VIP bonus drop.",
                detected_at=now
            ),
            Platform.DUAL_STAKE: BonusCodeItem(
                code="mjp6axxg",
                platform=Platform.DUAL_STAKE,
                amount_value="$3.00 (US & COM)",
                wager_requirement="$6,000 Played in last 7 days",
                source_url="https://t.me/codestats2/26044",
                source_name="@codestats2",
                is_affiliate=False,
                is_dual_stake=True,
                description="[TEST EVENT] Dual Stake code valid on both Stake.us and Stake.com.",
                detected_at=now
            ),
             Platform.THRILL: BonusCodeItem(
                code="THRILL_TEST",
                platform=Platform.THRILL,
                amount_value="Exclusive Offer",
                wager_requirement="None",
                source_url="https://thrill.com",
                source_name="THRILL",
                is_affiliate=True,
                description="[TEST EVENT] THRILL exclusive signup link.",
                detected_at=now
            ),
            Platform.WINNA: BonusCodeItem(
                code="WINNA_TEST",
                platform=Platform.WINNA,
                amount_value="Exclusive Offer",
                wager_requirement="None",
                source_url="https://winna.com",
                source_name="WINNA",
                is_affiliate=True,
                description="[TEST EVENT] WINNA exclusive signup link.",
                detected_at=now
            ),
        }

        defaults = {}
        for plat, item in sample_items.items():
            defaults[plat.value] = self._build_template_for_item(item)
        return defaults

    def template_to_embed_dict(self, template: Dict[str, Any]) -> Dict[str, Any]:
        embed = {
            "title": template.get("title", ""),
            "description": template.get("description", ""),
            "color": self._hex_to_int(template.get("color", "#5865F2")),
            "fields": template.get("fields", []),
        }
        if template.get("thumbnail_url"):
            embed["thumbnail"] = {"url": template["thumbnail_url"]}
        if template.get("image_url"):
            embed["image"] = {"url": template["image_url"]}
        if template.get("footer_text"):
            footer = {"text": template["footer_text"]}
            if template.get("footer_icon"):
                footer["icon_url"] = template["footer_icon"]
            embed["footer"] = footer
        if template.get("author_name"):
            author = {"name": template["author_name"]}
            if template.get("author_icon"):
                author["icon_url"] = template["author_icon"]
            embed["author"] = author
        return embed

    def _hex_to_int(self, hex_color: str) -> int:
        hex_color = hex_color.lstrip("#")
        return int(hex_color, 16)
