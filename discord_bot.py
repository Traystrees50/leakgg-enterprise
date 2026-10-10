import logging
import asyncio
import re
import copy
from typing import Optional, Dict, Any, List
import discord
from discord.ext import commands, tasks

from config import DISCORD_BOT_TOKEN, BOT_NAME, BOT_AVATAR_URL, CHECK_INTERVAL_SECONDS, OWNER_USER_ID, DISCORD_INVITE_URL
from models import BonusCodeItem, Platform
from tracker import CodeTracker
from dashboard_manager import DashboardManager
from discord_notifier import DiscordNotifier, save_backup
from scrapers.engine import ScraperEngine
from scrapers.stakestats import StakeStatsPoller
from scrapers.validator import StakeCodeValidator
from health_monitor import HealthMonitor
from filters import is_valid_affiliate_code, MAX_EVENT_AGE_DAYS, STOP_WORDS
from embed_editor import EmbedTemplateManager

logger = logging.getLogger("LeakedGG.DiscordBot")
logging.getLogger("discord").setLevel(logging.WARNING)


def _has_admin_access(user: discord.abc.User) -> bool:
    """
    Returns True if the user is a server administrator or has an @admin role.
    """
    if isinstance(user, discord.Member):
        if user.guild_permissions.administrator:
            return True
        return any(role.name.lower() == "admin" for role in user.roles)
    return False


def create_unauthorized_embed() -> discord.Embed:
    """
    Generates a clean embed informing non-authorized users of the owner restriction
    and how to subscribe for $2 in any cryptocurrency.
    """
    embed = discord.Embed(
        title="🔒 Access Restricted — Owner / Subscriber Access Only",
        description=(
            f"Administrative and platform routing configuration is restricted to the Project Creator & Owner (<@{OWNER_USER_ID}>) "
            "and active subscribers.\n\n"
            "### 💎 Subscribe for $2 (Any Cryptocurrency in USD Value)\n"
            "You can unlock full access to the interactive Dashboard, personal channel bindings, and custom platform webhooks for just **$2.00 USD** in any crypto (BTC, LTC, USDT, SOL, ETH, etc.).\n\n"
            "**How to activate your subscription:**\n"
            f"1. Join our Official Discord: [JOIN DISCORD]({DISCORD_INVITE_URL})\n"
            f"2. Contact Project Owner <@{OWNER_USER_ID}> with your tx hash / username.\n"
            "3. Your User ID will be activated instantly to configure all platform drops!"
        ),
        color=0xFF1493
    )
    embed.add_field(
        name="💬 Official Community",
        value=f"[👉 Join Discord Server]({DISCORD_INVITE_URL})",
        inline=True
    )
    embed.add_field(
        name="👑 Project Owner",
        value=f"<@{OWNER_USER_ID}>",
        inline=True
    )
    embed.set_footer(text=f"{BOT_NAME} • Premium Access System", icon_url=BOT_AVATAR_URL)
    return embed

def create_subscribe_embed() -> discord.Embed:
    """
    Generates a subscription information embed guiding users on how to
    inquire about premium dashboard access for broadcasting platform bonus codes.
    """
    embed = discord.Embed(
        title="📋 Premium Dashboard Access — Inquiry Required",
        description=(
            "Unlock the full **Interactive Dashboard** with multi-platform routing, custom webhooks, "
            "and real-time monitoring controls across all your servers.\n\n"
            "### 📋 Subscription Benefits\n"
            "• ✅ Full access to `/dashboard` interactive control panel\n"
            "• ✅ Bind custom channel IDs and webhooks per platform\n"
            "• ✅ Add/remove monitored Telegram & Web Review sources\n"
            "• ✅ Test route dispatch and real-time monitoring controls\n"
            "• ✅ Works in any server where this bot is present\n\n"
            "### 📝 How to Get Access\n"
            f"1. **DM <@{OWNER_USER_ID}>** on Discord and say: \"I want to broadcast platform bonus codes in my server\"\n"
            f"2. **Join the Official Discord:** [JOIN DISCORD]({DISCORD_INVITE_URL})\n"
            f"3. **Open a ticket** in the Discord server and describe your server setup needs\n"
            f"4. Once approved, your Discord User ID will be **activated instantly** for full dashboard access!\n\n"
            "### ⚡ Instant Activation\n"
            "Once activated, you can use `/dashboard` or `!dashboard` anywhere the bot is installed."
        ),
        color=0x10B981
    )
    embed.add_field(
        name="💬 Official Community",
        value=f"[👉 Join Discord Server]({DISCORD_INVITE_URL})",
        inline=True
    )
    embed.add_field(
        name="👑 Project Owner",
        value=f"<@{OWNER_USER_ID}>",
        inline=True
    )
    embed.add_field(
        name="📋 Access Type",
        value="Inquiry-Based",
        inline=True
    )
    embed.set_footer(text=f"{BOT_NAME} • Premium Subscription", icon_url=BOT_AVATAR_URL)
    return embed


def create_info_embed() -> discord.Embed:
    """
    Generates a comprehensive information embed explaining the bot capabilities,
    supported platforms, and usage instructions.
    """
    embed = discord.Embed(
        title=f"👑 {BOT_NAME} — Information & Guide",
        description=(
            f"**{BOT_NAME}** is an enterprise real-time bonus drop & low-wager promo code monitoring engine. "
            "It automatically sweeps official channels, Telegram groups, review sources, and live tools to detect, "
            "extract, format, and broadcast bonus codes with direct one-click claim links.\n\n"
            f"💬 **Official Discord:** [JOIN DISCORD]({DISCORD_INVITE_URL})\n"
            f"🎥 **Follow Traystrees50 on Kick:** [kick.com/traystrees50](https://www.kick.com/traystrees50)"
        ),
        color=0x8A2BE2
    )

    platform_palette = (
            "• 🇺🇸 **Stake.us** — `Orange` • Social Casino Drops & VIP Boosts\n"
            "• 🌍 **Stake.com** — `Deep Pink` • Global Crypto Drops & High Rollers\n"
            "• 🔀 **Shuffle.us** — `White` • US Social Casino Bonus Drops\n"
            "• 🟣 **Shuffle.com** — `Purple` • Verified Crypto Casino Drops\n"
            "• 🎲 **Qzino** — `Gold Yellow` • AI Promos & Media Drops\n"
            "• 🌧️ **Rainbet** — `Navy Dark Blue` • Instant Wager Drops\n"
            "• 🔥 **Degen** — `Crimson Red` • Media / Graphic Drops\n"
            "• 🐐 **Goated** — `Amber Gold` • VIP Promos\n"
            "• 🎰 **Dual Stake** — `Violet` • US & COM Combined\n"
            "• 💎 **MYPRIZE.US** — `Cyan` • Exclusive Offers\n"
            "• 👑 **CrownCoins** — `Gold` • Social Casino Sweeps\n"
            "• 🎁 **RealPrize** — `Pink` • Referral Rewards\n"
            "• 🎰 **AceBet Casino** — `Red` • Crypto Casino Drops\n"
            "• ⭐ **LoneStar Casino** — `Orange` • Texas-Style Promos\n"
            "• 🍀 **Chanced Casino** — `Green` • Lucky Drop Events\n"
            "• 💎 **PULSZ** — `Purple` • PULSZ Platform\n"
            "• 🎢 **THRILL** — `Red` • THRILL Platform\n"
            "• 🎮 **MODO** — `Blue` • MODO Platform\n"
            "• 🎰 **BABA** — `Green` • BABA Casino\n"
            "• 🍳 **COOKED.US** — `Amber` • COOKED.US Platform\n"
            "• 🍳 **COOKED.COM** — `Amber` • COOKED.COM Platform\n"
            "• 🌟 **WOWVEGAS** — `Violet` • WOWVEGAS Platform\n"
            "• 🎉 **YAYCASINO** — `Pink` • YAYCASINO Platform\n"
            "• 🏆 **WINNA** — `Gold` • WINNA Platform"
    )
    palette_lines = platform_palette.splitlines()
    embed.add_field(
        name="🎰 Supported Platforms & Theme Palette",
        value="\n".join(palette_lines[:13]),
        inline=False
    )
    embed.add_field(
        name="🎰 Supported Platforms (continued)",
        value="\n".join(palette_lines[13:]),
        inline=False
    )

    embed.add_field(
        name="⚡ Core Commands",
        value=(
            "• `/activecodes` — Query StakeStats live for active Stake.us & Stake.com drops with copyable codes & redeem links.\n"
            "• `/dashboard` — Personal routing dashboard; subscribers configure their own server channels, DMs, and webhooks.\n"
            "• `/info` — Display this information overview.\n"
            "• `/help` — Detailed usage guide and platform links.\n"
            "• `/commands` — View all available commands.\n"
            "• `/links` — View all affiliate/signup links for every platform.\n"
            "• `/subscribe` — Unlock full dashboard access for $2 in any crypto."
        ),
        inline=False
    )

    embed.add_field(
        name="💎 $2 Crypto Subscription Access",
        value=(
            "Users can subscribe for **$2 in any crypto (USD value)** to gain full access to a personal `/dashboard` "
            "and bind their own server channels, DMs, and webhooks per platform without changing other users' routes.\n"
            f"Contact <@{OWNER_USER_ID}> or visit [JOIN DISCORD]({DISCORD_INVITE_URL}) to activate."
        ),
        inline=False
    )

    embed.set_footer(text=f"{BOT_NAME} • Enterprise Ready", icon_url=BOT_AVATAR_URL)
    return embed

# Sample test items for each platform for testing routing
SAMPLE_TEST_ITEMS = {
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
        description="[TEST EVENT] Fresh Stake.us verified bonus drop."
    ),
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
        description="[TEST EVENT] High Roller Stake.com drop."
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
        description="[TEST EVENT] Shuffle.us social casino drop."
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
        description="[TEST EVENT] Shuffle.com verified bonus drop."
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
        description="[TEST EVENT] Rainbet instant drop code."
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
        description="[TEST EVENT] Degen drop with media verification."
    ),
    Platform.QZINO: BonusCodeItem(
        code="QZINOMAX",
        platform=Platform.QZINO,
        amount_value="100% Match + AI Rakeback",
        wager_requirement="10x Playthrough",
        source_url="https://qzino.ai",
        source_name="Qzino AI",
        is_affiliate=True,
        description="[TEST EVENT] Exclusive Qzino promotion."
    ),
    Platform.GOATED: BonusCodeItem(
        code="GOATEDVIP",
        platform=Platform.GOATED,
        amount_value="100% Deposit Match + 5% Rakeback",
        wager_requirement="30x Playthrough",
        source_url="https://goated.com",
        source_name="Goated VIP",
        is_affiliate=True,
        description="[TEST EVENT] Goated VIP bonus drop."
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
        description="[TEST EVENT] Dual Stake code valid on both Stake.us and Stake.com."
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
        description="[TEST EVENT] Stake.com VIP Weekly Boost notice with claim link."
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
        description="[TEST EVENT] Stake.us VIP Weekly Boost notice with claim link."
    ),
    Platform.THRILL: BonusCodeItem(
        code="THRILL_TEST",
        platform=Platform.THRILL,
        amount_value="Exclusive Offer",
        wager_requirement="None",
        source_url="https://thrill.com",
        source_name="THRILL",
        is_affiliate=True,
        description="[TEST EVENT] THRILL exclusive signup link."
    ),
    Platform.WINNA: BonusCodeItem(
        code="WINNA_TEST",
        platform=Platform.WINNA,
        amount_value="Exclusive Offer",
        wager_requirement="None",
        source_url="https://winna.com",
        source_name="WINNA",
        is_affiliate=True,
        description="[TEST EVENT] WINNA exclusive signup link."
    )
}

def create_sources_embed(manager: DashboardManager) -> discord.Embed:
    """
    Generates a structured information embed listing all active and custom monitored sources
    across Telegram channels (grouped by platform), Web review sites (grouped by platform),
    and real-time APIs.
    """
    summary = manager.get_all_monitored_sources_summary()
    tg_by_plat = summary.get("telegram_by_platform", {})
    web_sources = summary.get("web_sources", [])
    web_by_platform = summary.get("web_sources_by_platform", {})
    custom = summary.get("custom_sources", {})

    total_tg = summary.get("total_telegram_channels", 0)
    total_web = summary.get("total_web_sources", 0)
    total_custom = summary.get("total_custom_sources", 0)

    embed = discord.Embed(
        title=f"📡 {BOT_NAME} — Monitored Event Sources",
        description=(
            f"Currently monitoring **{total_tg} Telegram Channels**, **{total_web} Web Review Sites**, "
            f"and **2 Live API Engines**.\n"
            f"✨ **Private Telegram Sources:** `{summary.get('total_telegram_private_sources', 0)}` | "
            f"**Custom Sources Added:** `{total_custom}` | Use `/dashboard` to manage feeds."
        ),
        color=0x1475E1
    )

    platform_emojis = {
        "stake_us": "🇺🇸 Stake.us",
        "stake_com": "🌍 Stake.com",
        "stake_us_vip": "👑 Stake.us VIP",
        "stake_com_vip": "👑 Stake.com VIP",
        "shuffle": "🔀 Shuffle",
        "qzino": "🎲 Qzino",
        "rainbet": "🌧️ Rainbet",
        "degen": "🔥 Degen",
        "goated": "🐐 Goated",
        "thrill": "🎢 THRILL",
        "winna": "🏆 WINNA",
        "codestats": "📊 CodeStats",
        "custom": "📡 Custom Feeds",
    }

    custom_tg_flat = []
    for ch_list in custom.get("telegram", {}).values():
        custom_tg_flat.extend(ch_list)

    for p_key, ch_list in tg_by_plat.items():
        title = platform_emojis.get(p_key, f"📡 {p_key.upper()} Feeds")
        formatted_chans = []
        for ch in ch_list:
            if ch in custom_tg_flat:
                formatted_chans.append(f"• `@{ch}` 🌟 *(Custom)*")
            else:
                formatted_chans.append(f"• `@{ch}`")
        if formatted_chans:
            embed.add_field(
                name=title,
                value="\n".join(formatted_chans),
                inline=True
            )

    private_tg = summary.get("telegram_private_sources", {})
    if private_tg:
        private_lines = []
        for chat_id, meta in private_tg.items():
            label = meta.get("label", chat_id)
            ref_msg = meta.get("reference_msg_id", "")
            src_url = meta.get("source_url", "")
            ref_str = f" (ref: msg {ref_msg})" if ref_msg else ""
            url_str = f" — [Link]({src_url})" if src_url else ""
            private_lines.append(f"• `{label}`{ref_str}{url_str}")
        embed.add_field(
            name="🔒 Private Telegram Sources",
            value="\n".join(private_lines) if private_lines else "None configured",
            inline=True
        )

    custom_web = custom.get("web", [])

    if web_by_platform:
        web_platform_emojis = {
            "Stake.us": "🇺🇸",
            "Stake.com": "🌍",
            "Shuffle.com": "🟣",
            "Shuffle.us": "🔀",
            "Qzino": "🎲",
            "Rainbet": "🌧️",
            "Degen": "🔥",
            "Goated": "🐐",
            "General": "🌐"
        }
        for plat_key, urls in web_by_platform.items():
            emoji = web_platform_emojis.get(plat_key, "🌐")
            display_lines = []
            for u in urls[:6]:
                is_cust = " 🌟 *(Custom)*" if u in custom_web else ""
                display_lines.append(f"• [{u.split('//')[-1].split('/')[0]}]({u}){is_cust}")
            if len(urls) > 6:
                display_lines.append(f"• *...plus {len(urls) - 6} more*")
            embed.add_field(
                name=f"{emoji} {plat_key} Web Review Sources ({len(urls)})",
                value="\n".join(display_lines) if display_lines else "None configured",
                inline=True
            )
    elif web_sources:
        web_display_lines = []
        for u in web_sources[:8]:
            is_cust = " 🌟 *(Custom)*" if u in custom_web else ""
            web_display_lines.append(f"• [{u.split('//')[-1].split('/')[0]}]({u}){is_cust}")
        if len(web_sources) > 8:
            web_display_lines.append(f"• *...plus {len(web_sources) - 8} more review sites*")
        embed.add_field(
            name=f"🌐 Web Review & Affiliate Sources ({len(web_sources)} Sites)",
            value="\n".join(web_display_lines) if web_display_lines else "None configured",
            inline=False
        )

    embed.add_field(
        name="⚡ Live Poller & Feed Endpoints",
        value=(
            "• **StakeStats:** `stakestats.net/stake/tools/code`\n"
            "• **CodeStats:** `codestats.gg`"
        ),
        inline=True
    )

    embed.add_field(
        name="🛠️ Manage Custom Sources",
        value="Use `/dashboard` → ⚙️ Action dropdown → **Add/Remove Source**.\nOpen `/dashboard` to configure channel routes.",
        inline=True
    )

    embed.set_footer(text=f"{BOT_NAME} • Source Management", icon_url=BOT_AVATAR_URL)
    return embed

def create_public_dashboard_embed() -> discord.Embed:
    """
    Generates a public-facing dashboard embed showing all affiliate/signup links
    and prompting users to subscribe for $2 in crypto to unlock full admin access.
    """
    embed = discord.Embed(
        title=f"💎 {BOT_NAME} — Public Dashboard",
        description=(
            "Welcome to the **Active Codes** public dashboard!\n\n"
            "Below are all platform affiliate/signup links. To unlock the **full interactive control panel** "
            "with multi-platform routing, custom webhooks, embed editing, and real-time monitoring controls, "
            "you need to subscribe.\n\n"
            "### 💎 Unlock Full Dashboard Access — $2 Crypto Subscription\n"
            "• ✅ Full `/dashboard` interactive control panel\n"
            "• ✅ Bind custom channel IDs and webhooks per platform\n"
            "• ✅ Add/remove monitored Telegram & Web Review sources\n"
            "• ✅ Edit embed templates (author, title, description, thumbnail, footer, fields)\n"
            "• ✅ Test route dispatch and real-time monitoring controls\n"
            "• ✅ Grant access to other users\n\n"
            "### 📝 How to Subscribe\n"
            f"1. **Tip $2 USD** in any crypto to **@traystrees50**\n"
            f"2. **Join the Official Discord:** [JOIN DISCORD]({DISCORD_INVITE_URL})\n"
            f"3. **Open a ticket** or DM <@{OWNER_USER_ID}> with your transaction hash / username\n"
            f"4. Your Discord User ID will be **activated instantly** for full dashboard access!\n\n"
            "### ⚡ Instant Activation\n"
            "Once activated, you can use `/dashboard` or `!dashboard` anywhere the bot is installed."
        ),
        color=0x1475E1
    )

    embed.add_field(
        name="🎰 Casino & Social Platforms",
        value=(
            "• 🇺🇸 **Stake.us:** [stake.us/?c=selfmade](https://www.stake.us/?c=selfmade)\n"
            "• 🌏 **Stake.com:** [stake.com/?c=SELFMADE](https://stake.com/?c=SELFMADE)\n"
            "• 👑 **Stake.us - VIP Notices:** [stake.us/?c=selfmade](https://www.stake.us/?c=selfmade)\n"
            "• 👑 **Stake.com - VIP Notices:** [stake.com/?c=SELFMADE](https://stake.com/?c=SELFMADE)\n"
            "• 🔀 **Shuffle.us:** [shuffle.us/?r=selfmade](https://shuffle.us/?r=selfmade)\n"
            "• 🟣 **Shuffle.com:** [shuffle.com/?r=selfmade](https://shuffle.com/?r=selfmade)"
        ),
        inline=False
    )
    embed.add_field(
        name="🎲 AI, Media & Niche Platforms",
        value=(
            "• 🎲 **Qzino:** [qzino.ai/?r=SELFMADE](https://qzino.ai/?r=SELFMADE)\n"
            "• 🌧️ **Rainbet:** [rainbet.com/?r=murphy](https://rainbet.com/?r=murphy)\n"
            "• 🔥 **Degen:** [degen.com/r/selfmade](https://degen.com/r/selfmade)\n"
            "• 🐐 **Goated:** [goated.com/?r=selfmade](https://goated.com/?r=selfmade)"
        ),
        inline=False
    )
    embed.add_field(
        name="💎 Partner Platforms",
        value=(
            "• 💎 **MYPRIZE.US:** [myprize.us/invite/Traystrees50](https://myprize.us/invite/Traystrees50)\n"
            "• 👑 **CrownCoins:** [crowncoinscasino.com](https://crowncoinscasino.com/?utm_campaign=856db775-8290-42d7-93b4-76ddc67ddf4b&utm_source=friends)\n"
            "• 🎁 **RealPrize:** [realprize.com/refer/212990](https://www.realprize.com/refer/212990)\n"
            "• 🎰 **AceBet Casino:** [acebet.cc/welcome/r/selfmade](https://acebet.cc/welcome/r/selfmade)\n"
            "• ⭐ **LoneStar Casino:** [lonestarcasino.com/refer/869128](https://lonestarcasino.com/refer/869128)\n"
            "• 🍀 **Chanced Casino:** [chanced.com/c/v5a5yh](https://chanced.com/c/v5a5yh)\n"
            "• 💎 **PULSZ:** [pulsz.com/?invited_by=ga1vnk](https://www.pulsz.com/?invited_by=ga1vnk)\n"
            "• 🎢 **THRILL:** [thrill.com/?r=selfmade](https://thrill.com/?r=selfmade)\n"
            "• 🎮 **MODO:** [modo.us/?referralCode=Z901K9](https://modo.us/?referralCode=Z901K9)\n"
            "• 🎰 **BABA:** [play.babacasino.com](https://play.babacasino.com/#/?referral_id=5403a829ac9926527b94e7c068708e07&inv_referral=true&fb_source=invite)"
        ),
        inline=False
    )
    embed.add_field(
        name="🍳 More Partners",
        value=(
            "• 🍳 **COOKED.US:** [cooked.us/?auth=register&referral_source=SELFMADE](https://cooked.us/?auth=register&referral_source=SELFMADE)\n"
            "• 🍳 **COOKED.COM:** [cooked.com/?auth=register&referral_source=SELFMADE](https://cooked.com/?auth=register&referral_source=SELFMADE)\n"
            "• 🌟 **WOWVEGAS:** [wowvegas.com/?raf=1274028](https://www.wowvegas.com/?raf=1274028)\n"
            "• 🎉 **YAYCASINO:** [yaycasino.com/signup/7ab97436-a07a-4514-9506-bcbbcd2495e8](https://www.yaycasino.com/signup/7ab97436-a07a-4514-9506-bcbbcd2495e8)\n"
            "• 🏆 **WINNA:** [winna.com/?bonus-center=true&SELFMADE](https://winna.com/?bonus-center=true&SELFMADE)"
        ),
        inline=False
    )
    embed.add_field(
        name="🌐 Community & Social",
        value=(
            "• 💬 **Official Discord:** [JOIN DISCORD](https://discord.gg/TvJe6BV7ge)\n"
            "• 🎥 **Follow Traystrees50 on Kick:** [kick.com/traystrees50](https://www.kick.com/traystrees50)"
        ),
        inline=False
    )

    embed.set_footer(text=f"{BOT_NAME} • Public Dashboard • Subscribe for full access", icon_url=BOT_AVATAR_URL)
    return embed


class PublicDashboardView(discord.ui.View):
    """
    Public dashboard view for non-authorized users.
    Shows affiliate links and a subscribe prompt.
    """
    def __init__(self, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        self.add_item(discord.ui.Button(label="💎 /subscribe", style=discord.ButtonStyle.success, row=0, custom_id="public_subscribe"))
        self.add_item(discord.ui.Button(label="💬 Join Discord", style=discord.ButtonStyle.link, row=0, url=DISCORD_INVITE_URL))
        self.add_item(discord.ui.Button(label="🎥 Follow on Kick", style=discord.ButtonStyle.link, row=0, url="https://www.kick.com/traystrees50"))
        self.add_item(discord.ui.Button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, row=1, custom_id="public_refresh"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "public_subscribe":
            await interaction.response.send_message(
                "To unlock full dashboard access, tip **$2 USD** in any crypto to **@traystrees50** "
                "and DM <@1051355279511519273> with your tx hash. Your User ID will be activated instantly!",
                ephemeral=True
            )
            return False
        if interaction.data.get("custom_id") == "public_refresh":
            embed = create_public_dashboard_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            return False
        return True


def create_dashboard_embed(manager: DashboardManager, bot: commands.Bot, subscriber_uid: Optional[str] = None) -> List[discord.Embed]:
    """
    Generates enterprise visual status embeds representing the multi-channel & multi-webhook
    routing configuration across all platforms and real-time monitoring state.
    Splits across multiple embeds to avoid Discord's 25-field limit.
    """
    is_realtime = manager.get_setting("realtime_monitoring_enabled", True)
    interval = manager.get_setting("check_interval_seconds", CHECK_INTERVAL_SECONDS)
    summary = manager.get_all_routes_summary()
    src_summary = manager.get_all_monitored_sources_summary()

    status_badge = f"🟢 **ACTIVE** (Every {interval}s)" if is_realtime else "🔴 **PAUSED**"

    platform_items = list(summary.items())
    chunk_size = 10
    chunks = [platform_items[i:i + chunk_size] for i in range(0, len(platform_items), chunk_size)]

    embeds: List[discord.Embed] = []
    for idx, chunk in enumerate(chunks):
        embed = discord.Embed(
            title=(
                f"🎛️ {BOT_NAME} — Enterprise Platform Control Panel"
                if idx == 0
                else f"🎛️ {BOT_NAME} — Platforms (Part {idx + 1})"
            ),
            description=(
                (
                    f"**Realtime Bonus Monitoring Status:** {status_badge}\n"
                    + (
                        f"👤 **Personal Routing Mode** — You are configuring your own channel routes. "
                        f"Notifications will be dispatched to your channels independently of other servers.\n"
                        if subscriber_uid
                        else "Configure multi-channel and multi-webhook distribution per platform using the menus below."
                    )
                )
                if idx == 0
                else "Continued platform routing overview:"
            ),
            color=0x1475E1
        )

        for plat_name, data in chunk:
            emoji = data["emoji"]

            if subscriber_uid:
                sub_channels = manager.get_subscriber_channels(subscriber_uid, plat_name)
                sub_webhooks = manager.get_subscriber_webhooks(subscriber_uid, plat_name)
                if not sub_channels:
                    sub_channels = manager.get_subscriber_channels(subscriber_uid, "Default")
                if not sub_webhooks:
                    sub_webhooks = manager.get_subscriber_webhooks(subscriber_uid, "Default")

                if not sub_channels:
                    ch_display = "❌ *Not Assigned*"
                elif len(sub_channels) == 1:
                    ch_display = f"<#{sub_channels[0]}> (`{sub_channels[0]}`)"
                else:
                    ch_display = ", ".join(f"<#{c}>" for c in sub_channels) + f" (`{len(sub_channels)} Channels`)"

                if not sub_webhooks:
                    wh_display = "❌ *Not Set*"
                elif len(sub_webhooks) == 1:
                    wh_display = "✅ *1 Webhook Active*"
                else:
                    wh_display = f"✅ *{len(sub_webhooks)} Webhooks Active*"
            else:
                ch_display = data.get("channels_display", "❌ Not Assigned")
                wh_display = data.get("webhooks_display", "❌ Not Set")

            embed.add_field(
                name=f"{emoji} {plat_name}",
                value=f"CH: {ch_display}\nWH: {wh_display}",
                inline=True
            )

        if idx == len(chunks) - 1:
            embed.add_field(
                name="📡 Active Sources",
                value=(
                    f"• **Telegram:** `{src_summary['total_telegram_channels']}` channels\n"
                    f"• **Web Reviews:** `{src_summary['total_web_sources']}` sites\n"
                    f"• **Custom Sources:** `{src_summary['total_custom_sources']}` added\n"
                    f"**Use `/dashboard` → ⚙️ Action dropdown to manage.**"
                ),
                inline=False
            )

        embed.set_footer(
            text=f"{BOT_NAME} • Select platform(s) + action from dropdowns below",
            icon_url=BOT_AVATAR_URL
        )
        embeds.append(embed)

    return embeds

# ----------------------------------------------------
# Dashboard Interactive Modals
# ----------------------------------------------------
class AddChannelModal(discord.ui.Modal):
    def __init__(self, platforms: List[str], manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None):
        super().__init__(title="Add Channel ID(s)")
        self.platforms = platforms
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid

        self.channels_input = discord.ui.TextInput(
            label=f"Channel ID(s) for {', '.join(platforms[:3])}{'...' if len(platforms) > 3 else ''}",
            placeholder="e.g. 123456789012345678, 987654321098765432",
            required=True,
            max_length=200,
            style=discord.TextStyle.short
        )
        self.add_item(self.channels_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_val = self.channels_input.value.strip()
        ids_raw = [part.strip().replace("<#", "").replace(">", "") for part in raw_val.replace(",", " ").split()]
        valid_ids = []
        for p in ids_raw:
            try:
                valid_ids.append(int(p))
            except ValueError:
                pass

        if not valid_ids:
            await interaction.response.send_message("❌ No valid integer Channel IDs provided.", ephemeral=True)
            return

        for plat in self.platforms:
            for cid in valid_ids:
                if self.subscriber_uid:
                    self.manager.add_subscriber_channel(self.subscriber_uid, plat, cid)
                else:
                    self.manager.add_channel(plat, cid)

        new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
        await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
        await interaction.followup.send(
            f"✅ Added {len(valid_ids)} channel ID(s) ({', '.join(f'<#{c}>' for c in valid_ids)}) to **{', '.join(self.platforms)}**!",
            ephemeral=True
        )


class RemoveChannelModal(discord.ui.Modal):
    def __init__(self, platforms: List[str], manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None):
        super().__init__(title="Remove Channel ID")
        self.platforms = platforms
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid

        self.channel_input = discord.ui.TextInput(
            label="Channel ID to Remove",
            placeholder="e.g. 123456789012345678",
            required=True,
            max_length=50,
            style=discord.TextStyle.short
        )
        self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_val = self.channel_input.value.strip().replace("<#", "").replace(">", "")
        try:
            cid = int(raw_val)
        except ValueError:
            await interaction.response.send_message("❌ Invalid Channel ID format.", ephemeral=True)
            return

        for plat in self.platforms:
            if self.subscriber_uid:
                self.manager.remove_subscriber_channel(self.subscriber_uid, plat, cid)
            else:
                self.manager.remove_channel(plat, cid)

        new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
        await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
        await interaction.followup.send(
            f"✅ Removed Channel ID `<#{cid}>` from **{', '.join(self.platforms)}**.",
            ephemeral=True
        )


class AddWebhookModal(discord.ui.Modal):
    def __init__(self, platforms: List[str], manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None):
        super().__init__(title="Add Discord Webhook URL(s)")
        self.platforms = platforms
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid

        self.webhook_input = discord.ui.TextInput(
            label=f"Webhook URL(s) for {', '.join(platforms[:3])}{'...' if len(platforms) > 3 else ''}",
            placeholder="https://discord.com/api/webhooks/...",
            required=True,
            max_length=400,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.webhook_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_urls = [u.strip() for u in self.webhook_input.value.replace(",", "\n").split("\n") if u.strip()]
        valid_urls = []
        for u in raw_urls:
            if u.startswith("https://discord.com/api/webhooks/") or u.startswith("https://discordapp.com/api/webhooks/"):
                valid_urls.append(u)

        if not valid_urls:
            await interaction.response.send_message("❌ No valid Discord Webhook URLs provided (must start with `https://discord.com/api/webhooks/`).", ephemeral=True)
            return

        for plat in self.platforms:
            for url in valid_urls:
                if self.subscriber_uid:
                    self.manager.add_subscriber_webhook(self.subscriber_uid, plat, url)
                else:
                    self.manager.add_webhook(plat, url)

        new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
        await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
        await interaction.followup.send(
            f"✅ Added {len(valid_urls)} webhook(s) to **{', '.join(self.platforms)}**!",
            ephemeral=True
        )


class RemoveWebhookModal(discord.ui.Modal):
    def __init__(self, platforms: List[str], manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None):
        super().__init__(title="Remove Webhook URL")
        self.platforms = platforms
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid

        self.webhook_input = discord.ui.TextInput(
            label="Webhook URL or URL Fragment to Remove",
            placeholder="https://discord.com/api/webhooks/... or part of URL",
            required=True,
            max_length=200,
            style=discord.TextStyle.short
        )
        self.add_item(self.webhook_input)

    async def on_submit(self, interaction: discord.Interaction):
        target = self.webhook_input.value.strip()
        for plat in self.platforms:
            if self.subscriber_uid:
                current_whs = self.manager.get_subscriber_webhooks(self.subscriber_uid, plat)
                for wh in current_whs:
                    if target in wh:
                        uid = self.subscriber_uid
                        sub_routes = self.manager._get_subscriber_routes(uid)
                        key = self.manager._normalize_platform_key(plat)
                        if key in sub_routes.get("webhooks", {}):
                            if wh in sub_routes["webhooks"][key]:
                                sub_routes["webhooks"][key].remove(wh)
                                if not sub_routes["webhooks"][key]:
                                    del sub_routes["webhooks"][key]
                                self.manager.save()
            else:
                current_whs = self.manager.get_webhooks(plat)
                for wh in current_whs:
                    if target in wh:
                        self.manager.remove_webhook(plat, wh)

        new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
        await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
        await interaction.followup.send(
            f"✅ Removed matching webhook from **{', '.join(self.platforms)}**.",
            ephemeral=True
        )


class IntervalModal(discord.ui.Modal):
    def __init__(self, manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None):
        super().__init__(title="Adjust Realtime Sweep Interval")
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid

        self.interval_input = discord.ui.TextInput(
            label="Scan Interval (in seconds)",
            placeholder="e.g. 30, 60, 120",
            required=True,
            max_length=5,
            default=str(self.manager.get_setting("check_interval_seconds", CHECK_INTERVAL_SECONDS))
        )
        self.add_item(self.interval_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.interval_input.value.strip())
            if val < 15:
                await interaction.response.send_message("⚠️ Minimum scan interval is 15 seconds to prevent rate limits.", ephemeral=True)
                return
            self.manager.set_setting("check_interval_seconds", val)
            
            if hasattr(interaction.client, "background_monitor_task") and interaction.client.background_monitor_task.is_running():
                interaction.client.background_monitor_task.change_interval(seconds=val)

            new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
            await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
            await interaction.followup.send(f"✅ Monitoring interval updated to **{val} seconds**.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please provide a valid integer number of seconds.", ephemeral=True)


class AddSourceModal(discord.ui.Modal):
    def __init__(self, manager: DashboardManager, view: "DashboardView", default_platform: Optional[str] = None, subscriber_uid: Optional[str] = None):
        super().__init__(title="Add Monitored Event Source")
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid

        self.type_input = discord.ui.TextInput(
            label="Source Type (telegram or web)",
            placeholder="Type 'telegram' for channel or 'web' for URL",
            required=True,
            max_length=15,
            default="telegram"
        )
        self.add_item(self.type_input)

        self.source_input = discord.ui.TextInput(
            label="Channel Handle or Web URL",
            placeholder="e.g. @bonus_channel or https://site.com/drops",
            required=True,
            max_length=300,
            style=discord.TextStyle.short
        )
        self.add_item(self.source_input)

        self.platform_input = discord.ui.TextInput(
            label="Platform (for Telegram channels)",
            placeholder="Stake.us, Stake.com, Shuffle, Qzino, Rainbet, Degen, Goated, All",
            required=False,
            max_length=30,
            default=default_platform or "All"
        )
        self.add_item(self.platform_input)

    async def on_submit(self, interaction: discord.Interaction):
        stype = self.type_input.value.strip().lower()
        src_val = self.source_input.value.strip()
        plat_val = self.platform_input.value.strip() or "custom"

        if "web" in stype or src_val.startswith("http://") or src_val.startswith("https://"):
            success, msg = self.manager.add_web_source(src_val)
        else:
            success, msg = self.manager.add_telegram_source(src_val, plat_val)

        if success:
            new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
            await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


class RemoveSourceModal(discord.ui.Modal):
    def __init__(self, manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None):
        super().__init__(title="Remove Custom Monitored Source")
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid

        self.source_input = discord.ui.TextInput(
            label="Custom Channel Handle or Web URL to Remove",
            placeholder="e.g. @bonus_channel or https://site.com/drops",
            required=True,
            max_length=300,
            style=discord.TextStyle.short
        )
        self.add_item(self.source_input)

    async def on_submit(self, interaction: discord.Interaction):
        src_val = self.source_input.value.strip()
        if src_val.startswith("http://") or src_val.startswith("https://"):
            success, msg = self.manager.remove_web_source(src_val)
        else:
            success, msg = self.manager.remove_telegram_source(src_val)

        if success:
            new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
            await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


# ----------------------------------------------------
# Dashboard UI Dropdowns & View Components
# ----------------------------------------------------
class PlatformMultiSelect(discord.ui.Select):
    """
    Step 1: Multi-select dropdown to choose one or more platforms to configure.
    """
    def __init__(self):
        options = [
            discord.SelectOption(label="Stake.us", description="Stake.us Social Casino Drops", emoji="🇺🇸"),
            discord.SelectOption(label="Stake.com", description="Stake.com Global Crypto Drops", emoji="🌍"),
            discord.SelectOption(label="Stake.us - VIP Notices", description="Stake.us VIP Weekly/Monthly Bonus Notices", emoji="👑"),
            discord.SelectOption(label="Stake.com - VIP Notices", description="Stake.com VIP Weekly/Monthly Bonus Notices", emoji="👑"),
            discord.SelectOption(label="Shuffle.us", description="Shuffle.us US Social Casino Drops", emoji="🔀"),
            discord.SelectOption(label="Shuffle.com", description="Shuffle.com Crypto Casino Drops", emoji="🟣"),
            discord.SelectOption(label="Rainbet", description="Rainbet Instant Bonus Drops", emoji="🌧️"),
            discord.SelectOption(label="Degen", description="Degen Drops with Media Attachments", emoji="🔥"),
            discord.SelectOption(label="Qzino", description="Qzino AI Promotions", emoji="🎲"),
            discord.SelectOption(label="Goated", description="Goated VIP Drops", emoji="🐐"),
            discord.SelectOption(label="THRILL", description="THRILL Platform Drops", emoji="🎢"),
            discord.SelectOption(label="WINNA", description="WINNA Platform Drops", emoji="🏆"),
            discord.SelectOption(label="Stake.us & Stake.com", description="Dual Stake Combined Routing", emoji="🎰"),
            discord.SelectOption(label="Default", description="Default / Global Fallback Route", emoji="🌐"),
        ]
        super().__init__(
            placeholder="🎯 Step 1: Select Platform(s) to Configure...",
            min_values=1,
            max_values=len(options),
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_platforms = self.values
        selected_str = ", ".join(self.values)
        await interaction.response.send_message(
            f"🎯 Selected **{len(self.values)} Platform(s)**: `{selected_str}`\n"
            f"👉 Now choose an action from **Step 2: Action Dropdown** below to add/remove channels or webhooks.",
            ephemeral=True
        )


class GrantAccessModal(discord.ui.Modal):
    def __init__(self, manager: DashboardManager, view: "DashboardView"):
        super().__init__(title="Grant Dashboard Access")
        self.manager = manager
        self.parent_view = view

        self.user_input = discord.ui.TextInput(
            label="User ID or Username",
            placeholder="e.g. 123456789012345678 or traystrees50",
            required=True,
            max_length=100,
            style=discord.TextStyle.short
        )
        self.note_input = discord.ui.TextInput(
            label="Note (optional)",
            placeholder="e.g. Paid subscriber, friend, etc.",
            required=False,
            max_length=200,
            style=discord.TextStyle.short
        )
        self.duration_select = discord.ui.Select(
            placeholder="Select access duration...",
            options=[
                discord.SelectOption(label="Lifetime Access", value="lifetime", description="Permanent access", emoji="∞"),
                discord.SelectOption(label="1 Month (30 days)", value="1month", description="Expires in 30 days", emoji="📅"),
                discord.SelectOption(label="7 Days", value="7days", description="Expires in 7 days", emoji="⏰"),
            ],
            custom_id="grant_duration_select"
        )
        self.add_item(self.user_input)
        self.add_item(self.note_input)
        self.add_item(self.duration_select)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.user_input.value.strip()
        note = self.note_input.value.strip() or "Granted by admin"

        user_id = None
        if raw.isdigit():
            user_id = int(raw)
        else:
            user_id = raw

        duration = self.duration_select.values[0] if self.duration_select.values else "lifetime"
        self.manager.add_subscriber(user_id, note=note, role="subscriber", duration=duration)
        new_embed = create_dashboard_embed(self.manager, interaction.client, None)
        await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
        await interaction.followup.send(
            f"✅ Granted full dashboard access to `{user_id}` ({note}) — Duration: **{duration}**.",
            ephemeral=True
        )
class RevokeAccessModal(discord.ui.Modal):
    def __init__(self, manager: DashboardManager, view: "DashboardView"):
        super().__init__(title="Revoke Dashboard Access")
        self.manager = manager
        self.parent_view = view
        self.user_input = discord.ui.TextInput(
            label="Subscriber User ID",
            placeholder="e.g. 123456789012345678",
            required=True,
            max_length=100,
            style=discord.TextStyle.short
        )
        self.add_item(self.user_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.user_input.value.strip()
        user_id = int(raw) if raw.isdigit() else raw
        removed = self.manager.remove_subscriber(user_id)
        new_embed = create_dashboard_embed(self.manager, interaction.client, None)
        await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
        message = f"✅ Revoked dashboard access from `{user_id}`." if removed else f"❌ `{user_id}` is not an active subscriber or is the owner."
        await interaction.followup.send(message, ephemeral=True)


class ManualPostModal(discord.ui.Modal):
    def __init__(self, platforms: List[str], manager: DashboardManager, bot: commands.Bot, subscriber_uid: Optional[str] = None):
        super().__init__(title="Manual Post - Paste Event / Message")
        self.platforms = platforms
        self.manager = manager
        self.bot = bot
        self.subscriber_uid = subscriber_uid
        self.message_input = discord.ui.TextInput(
            label="Paste Event or Post Text",
            placeholder="Paste the event text or message to dispatch.",
            required=True,
            max_length=2000,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        content = self.message_input.value.strip()
        if not content:
            await interaction.response.send_message("No post content was provided.", ephemeral=True)
            return
        notifier = DiscordNotifier(dashboard_manager=self.manager, bot_client=self.bot)
        sent_any = False
        for platform_name in self.platforms:
            platform = Platform.from_str(platform_name)
            if platform == Platform.UNKNOWN:
                continue
            if notifier.send_raw_message(platform, content, subscriber_uid=self.subscriber_uid):
                sent_any = True
        message = "Manual post dispatched." if sent_any else "No personal routes are configured for the selected platform(s)."
        await interaction.response.send_message(message, ephemeral=True)


class ActionSelect(discord.ui.Select):
    """
    Step 2: Action dropdown to add, remove, test, or clear channel IDs and webhooks for selected platforms,
    and manage monitored drop sources.
    """
    def __init__(self):
        options = [
            discord.SelectOption(label="Add Channel ID(s)", value="add_channel", description="Add 1 or more text channel IDs to selected platform(s)", emoji="➕"),
            discord.SelectOption(label="Remove Channel ID", value="remove_channel", description="Remove a specific channel ID from selected platform(s)", emoji="➖"),
            discord.SelectOption(label="Fast-Bind Current Channel", value="bind_current", description="Bind this current Discord channel to selected platform(s)", emoji="📢"),
            discord.SelectOption(label="Add Webhook URL(s)", value="add_webhook", description="Add 1 or more webhook URLs to selected platform(s)", emoji="🔗"),
            discord.SelectOption(label="Remove Webhook URL", value="remove_webhook", description="Remove a webhook URL from selected platform(s)", emoji="✂️"),
            discord.SelectOption(label="Add Monitored Source", value="add_source", description="Add a new Telegram channel or Web Review URL to monitor", emoji="📡"),
            discord.SelectOption(label="Remove Custom Source", value="remove_source", description="Remove a custom Telegram channel or Web Review URL", emoji="🗑️"),
            discord.SelectOption(label="View All Active Sources", value="view_sources", description="Display all monitored Telegram channels, web feeds & APIs", emoji="📋"),
            discord.SelectOption(label="Make Manual Post", value="manual_post", description="Broadcast a raw event/post to selected platform channels", emoji="📝"),
            discord.SelectOption(label="Test Route Dispatch", value="test_route", description="Send test drop embed to all routes for selected platform(s)", emoji="🧪"),
            discord.SelectOption(label="Clear All Channels", value="clear_channels", description="Remove all channel IDs for selected platform(s)", emoji="🧹"),
            discord.SelectOption(label="Clear All Webhooks", value="clear_webhooks", description="Remove all webhook URLs for selected platform(s)", emoji="🧹"),
            discord.SelectOption(label="Reset All Routes", value="clear_all", description="Wipe both channels & webhooks for selected platform(s)", emoji="🗑️"),
            discord.SelectOption(label="Grant Access", value="grant_access", description="Grant full dashboard access to a user by ID or username", emoji="🔑"),
            discord.SelectOption(label="Revoke Access", value="revoke_access", description="Remove a subscriber's dashboard access by user ID", emoji="🔒"),
                discord.SelectOption(label="List Subscribers", value="list_subscribers", description="View active subscribers and expiration details", emoji="👥"),
        ]
        super().__init__(
            placeholder="⚙️ Step 2: Choose Routing or Source Action for Selected Platform(s)...",
            min_values=1,
            max_values=1,
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        selected_platforms = getattr(self.view, "selected_platforms", ["Stake.us"])
        manager = self.view.manager
        uid = str(interaction.user.id)
        is_owner = manager.is_owner(uid)

        if action == "add_channel":
            modal = AddChannelModal(selected_platforms, manager, self.view, subscriber_uid=None if is_owner else uid)
            await interaction.response.send_modal(modal)
        elif action == "remove_channel":
            modal = RemoveChannelModal(selected_platforms, manager, self.view, subscriber_uid=None if is_owner else uid)
            await interaction.response.send_modal(modal)
        elif action == "bind_current":
            channel_id = interaction.channel_id
            if is_owner:
                for plat in selected_platforms:
                    manager.add_channel(plat, channel_id)
            else:
                for plat in selected_platforms:
                    manager.add_subscriber_channel(uid, plat, channel_id)
                if interaction.guild_id is not None:
                    manager.set_subscriber_guild(uid, interaction.guild_id)
            new_embed = create_dashboard_embed(manager, interaction.client, None if is_owner else uid)
            await interaction.response.edit_message(embeds=new_embed, view=self.view)
            await interaction.followup.send(
                f"✅ Bound current channel <#{channel_id}> to **{', '.join(selected_platforms)}**!",
                ephemeral=True
            )
        elif action == "add_webhook":
            modal = AddWebhookModal(selected_platforms, manager, self.view, subscriber_uid=None if is_owner else uid)
            await interaction.response.send_modal(modal)
        elif action == "remove_webhook":
            modal = RemoveWebhookModal(selected_platforms, manager, self.view, subscriber_uid=None if is_owner else uid)
            await interaction.response.send_modal(modal)
        elif action == "add_source":
            if not is_owner:
                await interaction.response.send_message(
                    "Source management is owner-controlled so one subscriber cannot change monitoring for others.",
                    ephemeral=True
                )
                return
            modal = AddSourceModal(
                manager,
                self.view,
                selected_platforms[0] if selected_platforms else None,
                subscriber_uid=None if is_owner else uid
            )
            await interaction.response.send_modal(modal)
        elif action == "remove_source":
            if not is_owner:
                await interaction.response.send_message(
                    "Source management is owner-controlled so one subscriber cannot change monitoring for others.",
                    ephemeral=True
                )
                return
            modal = RemoveSourceModal(manager, self.view, subscriber_uid=None if is_owner else uid)
            await interaction.response.send_modal(modal)
        elif action == "view_sources":
            embed = create_sources_embed(manager)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif action == "manual_post":
            if not selected_platforms:
                await interaction.response.send_message("❌ Please select at least one platform first.", ephemeral=True)
                return
            modal = ManualPostModal(selected_platforms, manager, interaction.client, None if is_owner else uid)
            await interaction.response.send_modal(modal)
        elif action == "test_route":
            await interaction.response.defer(ephemeral=True)
            notifier = DiscordNotifier(dashboard_manager=manager, bot_client=interaction.client)
            sent_count = 0
            for plat_name in selected_platforms:
                plat_enum = Platform.from_str(plat_name)
                test_item = SAMPLE_TEST_ITEMS.get(plat_enum) or SAMPLE_TEST_ITEMS[Platform.STAKE_US]
                if notifier.send_notification(test_item, subscriber_uid=None if is_owner else uid):
                    sent_count += 1
            await interaction.followup.send(
                f"🧪 Test notification dispatched for **{sent_count} / {len(selected_platforms)} platform(s)** across all configured channels and webhooks!",
                ephemeral=True
            )
        elif action == "clear_channels":
            for plat in selected_platforms:
                if is_owner:
                    manager.clear_channels(plat)
                else:
                    manager.clear_subscriber_channels(uid, plat)
            new_embed = create_dashboard_embed(manager, interaction.client, None if is_owner else uid)
            await interaction.response.edit_message(embeds=new_embed, view=self.view)
            await interaction.followup.send(f"🗑️ Cleared all channels for **{', '.join(selected_platforms)}**.", ephemeral=True)
        elif action == "clear_webhooks":
            if is_owner:
                for plat in selected_platforms:
                    manager.clear_webhooks(plat)
            else:
                for plat in selected_platforms:
                    manager.clear_subscriber_webhooks(uid, plat)
            new_embed = create_dashboard_embed(manager, interaction.client, None if is_owner else uid)
            await interaction.response.edit_message(embeds=new_embed, view=self.view)
            await interaction.followup.send(f"🗑️ Cleared all webhooks for **{', '.join(selected_platforms)}**.", ephemeral=True)
        elif action == "clear_all":
            if is_owner:
                for plat in selected_platforms:
                    manager.clear_routes(plat)
            else:
                for plat in selected_platforms:
                    manager.clear_subscriber_channels(uid, plat)
                    manager.clear_subscriber_webhooks(uid, plat)
            new_embed = create_dashboard_embed(manager, interaction.client, None if is_owner else uid)
            await interaction.response.edit_message(embeds=new_embed, view=self.view)
            await interaction.followup.send(f"🧹 Reset all routes for **{', '.join(selected_platforms)}**.", ephemeral=True)
        elif action == "grant_access":
            if not _has_admin_access(interaction.user) and not manager.is_owner(interaction.user.id):
                await interaction.response.send_message("❌ Only the project owner or server admins can grant access.", ephemeral=True)
                return
            modal = GrantAccessModal(manager, self.view)
            await interaction.response.send_modal(modal)
        elif action == "list_subscribers":
            if not _has_admin_access(interaction.user) and not manager.is_owner(interaction.user.id):
                await interaction.response.send_message("❌ Only the project owner or server admins can view subscribers.", ephemeral=True)
                return
            subscribers = manager.get_subscribers()
            embed = discord.Embed(
                title=f"👥 {BOT_NAME} - Active Subscribers",
                description="Dashboard access and expiration details.",
                color=0x1475E1
            )
            for subscriber_id, data in subscribers.items():
                status = "ACTIVE" if data.get("active", False) else "INACTIVE"
                embed.add_field(
                    name=f"<@{subscriber_id}> ({subscriber_id})",
                    value=(
                        f"**Status:** {status}\n"
                        f"**Duration:** {data.get('duration', 'lifetime')}\n"
                        f"**Expires:** {data.get('expires_at') or 'Never'}\n"
                        f"**Note:** {data.get('note', '')}"
                    ),
                    inline=False
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif action == "revoke_access":
            if not _has_admin_access(interaction.user) and not manager.is_owner(interaction.user.id):
                await interaction.response.send_message("❌ Only the project owner or server admins can revoke access.", ephemeral=True)
                return
            await interaction.response.send_modal(RevokeAccessModal(manager, self.view))


class DashboardView(discord.ui.View):
    """
    Interactive Enterprise Control Panel View featuring Multi-Select Platform Dropdown,
    Action Dropdown, and Quick Action buttons.
    """
    def __init__(self, manager: DashboardManager, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.selected_platforms: List[str] = ["Stake.us"]
        self.subscriber_uid: Optional[str] = None
        self.add_item(PlatformMultiSelect())
        self.add_item(ActionSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.manager.is_authorized(interaction.user.id) and not _has_admin_access(interaction.user):
            embed = create_unauthorized_embed()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        uid = str(interaction.user.id)
        self.subscriber_uid = None if self.manager.is_owner(uid) else uid
        return True

    @discord.ui.button(label="⚡ Toggle Monitor", style=discord.ButtonStyle.success, row=2, emoji="🟢")
    async def btn_toggle_monitor(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.subscriber_uid:
            await interaction.response.send_message(
                "Monitoring is managed by the bot owner. Your subscriber dashboard controls personal routes only.",
                ephemeral=True
            )
            return
        current = self.manager.get_setting("realtime_monitoring_enabled", True)
        new_state = not current
        self.manager.set_setting("realtime_monitoring_enabled", new_state)

        if hasattr(interaction.client, "background_monitor_task"):
            if new_state and not interaction.client.background_monitor_task.is_running():
                interaction.client.background_monitor_task.start()
            elif not new_state and interaction.client.background_monitor_task.is_running():
                interaction.client.background_monitor_task.cancel()

        new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
        await interaction.response.edit_message(embeds=new_embed, view=self)
        state_str = "ENABLED 🟢" if new_state else "PAUSED 🔴"
        await interaction.followup.send(f"Real-time monitoring is now **{state_str}**.", ephemeral=True)

    @discord.ui.button(label="⏱️ Interval", style=discord.ButtonStyle.secondary, row=2, emoji="⚙️")
    async def btn_set_interval(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.subscriber_uid:
            await interaction.response.send_message(
                "Polling interval is managed by the bot owner. Your personal routes remain independent.",
                ephemeral=True
            )
            return
        modal = IntervalModal(self.manager, self, self.subscriber_uid)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📡 Sources", style=discord.ButtonStyle.secondary, row=2, emoji="📡")
    async def btn_sources(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = create_sources_embed(self.manager)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🩺 Health", style=discord.ButtonStyle.secondary, row=3, emoji="🩺")
    async def btn_health(self, interaction: discord.Interaction, button: discord.ui.Button):
        health_mon = HealthMonitor(dashboard_manager=self.manager)
        embed = health_mon.create_health_embed(interaction.client)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="➕ Add Source", style=discord.ButtonStyle.primary, row=3, emoji="➕")
    async def btn_add_source(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.subscriber_uid:
            await interaction.response.send_message(
                "Source management is owner-controlled so one subscriber cannot change monitoring for others.",
                ephemeral=True
            )
            return
        selected_platforms = getattr(self, "selected_platforms", ["Stake.us"])
        modal = AddSourceModal(
            self.manager,
            self,
            selected_platforms[0] if selected_platforms else None,
            self.subscriber_uid
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, row=3)
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
        await interaction.response.edit_message(embeds=new_embed, view=self)

    @discord.ui.button(label="📝 Submitted Codes", style=discord.ButtonStyle.primary, row=3, emoji="📝")
    async def btn_submitted_codes(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Opens the submitted-codes routing settings panel."""
        modal = SubmittedCodesRoutingModal(self.manager, self, self.subscriber_uid)
        await interaction.response.send_modal(modal)


# ----------------------------------------------------
# Submitted Codes Routing Settings
# ----------------------------------------------------
class SubmittedCodesRoutingModal(discord.ui.Modal):
    """Modal for configuring where manually submitted codes get sent."""
    def __init__(self, manager: DashboardManager, parent_view, subscriber_uid: Optional[str] = None):
        super().__init__(title="📝 Submitted Codes Routing")
        self.manager = manager
        self.parent_view = parent_view
        self.subscriber_uid = subscriber_uid

        self.platform_select = discord.ui.Select(
            label="Target Platform",
            placeholder="Select platform for submitted codes",
            options=[
                discord.SelectOption(label="Stake.us", value="Stake.us"),
                discord.SelectOption(label="Stake.com", value="Stake.com"),
                discord.SelectOption(label="Shuffle.us", value="Shuffle.us"),
                discord.SelectOption(label="Shuffle.com", value="Shuffle.com"),
                discord.SelectOption(label="Qzino", value="Qzino"),
                discord.SelectOption(label="Rainbet", value="Rainbet"),
                discord.SelectOption(label="Degen", value="Degen"),
                discord.SelectOption(label="Goated", value="Goated"),
                discord.SelectOption(label="Dual Stake", value="Dual Stake"),
            ],
            row=0
        )
        self.platform_select.callback = self._on_platform_select
        self.add_item(self.platform_select)

        self.channel_input = discord.ui.TextInput(
            label="Channel ID (optional)",
            placeholder="Discord channel ID where submitted codes should be posted",
            required=False,
            max_length=20,
            style=discord.TextStyle.short
        )
        self.add_item(self.channel_input)

        self.webhook_input = discord.ui.TextInput(
            label="Webhook URL (optional)",
            placeholder="Discord webhook URL for submitted codes",
            required=False,
            max_length=200,
            style=discord.TextStyle.short
        )
        self.add_item(self.webhook_input)

    async def _on_platform_select(self, interaction: discord.Interaction):
        self.selected_platform = self.platform_select.values[0] if self.platform_select.values else None

    async def on_submit(self, interaction: discord.Interaction):
        platform = getattr(self, "selected_platform", None) or "Stake.us"
        channel_id = self.channel_input.value.strip() if self.channel_input.value else None
        webhook_url = self.webhook_input.value.strip() if self.webhook_input.value else None

        if self.subscriber_uid:
            if channel_id and channel_id.isdigit():
                self.manager.add_subscriber_channel(self.subscriber_uid, platform, int(channel_id))
            if webhook_url:
                self.manager.add_subscriber_webhook(self.subscriber_uid, platform, webhook_url)
        else:
            if channel_id and channel_id.isdigit():
                self.manager.set_channel(platform, int(channel_id))
            if webhook_url:
                self.manager.set_webhook(platform, webhook_url)

        await interaction.response.send_message(
            f"✅ Submitted codes routing updated for **{platform}**:\n"
            f"  • Channel: `{channel_id or 'unchanged'}`\n"
            f"  • Webhook: `{webhook_url[:30] + '...' if webhook_url and len(webhook_url) > 30 else webhook_url or 'unchanged'}`",
            ephemeral=True
        )


# ----------------------------------------------------
# Embed Editor Dashboard
# ----------------------------------------------------
class EditTitleModal(discord.ui.Modal):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], parent_view: "EmbedEditorView"):
        super().__init__(title="Edit Embed Title")
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.parent_view = parent_view

        self.title_input = discord.ui.TextInput(
            label="Embed Title",
            placeholder="Enter embed title...",
            required=True,
            max_length=256,
            style=discord.TextStyle.short,
            default=self.template.get("title", "")
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.template["title"] = self.title_input.value.strip()
        embed = self.parent_view.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        await interaction.followup.send("✅ Title updated.", ephemeral=True)


class EditDescriptionModal(discord.ui.Modal):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], parent_view: "EmbedEditorView"):
        super().__init__(title="Edit Embed Description")
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.parent_view = parent_view

        self.desc_input = discord.ui.TextInput(
            label="Embed Description",
            placeholder="Enter embed description...",
            required=False,
            max_length=4096,
            style=discord.TextStyle.paragraph,
            default=self.template.get("description", "")
        )
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.template["description"] = self.desc_input.value.strip()
        embed = self.parent_view.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        await interaction.followup.send("✅ Description updated.", ephemeral=True)


class EditColorModal(discord.ui.Modal):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], parent_view: "EmbedEditorView"):
        super().__init__(title="Edit Embed Color (Hex)")
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.parent_view = parent_view

        self.color_input = discord.ui.TextInput(
            label="Hex Color Code",
            placeholder="#FF1493",
            required=True,
            max_length=7,
            style=discord.TextStyle.short,
            default=self.template.get("color", "#5865F2")
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.color_input.value.strip()
        if not val.startswith("#"):
            val = "#" + val
        if len(val) != 7:
            await interaction.response.send_message("❌ Invalid hex color. Use format #RRGGBB.", ephemeral=True)
            return
        self.template["color"] = val.upper()
        embed = self.parent_view.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        await interaction.followup.send(f"✅ Color updated to `{val}`.", ephemeral=True)


class EditThumbnailModal(discord.ui.Modal):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], parent_view: "EmbedEditorView"):
        super().__init__(title="Edit Thumbnail URL")
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.parent_view = parent_view

        self.url_input = discord.ui.TextInput(
            label="Thumbnail Image URL",
            placeholder="https://example.com/image.png",
            required=False,
            max_length=400,
            style=discord.TextStyle.short,
            default=self.template.get("thumbnail_url", "")
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.template["thumbnail_url"] = self.url_input.value.strip()
        embed = self.parent_view.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        await interaction.followup.send("✅ Thumbnail URL updated.", ephemeral=True)


class EditImageModal(discord.ui.Modal):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], parent_view: "EmbedEditorView"):
        super().__init__(title="Edit Image URL")
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.parent_view = parent_view

        self.url_input = discord.ui.TextInput(
            label="Embed Image URL",
            placeholder="https://example.com/image.png",
            required=False,
            max_length=400,
            style=discord.TextStyle.short,
            default=self.template.get("image_url", "")
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.template["image_url"] = self.url_input.value.strip()
        embed = self.parent_view.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        await interaction.followup.send("✅ Image URL updated.", ephemeral=True)


class EditFooterModal(discord.ui.Modal):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], parent_view: "EmbedEditorView"):
        super().__init__(title="Edit Footer")
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.parent_view = parent_view

        self.text_input = discord.ui.TextInput(
            label="Footer Text",
            placeholder="Footer text...",
            required=False,
            max_length=2048,
            style=discord.TextStyle.paragraph,
            default=self.template.get("footer_text", "")
        )
        self.icon_input = discord.ui.TextInput(
            label="Footer Icon URL",
            placeholder="https://example.com/icon.png",
            required=False,
            max_length=400,
            style=discord.TextStyle.short,
            default=self.template.get("footer_icon", "")
        )
        self.add_item(self.text_input)
        self.add_item(self.icon_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.template["footer_text"] = self.text_input.value.strip()
        self.template["footer_icon"] = self.icon_input.value.strip()
        embed = self.parent_view.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        await interaction.followup.send("✅ Footer updated.", ephemeral=True)


class EditAuthorModal(discord.ui.Modal):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], parent_view: "EmbedEditorView"):
        super().__init__(title="Edit Author")
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.parent_view = parent_view

        self.name_input = discord.ui.TextInput(
            label="Author Name",
            placeholder="Author name...",
            required=False,
            max_length=256,
            style=discord.TextStyle.short,
            default=self.template.get("author_name", "")
        )
        self.icon_input = discord.ui.TextInput(
            label="Author Icon URL",
            placeholder="https://example.com/icon.png",
            required=False,
            max_length=400,
            style=discord.TextStyle.short,
            default=self.template.get("author_icon", "")
        )
        self.add_item(self.name_input)
        self.add_item(self.icon_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.template["author_name"] = self.name_input.value.strip()
        self.template["author_icon"] = self.icon_input.value.strip()
        embed = self.parent_view.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        await interaction.followup.send("✅ Author updated.", ephemeral=True)


class AddFieldModal(discord.ui.Modal):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], parent_view: "EmbedEditorView"):
        super().__init__(title="Add New Field")
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.parent_view = parent_view

        self.name_input = discord.ui.TextInput(
            label="Field Name",
            placeholder="Field name...",
            required=True,
            max_length=256,
            style=discord.TextStyle.short
        )
        self.value_input = discord.ui.TextInput(
            label="Field Value",
            placeholder="Field value...",
            required=True,
            max_length=1024,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.name_input)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        fields = self.template.get("fields", [])
        fields.append({
            "name": self.name_input.value.strip(),
            "value": self.value_input.value.strip(),
            "inline": False
        })
        self.template["fields"] = fields
        embed = self.parent_view.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        await interaction.followup.send("✅ Field added.", ephemeral=True)


class EditFieldModal(discord.ui.Modal):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], field_index: int, parent_view: "EmbedEditorView"):
        super().__init__(title=f"Edit Field #{field_index + 1}")
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.field_index = field_index
        self.parent_view = parent_view

        field = template.get("fields", [])[field_index] if field_index < len(template.get("fields", [])) else {}
        self.name_input = discord.ui.TextInput(
            label="Field Name",
            placeholder="Field name...",
            required=True,
            max_length=256,
            style=discord.TextStyle.short,
            default=field.get("name", "")
        )
        self.value_input = discord.ui.TextInput(
            label="Field Value",
            placeholder="Field value...",
            required=True,
            max_length=1024,
            style=discord.TextStyle.paragraph,
            default=field.get("value", "")
        )
        self.add_item(self.name_input)
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        fields = self.template.get("fields", [])
        if 0 <= self.field_index < len(fields):
            fields[self.field_index]["name"] = self.name_input.value.strip()
            fields[self.field_index]["value"] = self.value_input.value.strip()
            self.template["fields"] = fields
            embed = self.parent_view.get_preview_embed()
            await interaction.response.edit_message(embed=embed, view=self.parent_view)
            await interaction.followup.send("✅ Field updated.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Invalid field index.", ephemeral=True)


class FieldsManageView(discord.ui.View):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, template: Dict[str, Any], parent_view: "EmbedEditorView"):
        super().__init__(timeout=600)
        self.template_manager = template_manager
        self.platform = platform
        self.template = template
        self.parent_view = parent_view

        self.field_select = discord.ui.Select(
            placeholder="Select a field to edit or remove...",
            min_values=1,
            max_values=1,
            row=0
        )
        self.field_select.callback = self._on_field_select
        self.add_item(self.field_select)
        self._refresh_field_options()

    def _refresh_field_options(self):
        self.field_select.options = []
        fields = self.template.get("fields", [])
        for idx, field in enumerate(fields):
            label = field.get("name", f"Field {idx+1}")[:100]
            desc = field.get("value", "")[:100]
            self.field_select.add_option(
                label=f"#{idx+1} {label}",
                description=desc,
                value=str(idx)
            )
        if not fields:
            self.field_select.add_option(label="No fields configured", value="-1")

    @discord.ui.button(label="➕ Add Field", style=discord.ButtonStyle.primary, row=1)
    async def btn_add_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddFieldModal(self.template_manager, self.platform, self.template, self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🗑️ Remove Selected", style=discord.ButtonStyle.danger, row=1)
    async def btn_remove_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        idx = int(self.field_select.values[0]) if self.field_select.values else -1
        fields = self.template.get("fields", [])
        if 0 <= idx < len(fields):
            fields.pop(idx)
            self.template["fields"] = fields
            self._refresh_field_options()
            embed = self.parent_view.get_preview_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send("✅ Field removed.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No valid field selected.", ephemeral=True)

    @discord.ui.button(label="✏️ Edit Selected", style=discord.ButtonStyle.secondary, row=1)
    async def btn_edit_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        idx = int(self.field_select.values[0]) if self.field_select.values else -1
        fields = self.template.get("fields", [])
        if 0 <= idx < len(fields):
            modal = EditFieldModal(self.template_manager, self.platform, self.template, idx, self.parent_view)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("❌ No valid field selected.", ephemeral=True)

    @discord.ui.button(label="🔙 Back", style=discord.ButtonStyle.secondary, row=2)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.parent_view.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

    async def _on_field_select(self, interaction: discord.Interaction):
        await interaction.response.defer()


class EmbedEditorPlatformSelect(discord.ui.Select):
    def __init__(self, template_manager: EmbedTemplateManager, parent_view: "EmbedEditorPlatformSelectView"):
        options = []
        for plat_name in template_manager.get_all_platforms():
            try:
                plat = Platform.from_str(plat_name)
                emoji = plat.emoji.split()[0] if plat != Platform.UNKNOWN else "🎁"
            except Exception:
                emoji = "🎁"
            options.append(discord.SelectOption(
                label=plat_name,
                description=f"Edit embed template for {plat_name}",
                emoji=emoji
            ))
        super().__init__(
            placeholder="🎯 Select a platform to edit...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )
        self.template_manager = template_manager
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        platform = self.values[0]
        self.parent_view.selected_platform = platform
        view = EmbedEditorView(self.template_manager, platform, interaction)
        embed = view.get_preview_embed()
        embed.description = f"Editing embed template for **{platform}**\nUse the buttons below to edit each component."
        await interaction.response.edit_message(embed=embed, view=view)


class EmbedEditorPlatformSelectView(discord.ui.View):
    def __init__(self, template_manager: EmbedTemplateManager, interaction: discord.Interaction):
        super().__init__(timeout=600)
        self.template_manager = template_manager
        self.interaction = interaction
        self.selected_platform: Optional[str] = None
        self.add_item(EmbedEditorPlatformSelect(template_manager, self))


class EmbedEditorView(discord.ui.View):
    def __init__(self, template_manager: EmbedTemplateManager, platform: str, interaction: discord.Interaction):
        super().__init__(timeout=600)
        self.template_manager = template_manager
        self.platform = platform
        self.template = template_manager.get_template(platform)
        self.original_template = copy.deepcopy(self.template)
        self.interaction = interaction

    def get_preview_embed(self) -> discord.Embed:
        embed_dict = self.template_manager.template_to_embed_dict(self.template)
        embed = discord.Embed.from_dict(embed_dict)
        embed.set_footer(text=f"{BOT_NAME} • Embed Editor", icon_url=BOT_AVATAR_URL)
        return embed

    @discord.ui.button(label="✏️ Title", style=discord.ButtonStyle.secondary, row=1)
    async def btn_edit_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditTitleModal(self.template_manager, self.platform, self.template, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📝 Description", style=discord.ButtonStyle.secondary, row=1)
    async def btn_edit_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditDescriptionModal(self.template_manager, self.platform, self.template, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🎨 Color", style=discord.ButtonStyle.secondary, row=1)
    async def btn_edit_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditColorModal(self.template_manager, self.platform, self.template, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🖼️ Thumbnail", style=discord.ButtonStyle.secondary, row=1)
    async def btn_edit_thumb(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditThumbnailModal(self.template_manager, self.platform, self.template, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📷 Image", style=discord.ButtonStyle.secondary, row=1)
    async def btn_edit_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditImageModal(self.template_manager, self.platform, self.template, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📋 Footer", style=discord.ButtonStyle.secondary, row=1)
    async def btn_edit_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditFooterModal(self.template_manager, self.platform, self.template, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="👤 Author", style=discord.ButtonStyle.secondary, row=1)
    async def btn_edit_author(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditAuthorModal(self.template_manager, self.platform, self.template, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📚 Fields", style=discord.ButtonStyle.primary, row=2)
    async def btn_edit_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = FieldsManageView(self.template_manager, self.platform, self.template, self)
        embed = self.get_preview_embed()
        embed.description = f"Editing **{len(self.template.get('fields', []))}** fields for **{self.platform}**\nSelect a field below, then add/remove/edit."
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🧪 Post Test", style=discord.ButtonStyle.success, row=2)
    async def btn_post_test(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        success, msg = post_test_embed(self.interaction.client, self.template)
        if success:
            await interaction.followup.send(f"✅ Test embed posted! ({msg})", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ Failed to post: {msg}", ephemeral=True)

    @discord.ui.button(label="🔄 Reset", style=discord.ButtonStyle.danger, row=2)
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        from datetime import datetime, timezone
        from models import Platform as Plat
        plat_enum = Plat.from_str(self.platform)
        if plat_enum == Plat.UNKNOWN:
            await interaction.response.send_message("❌ Cannot reset unknown platform.", ephemeral=True)
            return
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        item = BonusCodeItem(
            code="RESET_TEST",
            platform=plat_enum,
            amount_value="Reset Template",
            wager_requirement="N/A",
            source_url="",
            source_name="Template Reset",
            is_affiliate=False,
            detected_at=now
        )
        self.template = self.template_manager.reset_template(self.platform, item)
        self.original_template = copy.deepcopy(self.template)
        embed = self.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("🔄 Template reset to default.", ephemeral=True)

    @discord.ui.button(label="💾 Save", style=discord.ButtonStyle.success, row=2)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.template_manager.update_template(self.platform, self.template)
        self.original_template = copy.deepcopy(self.template)
        embed = self.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("✅ Template saved.", ephemeral=True)

    @discord.ui.button(label="❌ Discard", style=discord.ButtonStyle.secondary, row=2)
    async def btn_discard(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.template = copy.deepcopy(self.original_template)
        embed = self.get_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("🗑️ Changes discarded.", ephemeral=True)


def post_test_embed(bot_client, template: Dict[str, Any]) -> tuple:
    manager = EmbedTemplateManager()
    embed_dict = manager.template_to_embed_dict(template)
    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_AVATAR_URL,
        "embeds": [embed_dict]
    }
    webhook_url = "https://discord.com/api/webhooks/1544995568810594328/-tHKfVnEUJow2BjIVdCsXa0J5s4QF5GONMXdKYzW4vg27CwJRBj3rSEHqOeXcdXNa8Bz"
    try:
        import requests
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in [200, 204]:
            return True, "webhook"
    except Exception as e:
        logger.error(f"Webhook test post failed: {e}")

    channel_id = 1460666123484794880
    if bot_client and not bot_client.is_closed():
        try:
            import asyncio
            import discord
            async def _send():
                channel = bot_client.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await bot_client.fetch_channel(channel_id)
                    except Exception:
                        return False
                if channel:
                    emb = discord.Embed.from_dict(embed_dict)
                    await channel.send(embed=emb)
                    return True
                return False
            try:
                loop = getattr(bot_client, "loop", None)
                if loop and loop.is_running():
                    fut = asyncio.run_coroutine_threadsafe(_send(), loop)
                    result = fut.result(timeout=15)
                    if result:
                        return True, "channel"
            except Exception as e:
                logger.error(f"Channel test post failed: {e}")
        except Exception:
            pass
    return False, "no route available"


# ----------------------------------------------------
# Main Discord Bot Application Factory
# ----------------------------------------------------
def run_discord_bot():
    """
    Launches the Leaked.GG Discord bot client with interactive dashboard controls,
    health monitor, /activecodes poller, and background sweep daemon.
    """
    if not DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN is not configured in .env or environment variables!")
        print("❌ Error: DISCORD_BOT_TOKEN is missing in .env. Please set it before starting the bot.")
        return

    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(
        command_prefix="!",
        intents=intents,
        help_command=None,
        heartbeat_timeout=120,
        max_messages=50,
    )
    manager = DashboardManager()
    tracker = CodeTracker()
    notifier = DiscordNotifier(dashboard_manager=manager, bot_client=bot)
    code_validator = StakeCodeValidator()
    engine = ScraperEngine(tracker=tracker, notifier=notifier, code_validator=code_validator)
    poller = StakeStatsPoller()
    health_mon = HealthMonitor(dashboard_manager=manager, tracker=tracker)

    # ----------------------------------------------------
    # Background Daemon Loop
    # ----------------------------------------------------
    import concurrent.futures
    interval_secs = manager.get_setting("check_interval_seconds", CHECK_INTERVAL_SECONDS)
    sweep_timeout = manager.get_setting("sweep_timeout_seconds", 120)
    sweep_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="SweepWorker")
    _sweep_lock = asyncio.Lock()

    @tasks.loop(seconds=interval_secs)
    async def background_monitoring_sweep():
        is_enabled = manager.get_setting("realtime_monitoring_enabled", True)
        if not is_enabled:
            return

        if _sweep_lock.locked():
            logger.debug("Previous background sweep still in progress, skipping overlapping tick.")
            return

        async with _sweep_lock:
            logger.info("Executing scheduled real-time bonus code monitoring sweep...")
            try:
                loop = asyncio.get_running_loop()
                new_codes = await asyncio.wait_for(
                    loop.run_in_executor(sweep_executor, lambda: engine.run_check(notify=True)),
                    timeout=sweep_timeout
                )
                if new_codes:
                    logger.info(f"✅ Realtime sweep dispatched {len(new_codes)} new bonus drops to configured channels/webhooks.")
                else:
                    logger.info("Realtime sweep completed. No new drops detected.")
            except asyncio.TimeoutError:
                logger.warning(f"Background sweep timed out after {sweep_timeout}s, skipping. Discord command responsiveness maintained.")
            except Exception as e:
                logger.error(f"Error during background real-time monitoring loop: {e}", exc_info=True)

    bot.background_monitor_task = background_monitoring_sweep

    # ----------------------------------------------------
    # Bot Lifecycle Events & Slash Command Tree Sync
    # ----------------------------------------------------
    @bot.event
    async def setup_hook():
        logger.info("Synchronizing application slash commands with Discord...")
        try:
            synced = await bot.tree.sync()
            logger.info(f"✅ Successfully synced and pushed {len(synced)} slash commands to Discord globally.")
            print(f" ✅ Pushed {len(synced)} application slash commands to Discord API.", flush=True)
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}", exc_info=True)

    async def _cleanup_old_slash_commands(bot):
        allowed_names = {
            "codes", "activecodes", "activecom", "activecodesus", "livecodes",
            "help", "info", "commands", "links", "subscribe", "dashboard",
            "status", "startmonitor", "embed-editor", "post", "code", "codechecker",
            "admin", "grant", "revoke", "subscribers",
        }
        cleaned = {"global": 0, "guilds": {}}

        try:
            existing_global = await bot.http.get_global_commands(bot.application_id)
            for cmd in existing_global:
                if cmd["name"] not in allowed_names:
                    await bot.http.delete_global_command(bot.application_id, cmd["id"])
                    cleaned["global"] += 1
                    logger.info(f"Removed old global slash command: /{cmd['name']}")
        except Exception as e:
            logger.error(f"Failed to cleanup global commands: {e}")

        for guild in bot.guilds:
            try:
                existing_guild = await bot.http.get_guild_commands(bot.application_id, guild.id)
                for cmd in existing_guild:
                    if cmd["name"] not in allowed_names:
                        await bot.http.delete_guild_command(bot.application_id, guild.id, cmd["id"])
                        cleaned["guilds"][guild.id] = cleaned["guilds"].get(guild.id, 0) + 1
                        logger.info(f"Removed old guild slash command /{cmd['name']} from {guild.name}")
            except Exception as e:
                logger.debug(f"Guild cleanup skipped for {guild.id}: {e}")

        if cleaned["global"] or cleaned["guilds"]:
            logger.info(f"Slash command cleanup complete. Removed {cleaned['global']} global commands and {sum(cleaned['guilds'].values())} guild commands.")

    @bot.event
    async def on_ready():
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Leaked.GG bonus codes | /dashboard"
            )
        )
        logger.info(f"{BOT_NAME} Discord Bot connected as {bot.user} (ID: {bot.user.id})")
        print(f"\n==================================================================", flush=True)
        print(f" ✅ {BOT_NAME} DISCORD BOT IS ONLINE & RUNNING", flush=True)
        print(f" Connected User: {bot.user} (ID: {bot.user.id})", flush=True)
        print(f" Realtime Monitor: {'ENABLED (Every ' + str(interval_secs) + 's)' if manager.get_setting('realtime_monitoring_enabled', True) else 'PAUSED'}", flush=True)
        print(f" Slash Commands: /codes, /codechecker, /help, /info, /commands, /links, /subscribe, /dashboard, /status, /startmonitor, /post, /code, /embed-editor, /admin, /grant, /revoke, /subscribers", flush=True)
        print(f" Prefix Commands: !codes, !codechecker, !checkcode, !cc, !help, !info, !commands, !links, !subscribe, !dashboard, !startmonitor, !status, !post, !code, !grant, !revoke, !subscribers", flush=True)
        print(f"==================================================================\n", flush=True)

        # Full command sync: clear old commands and sync current tree
        try:
            await bot.tree.sync()
            logger.info("Global slash commands synced successfully.")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

        await _cleanup_old_slash_commands(bot)

        # Global sync already covers all servers; skip guild-level sync to avoid duplicate command registration
        logger.info(f"Bot is ready in {len(bot.guilds)} server(s). Global slash commands are active.")

        if manager.get_setting("realtime_monitoring_enabled", True) and not background_monitoring_sweep.is_running():
            background_monitoring_sweep.start()

    @bot.event
    async def on_guild_available(guild):
        logger.info(f"Guild {guild.name} ({guild.id}) is now available/reconnected")

    @bot.event
    async def on_resumed():
        logger.info("Discord gateway connection resumed successfully")
        if manager.get_setting("realtime_monitoring_enabled", True) and not background_monitoring_sweep.is_running():
            background_monitoring_sweep.start()

    @bot.event
    async def on_disconnect():
        logger.warning("Discord gateway disconnected! Attempting to reconnect...")
        if background_monitoring_sweep.is_running():
            background_monitoring_sweep.cancel()

    @bot.event
    async def on_connect():
        logger.info("Discord gateway connected")

    @bot.event
    async def on_error(event, *args, **kwargs):
        logger.error(f"Error in event {event}: {args}", exc_info=True)

    @bot.event
    async def on_command_error(ctx: commands.Context, error: Exception):
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=True)
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏱️ This command is on cooldown. Try again in {error.retry_after:.1f}s.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`", ephemeral=True)
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Invalid argument: {str(error)}", ephemeral=True)
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.", ephemeral=True)
        elif isinstance(error, commands.CommandNotFound):
            pass  # Silently ignore unknown prefix commands
        else:
            await ctx.send("❌ An unexpected error occurred. Check the bot logs.", ephemeral=True)

    @bot.event
    async def on_error(event: str, *args, **kwargs):
        logger.error(f"Unhandled error in {event}", exc_info=True)
        if args and isinstance(args[0], discord.Interaction):
            interaction = args[0]
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An unexpected error occurred. The bot team has been notified.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An unexpected error occurred. The bot team has been notified.",
                        ephemeral=True
                    )
            except Exception:
                pass

    # ----------------------------------------------------
    # Information & Guide Commands (Consolidated)
    # ----------------------------------------------------
    @bot.hybrid_command(
        name="help",
        aliases=["about", "guide"],
        with_app_command=True,
        description="Unified help menu: bot overview, available commands, platform links, and subscription info"
    )
    async def cmd_help(ctx: commands.Context):
        """
        Consolidated help command. Merges /info, /help, /commands, and /links
        into a single unified embed-based menu.
        Usage: /help [section]
        Sections: info, commands, links (default: all)
        """
        embed = discord.Embed(
            title=f"📖 {BOT_NAME} — Enterprise Bot Guide",
            description="Always-On Active Bonus Code & Low Wager Drop Monitoring Engine\n🔒 Admin features require `/subscribe` ($2 crypto) or server admin role.",
            color=0x1475E1
        )
        embed.add_field(
            name="🎁 Public Commands",
            value=(
                "• `/codes` [platform] — Query StakeStats.net for currently active drops.\n"
                "  *Examples:* `/codes` (all), `/codes stake.com`, `/codes stake.us`, `/codes qzino`, `/codes degen`\n"
                "  *Aliases:* `/activecodes`, `/livecodes`, `/activecom`, `/activecodesus`\n"
                "• `/codechecker` — Check a bonus code status (Active/Expired) with instant claim link.\n"
                "  *Prefix:* `!codechecker <code> [platform]` or `!checkcode` or `!cc`\n"
                "• `/info` — Bot overview, supported platforms, and theme palette.\n"
                "• `/help` — Display this unified usage guide.\n"
                "• `/commands` — List all available commands.\n"
                "• `/links` — View all affiliate/signup links for every platform.\n"
                "• `/subscribe` — Unlock full dashboard access for $2 in any crypto.\n"
                "• `/dashboard` — Personal routing dashboard, your server channels, DMs, and webhooks."
            ),
            inline=False
        )
        embed.add_field(
            name="🔒 Admin Commands (Owner / Subscriber / Server Admin)",
            value=(
                "• `/startmonitor` — Start background real-time scanner.\n"
                "• `/status` — View real-time monitor status, interval, and database counts.\n"
                "• `/dashboard` — Full interactive multi-platform control panel.\n"
                "• `/code` or `!code` — Validate and broadcast a bonus code to your authorized routes.\n"
                "• `!post` — Manually broadcast a raw event/post to selected platform channels.\n"
                "• `/embed-editor` — View and edit embed formats for each platform."
            ),
            inline=False
        )
        embed.add_field(
            name="👥 Admin Management (Owner / Server Admin)",
            value=(
                "• `/admin grant <user_id>` — Grant dashboard access to a user.\n"
                "• `/admin revoke <user_id>` — Revoke subscriber dashboard access.\n"
                "• `/admin subscribers` — List all active subscribers with expiration info.\n"
                "• `/admin` — Unified admin management panel."
            ),
            inline=False
        )
        embed.add_field(
            name="💎 Dashboard Access",
            value=(
                "If you're interested in having platform bonus codes broadcasted in your own server "
                "and channels or webhooks, DM <@{OWNER_USER_ID}> and inquire about premium access.\n"
                f"Visit [JOIN DISCORD]({DISCORD_INVITE_URL}) to join the community."
            ),
            inline=False
        )
        embed.set_footer(text=f"{BOT_NAME} Enterprise Monitoring", icon_url=BOT_AVATAR_URL)
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="info", with_app_command=True, description="Bot overview, supported platforms, and theme palette")
    async def cmd_info(ctx: commands.Context):
        """Standalone /info command — bot overview and supported platforms."""
        embed = create_info_embed()
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="commands", with_app_command=True, description="List all available Active Codes commands")
    async def cmd_commands(ctx: commands.Context):
        """Standalone /commands command — lists all available commands."""
        embed = discord.Embed(
            title=f"📋 {BOT_NAME} — Available Commands",
            description="Use `/command` in Discord to execute any of these.\n🔒 Admin-only commands require `/subscribe` ($2 crypto) or server admin role.",
            color=0x1475E1
        )
        embed.add_field(
            name="🎁 Public Commands",
            value=(
                "• `/codes` [platform] — Query StakeStats.net for currently active drops.\n"
                "  *Examples:* `/codes` (all), `/codes stake.com`, `/codes stake.us`, `/codes qzino`, `/codes degen`\n"
                "  *Aliases:* `/activecodes`, `/livecodes`, `/activecom`, `/activecodesus`\n"
                "• `/codechecker` — Check a bonus code status (Active/Expired) with instant claim link.\n"
                "  *Prefix:* `!codechecker <code> [platform]` or `!checkcode` or `!cc`\n"
                "• `/info` — Bot overview, supported platforms, and theme palette.\n"
                "• `/help` — Display this unified usage guide.\n"
                "• `/links` — View all affiliate/signup links for every platform.\n"
                "• `/subscribe` — Unlock full dashboard access for $2 in any crypto.\n"
                "• `/dashboard` — Personal routing dashboard, your server channels, DMs, and webhooks."
            ),
            inline=False
        )
        embed.add_field(
            name="🔒 Admin Commands (Owner / Subscriber / Server Admin)",
            value=(
                "• `/startmonitor` — Start background real-time scanner.\n"
                "• `/status` — View real-time monitor status, interval, and database counts.\n"
                "• `/dashboard` — Full interactive multi-platform control panel.\n"
                "• `/code` or `!code` — Validate and broadcast a bonus code to authorized routes.\n"
                "• `!post` — Manually broadcast a raw event/post to selected platform channels.\n"
                "• `/embed-editor` — View and edit embed formats for each platform."
            ),
            inline=False
        )
        embed.add_field(
            name="👥 Admin Management (Owner / Server Admin)",
            value=(
                "• `/admin grant <user_id>` — Grant dashboard access to a user.\n"
                "• `/admin revoke <user_id>` — Revoke subscriber dashboard access.\n"
                "• `/admin subscribers` — List all active subscribers with expiration info.\n"
                "• `/grant`, `/revoke`, `/subscribers` — Standalone aliases for the above."
            ),
            inline=False
        )
        embed.add_field(
            name="💎 $2 Crypto Subscription Access",
            value=(
                "Subscribe for **$2 in any crypto (USD value)** to unlock all admin commands.\n"
                f"Contact <@{OWNER_USER_ID}> or visit [JOIN DISCORD]({DISCORD_INVITE_URL}) to activate."
            ),
            inline=False
        )
        embed.set_footer(text=f"{BOT_NAME} • Enterprise Monitoring", icon_url=BOT_AVATAR_URL)
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="subscribe", with_app_command=True, description="Subscribe for $2 in crypto to unlock full dashboard access")
    async def cmd_subscribe(ctx: commands.Context):
        """Standalone /subscribe command — public subscription instructions."""
        embed = create_subscribe_embed()
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="links", with_app_command=True, description="View all affiliate/signup links for every platform (alias for /help links)")
    async def cmd_links(ctx: commands.Context):
        """
        Displays all affiliate/signup links for every supported platform.
        Backward-compatible: redirects to /help which includes links section.
        """
        embed = create_links_embed()
        await ctx.send(embed=embed)

    # ----------------------------------------------------
    # Dashboard & Configuration Commands (Hybrid: Slash & Prefix)
    # ----------------------------------------------------
    @bot.hybrid_command(name="dashboard", aliases=["setup", "panel", "settings", "config"], with_app_command=True, description="Open the interactive platform routing & webhook control panel")
    async def cmd_dashboard(ctx: commands.Context):
        """
        Opens the interactive enterprise visual control panel with drop down menus.
        Public users see affiliate links and a subscribe prompt.
        Restricted to Owner, active $2 crypto subscribers, server administrators, and @admin role users for full admin controls.
        """
        is_auth = manager.is_authorized(ctx.author.id) or _has_admin_access(ctx.author)

        if is_auth:
            uid = str(ctx.author.id)
            is_owner = manager.is_owner(uid)
            embeds = create_dashboard_embed(manager, bot, subscriber_uid=None if is_owner else uid)
            view = DashboardView(manager)
            await ctx.send(embeds=embeds, view=view)
        else:
            embed = create_public_dashboard_embed()
            view = PublicDashboardView()
            await ctx.send(embed=embed, view=view, ephemeral=True)



    @bot.hybrid_command(name="status", with_app_command=True, description="Display real-time monitoring engine status and tracked drop statistics")
    async def cmd_status(ctx: commands.Context):
        """
        Displays the current real-time monitoring engine status and active code statistics.
        """
        is_running = background_monitoring_sweep.is_running()
        interval = manager.get_setting("check_interval_seconds", CHECK_INTERVAL_SECONDS)
        all_tracked = tracker.get_all()

        embed = discord.Embed(
            title=f"📊 {BOT_NAME} — Engine Status",
            description="Always-On Real-Time Multi-Platform Bonus Code Monitoring",
            color=0x10B981 if is_running else 0xEF4444
        )
        embed.add_field(name="⚡ Realtime Monitoring", value="🟢 **ACTIVE**" if is_running else "🔴 **PAUSED**", inline=True)
        embed.add_field(name="⏱️ Polling Interval", value=f"`{interval} seconds`", inline=True)
        embed.add_field(name="📦 Total Tracked Codes", value=f"`{len(all_tracked)} codes`", inline=True)
        embed.add_field(name="🎛️ Dashboard", value="Type `/dashboard` or `!dashboard` to open interactive controls.", inline=False)
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="startmonitor", with_app_command=True, description="Start real-time bonus code monitoring")
    async def cmd_startmonitor(ctx: commands.Context):
        if not manager.is_authorized(ctx.author.id) and not _has_admin_access(ctx.author):
            embed = create_unauthorized_embed()
            await ctx.send(embed=embed, ephemeral=True)
            return
        manager.set_setting("realtime_monitoring_enabled", True)
        if not background_monitoring_sweep.is_running():
            background_monitoring_sweep.start()
        await ctx.send("🟢 Real-time bonus code monitoring has been **STARTED**.")

    # ----------------------------------------------------
    # On-Demand Code Polling & Scan Commands (Consolidated)
    # ----------------------------------------------------
    @bot.hybrid_command(
        name="codes",
        aliases=["activecodes", "livecodes"],
        with_app_command=True,
        description="Query StakeStats for active bonus drops. Usage: /codes [platform]"
    )
    async def cmd_codes(ctx: commands.Context, platform: str = "all"):
        """
        Polls StakeStats live API and displays active codes.
        Usage: /codes [platform]
        Examples:
          /codes — All platforms
          /codes stake.com — Stake.com only
          /codes stake.us — Stake.us only
          /codes qzino — Qzino only
          /codes degen — Degen only
        Backward-compatible: /activecodes, /activecom, /activecodesus, /livecodes all redirect here.
        """
        logger.info(f"User {ctx.author} requested /codes command (platform={platform}). Polling StakeStats live...")
        loop = asyncio.get_running_loop()
        try:
            await ctx.defer()
        except discord.NotFound:
            return
        except Exception as defer_err:
            logger.error(f"Failed to defer codes interaction: {defer_err}")

        plat_filter = None
        if platform and platform.lower() != "all":
            plat_filter = Platform.from_str(platform)
            if plat_filter == Platform.UNKNOWN:
                await ctx.send(f"❌ Unknown platform: `{platform}`. Valid: stake.com, stake.us, qzino, degen, etc.", ephemeral=True)
                return

        try:
            embed_dicts = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: poller.format_discord_active_list(plat_filter)),
                timeout=30
            )

            if not embed_dicts:
                filter_msg = f" for **{plat_filter.value}**" if plat_filter else ""
                await ctx.send(f"No active Stake.us or Stake.com codes were reported right now{filter_msg}.")
                return

            for page_number, ed in enumerate(embed_dicts):
                embed = discord.Embed.from_dict(ed)
                if page_number == 0:
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
        except asyncio.TimeoutError:
            await ctx.send("⏱️ The codes query timed out. Please try again.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /codes command: {e}", exc_info=True)
            try:
                await ctx.send(f"❌ An error occurred while fetching active codes: {str(e)[:200]}", ephemeral=True)
            except Exception:
                pass

    async def send_filtered_active_codes(ctx: commands.Context, platform: Platform) -> None:
        loop = asyncio.get_running_loop()
        try:
            await ctx.defer()
            embed_dicts = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: poller.format_discord_active_list(platform)),
                timeout=30
            )
            if not embed_dicts:
                await ctx.send("No active codes were reported for that platform right now.")
                return
            for embed_dict in embed_dicts:
                await ctx.send(embed=discord.Embed.from_dict(embed_dict))
        except asyncio.TimeoutError:
            await ctx.send("⏱️ The active-code query timed out. Please try again.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in filtered active-code command: {e}", exc_info=True)
            await ctx.send("❌ Unable to retrieve active codes right now.", ephemeral=True)

    # Backward-compatible aliases for platform-filtered codes
    @bot.hybrid_command(name="activecom", with_app_command=True, description="Display only active Stake.com bonus codes (alias for /codes stake.com)")
    async def cmd_activecom(ctx: commands.Context):
        await send_filtered_active_codes(ctx, Platform.STAKE_COM)

    @bot.hybrid_command(name="activecodesus", with_app_command=True, description="Display only active Stake.us bonus codes (alias for /codes stake.us)")
    async def cmd_activecodesus(ctx: commands.Context):
        await send_filtered_active_codes(ctx, Platform.STAKE_US)

    # ----------------------------------------------------
    # Information & Guide Commands (Consolidated)
    # ----------------------------------------------------
    def create_links_embed() -> discord.Embed:
        """
        Generates a comprehensive affiliate/signup links embed for all platforms.
        """
        embed = discord.Embed(
            title=f"🔗 {BOT_NAME} — All Affiliate & Signup Links",
            description="Every platform signup link, community link, and social follow link in one place.",
            color=0x1475E1
        )
        embed.add_field(
            name="🤝 Partnered Offers",
            value=(
                "• 🇺🇸 **Stake.us:** [stake.us/?c=selfmade](https://www.stake.us/?c=selfmade)\n"
                "• 🌏 **Stake.com:** [stake.com/?c=SELFMADE](https://stake.com/?c=SELFMADE)\n"
                "• 🔀 **Shuffle.us:** [shuffle.us/?r=selfmade](https://shuffle.us/?r=selfmade)\n"
                "• 🟣 **Shuffle.com:** [shuffle.com/?r=selfmade](https://shuffle.com/?r=selfmade)\n"
                "• 🎲 **Qzino:** [qzino.ai/?r=SELFMADE](https://qzino.ai/?r=SELFMADE)\n"
                "• 🌧️ **Rainbet:** [rainbet.com/?r=murphy](https://rainbet.com/?r=murphy)"
            ),
            inline=False
        )
        embed.add_field(
            name="📦 Other Platforms",
            value=(
                "• 🔥 **Degen:** [degen.com/r/selfmade](https://degen.com/r/selfmade)\n"
                "• 🐐 **Goated:** [goated.com/?r=selfmade](https://goated.com/?r=selfmade)\n"
                "• 💎 **MYPRIZE.US:** [myprize.us/invite/Traystrees50](https://myprize.us/invite/Traystrees50)\n"
                "• 👑 **CrownCoins:** [crowncoinscasino.com](https://crowncoinscasino.com/)\n"
                "• 🎁 **RealPrize:** [realprize.com/refer/212990](https://www.realprize.com/refer/212990)\n"
                "• 🎰 **AceBet Casino:** [acebet.cc/welcome/r/selfmade](https://acebet.cc/welcome/r/selfmade)\n"
                "• ⭐ **LoneStar Casino:** [lonestarcasino.com/refer/869128](https://lonestarcasino.com/refer/869128)\n"
                "• 🍀 **Chanced Casino:** [chanced.com/c/v5a5yh](https://chanced.com/c/v5a5yh)\n"
                "• 💎 **PULSZ:** [pulsz.com/?invited_by=ga1vnk](https://www.pulsz.com/?invited_by=ga1vnk)\n"
                "• 🎢 **THRILL:** [thrill.com/?r=selfmade](https://thrill.com/?r=selfmade)\n"
                "• 🎮 **MODO:** [modo.us/?referralCode=Z901K9](https://modo.us/?referralCode=Z901K9)\n"
                "• 🎰 **BABA:** [play.babacasino.com](https://play.babacasino.com/)\n"
                "• 🍳 **COOKED.US:** [cooked.us/?auth=register&referral_source=SELFMADE](https://cooked.us/?auth=register&referral_source=SELFMADE)\n"
                "• 🍳 **COOKED.COM:** [cooked.com/?auth=register&referral_source=SELFMADE](https://cooked.com/?auth=register&referral_source=SELFMADE)\n"
                "• 🌟 **WOWVEGAS:** [wowvegas.com/?raf=1274028](https://www.wowvegas.com/?raf=1274028)\n"
                "• 🎉 **YAYCASINO:** [yaycasino.com/signup/7ab97436-a07a-4514-9506-bcbbcd2495e8](https://www.yaycasino.com/signup/7ab97436-a07a-4514-9506-bcbbcd2495e8)\n"
                "• 🏆 **WINNA:** [winna.com/?bonus-center=true&SELFMADE](https://winna.com/?bonus-center=true&SELFMADE)"
            ),
            inline=False
        )
        embed.add_field(
            name="🌐 Community & Social",
            value=(
                "• 💬 **Official Discord:** [JOIN DISCORD](https://discord.gg/TvJe6BV7ge)\n"
                "• 🎥 **Follow Traystrees50 on Kick:** [kick.com/traystrees50](https://www.kick.com/traystrees50)"
            ),
            inline=False
        )
        embed.set_footer(text=f"{BOT_NAME} • Affiliate Links", icon_url=BOT_AVATAR_URL)
        return embed

    class ManualPostModal(discord.ui.Modal):
        def __init__(self, platforms: List[str], manager: DashboardManager, bot: commands.Bot):
            super().__init__(title="Manual Post — Paste Event / Message")
            self.platforms = platforms
            self.manager = manager
            self.bot = bot

            self.message_input = discord.ui.TextInput(
                label="Paste Event or Post Text",
                placeholder="Paste the full event text, claim links, requirements, Bet ID instructions, etc.",
                required=True,
                max_length=2000,
                style=discord.TextStyle.paragraph
            )
            self.add_item(self.message_input)

        async def on_submit(self, interaction: discord.Interaction):
            content = self.message_input.value.strip()
            if not content:
                await interaction.response.send_message("❌ Empty post content.", ephemeral=True)
                return

            notifier = DiscordNotifier(dashboard_manager=self.manager, bot_client=self.bot)
            sent_any = False
            for plat_name in self.platforms:
                try:
                    plat_enum = Platform.from_str(plat_name)
                    success = notifier.send_raw_message(plat_enum, content)
                    if success:
                        sent_any = True
                        logger.info(f"Manual post dispatched to {plat_name} by {interaction.user}")
                except Exception as e:
                    logger.error(f"Error posting to {plat_name}: {e}")

            if sent_any:
                plat_display = ", ".join(self.platforms)
                await interaction.response.send_message(f"✅ Successfully posted raw message to **{plat_display}**.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ No routes available for the selected platform(s). Configure channels/webhooks via `/dashboard`.", ephemeral=True)

    class ManualPostView(discord.ui.View):
        def __init__(self, manager: DashboardManager, bot: commands.Bot, timeout: Optional[float] = 300):
            super().__init__(timeout=timeout)
            self.manager = manager
            self.bot = bot
            self.selected_platforms: List[str] = []

            self.platform_select = discord.ui.Select(
                placeholder="Select Platform(s) to Post To...",
                min_values=1,
                max_values=24,
                options=[
                    discord.SelectOption(label="Stake.us", description="Stake.us Social Casino", emoji="US"),
                    discord.SelectOption(label="Stake.com", description="Stake.com Global Crypto", emoji="GLOBE"),
                    discord.SelectOption(label="Shuffle.us", description="Shuffle.us US Social Casino", emoji="SHUFFLE"),
                    discord.SelectOption(label="Shuffle.com", description="Shuffle.com Crypto Casino", emoji="PURPLE"),
                    discord.SelectOption(label="Rainbet", description="Rainbet Instant Bonus Drops", emoji="RAIN"),
                    discord.SelectOption(label="Degen", description="Degen Drops with Media", emoji="FIRE"),
                    discord.SelectOption(label="Qzino", description="Qzino AI Promotions", emoji="DICE"),
                    discord.SelectOption(label="Goated", description="Goated VIP Drops", emoji="GOAT"),
                    discord.SelectOption(label="MYPRIZE.US", description="MYPRIZE.US Exclusive Offers", emoji="GEM"),
                    discord.SelectOption(label="CrownCoins", description="CrownCoins Social Casino Sweeps", emoji="CROWN"),
                    discord.SelectOption(label="RealPrize", description="RealPrize Referral Rewards", emoji="GIFT"),
                    discord.SelectOption(label="AceBet Casino", description="AceBet Crypto Casino Drops", emoji="SLOT"),
                    discord.SelectOption(label="LoneStar Casino", description="LoneStar Texas-Style Promos", emoji="STAR"),
                    discord.SelectOption(label="Chanced Casino", description="Chanced Lucky Drop Events", emoji="CLOVER"),
                    discord.SelectOption(label="PULSZ", description="PULSZ Platform", emoji="GEM"),
                    discord.SelectOption(label="THRILL", description="THRILL Platform", emoji="ROLLERCOASTER"),
                    discord.SelectOption(label="MODO", description="MODO Platform", emoji="GAME"),
                    discord.SelectOption(label="BABA", description="BABA Casino", emoji="SLOT"),
                    discord.SelectOption(label="COOKED.US", description="COOKED.US Platform", emoji="COOKING"),
                    discord.SelectOption(label="COOKED.COM", description="COOKED.COM Platform", emoji="COOKING"),
                    discord.SelectOption(label="WOWVEGAS", description="WOWVEGAS Platform", emoji="STAR2"),
                    discord.SelectOption(label="YAYCASINO", description="YAYCASINO Platform", emoji="PARTY"),
                    discord.SelectOption(label="WINNA", description="WINNA Platform", emoji="TROPHY"),
                    discord.SelectOption(label="Stake.us & Stake.com", description="Dual Stake Combined", emoji="SLOT"),
                    discord.SelectOption(label="Default", description="Default / Global Fallback", emoji="GLOBE2"),
                ],
                row=0
            )
            self.platform_select.callback = self._on_platform_select
            self.add_item(self.platform_select)

            self.post_button = discord.ui.Button(label="Open Post Form", style=discord.ButtonStyle.primary, row=1)
            self.post_button.callback = self._on_post_click
            self.add_item(self.post_button)

        async def _on_platform_select(self, interaction: discord.Interaction):
            self.selected_platforms = self.platform_select.values
            selected_str = ", ".join(self.selected_platforms)
            await interaction.response.send_message(
                f"Selected {len(self.selected_platforms)} Platform(s): {selected_str}\n"
                f"Click Open Post Form to paste your event text.",
                ephemeral=True
            )

        async def _on_post_click(self, interaction: discord.Interaction):
            if not self.selected_platforms:
                await interaction.response.send_message("Please select at least one platform first.", ephemeral=True)
                return
            modal = self.bot.get_cog("ManualPostModal") or ManualPostModal(self.selected_platforms, self.manager, self.bot)
            await interaction.response.send_modal(modal)


    @bot.tree.command(name="post", description="Manually broadcast a raw event/post to selected platform channels")
    async def slash_post(interaction: discord.Interaction):
        """
        Opens an interactive manual post form with platform selection and text input.
        Restricted to owner, subscribers, server admins, and @admin role.
        """
        if not manager.is_authorized(interaction.user.id) and not _has_admin_access(interaction.user):
            embed = create_unauthorized_embed()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        view = ManualPostView(manager, interaction.client)
        embed = discord.Embed(
            title="📝 Manual Post — Broadcast to Platform Channels",
            description=(
                "**Step 1:** Select one or more target platforms from the dropdown below.\n"
                "**Step 2:** Click **📝 Open Post Form** and paste your full event text / post.\n\n"
                "The message will be sent as raw text to all configured channels and webhooks for the selected platform(s)."
            ),
            color=0x1475E1
        )
        embed.set_footer(text=f"{BOT_NAME} • Manual Broadcast", icon_url=BOT_AVATAR_URL)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @bot.hybrid_command(name="code", with_app_command=True, description="Validate and broadcast a bonus code to configured routes")
    async def cmd_code(ctx: commands.Context, *, raw_input: str):
        """
        Manually submit a bonus code for validation and broadcast.
        Usage: !code <platform> <code> or !code <code>
        Example: !code Stake.us UIJXBQUS
        Restricted to owner, active subscribers, and server admins.
        """
        if not manager.is_authorized(ctx.author.id) and not _has_admin_access(ctx.author):
            embed = create_unauthorized_embed()
            await ctx.send(embed=embed)
            return

        parts = raw_input.strip().split()
        if not parts:
            await ctx.send("❌ Usage: `!code <platform> <code>` or `!code <code>`\nExample: `!code Stake.us UIJXBQUS`")
            return

        platform = None
        code_parts = parts

        if len(parts) >= 2:
            plat_str = parts[0]
            detected = Platform.from_str(plat_str)
            if detected != Platform.UNKNOWN:
                platform = detected
                code_parts = parts[1:]
            else:
                plat_lower = plat_str.lower()
                platform_aliases = {
                    "stake.us": Platform.STAKE_US, "stakeus": Platform.STAKE_US, "us": Platform.STAKE_US,
                    "stake.com": Platform.STAKE_COM, "stakecom": Platform.STAKE_COM, "com": Platform.STAKE_COM,
                    "shuffle.us": Platform.SHUFFLE_US, "shuffleus": Platform.SHUFFLE_US,
                    "shuffle.com": Platform.SHUFFLE_COM, "shufflecom": Platform.SHUFFLE_COM, "shuffle": Platform.SHUFFLE_COM,
                    "qzino": Platform.QZINO,
                    "rainbet": Platform.RAINBET,
                    "degen": Platform.DEGEN,
                    "goated": Platform.GOATED,
                    "myprize.us": Platform.MYPRIZE_US, "myprize": Platform.MYPRIZE_US,
                    "crowncoins": Platform.CROWNSCOINS,
                    "realprize": Platform.REALPRIZE,
                    "acebet": Platform.ACEBET, "acebet casino": Platform.ACEBET,
                    "lonestar": Platform.LONESTAR, "lonestar casino": Platform.LONESTAR,
                    "chanced": Platform.CHANCED, "chanced casino": Platform.CHANCED,
                    "pulsz": Platform.PULSZ,
                    "thrill": Platform.THRILL, "thrillcodes": Platform.THRILL,
                    "modo": Platform.MODO,
                    "baba": Platform.BABA, "baba casino": Platform.BABA,
                    "cooked.us": Platform.COOKED_US, "cookedus": Platform.COOKED_US,
                    "cooked.com": Platform.COOKED_COM, "cookedcom": Platform.COOKED_COM,
                    "wowvegas": Platform.WOWVEGAS,
                    "yaycasino": Platform.YAYCASINO,
                    "winna": Platform.WINNA, "winnacodes": Platform.WINNA,
                }
                if plat_lower in platform_aliases:
                    platform = platform_aliases[plat_lower]
                    code_parts = parts[1:]

        code = " ".join(code_parts).strip()
        if not code:
            await ctx.send("❌ No bonus code provided. Usage: `!code <platform> <code>` or `!code <code>`")
            return

        if platform is None:
            c_upper = code.upper()
            if c_upper.startswith("STAKEUS"):
                platform = Platform.STAKE_US
            elif c_upper.startswith("STAKECOM"):
                platform = Platform.STAKE_COM
            else:
                platform = Platform.UNKNOWN

        c_clean = code.strip()
        c_upper = c_clean.upper()

        if len(c_clean) < 3 or len(c_clean) > 35:
            await ctx.send(f"❌ Invalid code length ({len(c_clean)} chars). Must be 3-35 characters.")
            return

        if c_upper in STOP_WORDS:
            await ctx.send(f"❌ Code `{c_clean}` is a reserved stop word and cannot be submitted.")
            return

        if not re.search(r"[A-Z]", c_upper):
            await ctx.send("❌ Code must contain at least one alphabetic character.")
            return

        if re.search(r"^[0-9]+$", c_upper):
            await ctx.send("❌ Numeric-only codes are not accepted.")
            return

        if tracker.is_seen(platform.value, c_clean):
            await ctx.send(f"⚠️ Code `{c_clean}` for **{platform.value}** has already been submitted/tracked.")
            return

        validation_result = None
        if platform in (
            Platform.STAKE_US,
            Platform.STAKE_COM,
            Platform.DUAL_STAKE,
            Platform.STAKE_US_VIP_NOTICES,
            Platform.STAKE_COM_VIP_NOTICES,
        ):
            validation_result = code_validator.validate(c_clean, platform)
            status = validation_result.get("status", "UNKNOWN")
            if status == "FULLY_CLAIMED":
                await ctx.send(
                    f"❌ Code `{c_clean}` for **{platform.value}** is **FULLY CLAIMED** and cannot be submitted."
                )
                return
            if status == "EXPIRED":
                await ctx.send(
                    f"❌ Code `{c_clean}` for **{platform.value}** is **EXPIRED** and cannot be submitted."
                )
                return
            status_msg = f"🔎 Validator status for `{c_clean}` on **{platform.value}**: **{status}**"
            if validation_result.get("bonusValue") is not None:
                status_msg += f" | Bonus Value: `{validation_result['bonusValue']}`"
            if validation_result.get("cryptoMultiplier") is not None:
                status_msg += f" | Multiplier: `{validation_result['cryptoMultiplier']}x`"
            if validation_result.get("reason"):
                status_msg += f"\n⚠️ Note: {validation_result['reason']}"
            await ctx.send(status_msg)

        # Verify Stake.com/US codes against live StakeStats data before broadcasting
        if platform in (Platform.STAKE_US, Platform.STAKE_COM, Platform.DUAL_STAKE):
            is_owner = manager.is_owner(ctx.author.id)
            is_admin = _has_admin_access(ctx.author)
            if not is_owner and not is_admin:
                is_active = poller.verify_code_active(c_clean, platform)
                if not is_active:
                    await ctx.send(f"❌ Code `{c_clean}` is not currently active on **{platform.value}**. Please verify the code and try again.")
                    return

        source_url = ""
        if ctx.guild:
            source_url = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{ctx.message.id}"

        item = BonusCodeItem(
            code=c_clean,
            platform=platform,
            amount_value="Manual Submission",
            wager_requirement="Unknown",
            source_url=source_url or "Manual Submission",
            source_name=f"{ctx.author} (Manual)",
            is_affiliate=False,
            event_type="DROP",
            description=f"Manually submitted by {ctx.author} via !code command"
        )

        notifier = DiscordNotifier(dashboard_manager=manager, bot_client=bot)
        sent = notifier.send_notification(item)
        tracker.mark_seen(item)

        if sent:
            await ctx.send(f"✅ Successfully submitted and dispatched **{platform.value}** bonus code: `{c_clean}`")
        else:
            await ctx.send(f"✅ Code `{c_clean}` marked as seen for **{platform.value}**, but no Discord routes are configured to broadcast it.")

    @bot.tree.command(name="embed-editor", description="View and edit embed formats for each platform")
    async def slash_embed_editor(interaction: discord.Interaction):
        if not manager.is_authorized(interaction.user.id) and not _has_admin_access(interaction.user):
            embed = create_unauthorized_embed()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        template_manager = EmbedTemplateManager()
        view = EmbedEditorPlatformSelectView(template_manager, interaction)
        embed = discord.Embed(
            title="🎨 Embed Editor Dashboard",
            description="Select a platform below to view and edit its current embed format.",
            color=0x1475E1
        )
        embed.set_footer(text=f"{BOT_NAME} • Embed Editor", icon_url=BOT_AVATAR_URL)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ----------------------------------------------------
    # Admin Command Group (Consolidated: grant, revoke, subscribers)
    # ----------------------------------------------------
    # ----------------------------------------------------
    # Admin Command Group (Consolidated: grant, revoke, subscribers)
    # ----------------------------------------------------
    @bot.group(name="admin", with_app_command=True, description="Admin management commands: grant, revoke, and subscriber listing")
    async def admin_group(ctx: commands.Context):
        if not ctx.invoked_subcommand:
            embed = discord.Embed(
                title="Admin Management",
                description="Available admin commands:\n"
                            "• `/admin grant <user_id>` — Grant dashboard access\n"
                            "• `/admin revoke <user_id>` — Revoke subscriber access\n"
                            "• `/admin subscribers` — List all active subscribers",
                color=0x1475E1
            )
            await ctx.send(embed=embed)

    @admin_group.command(name="grant", description="Grant full dashboard access to a user (owner/admin only)")
    async def admin_grant(ctx: commands.Context, user_id: str, note: str = "Granted by admin", duration: str = "lifetime"):
        if not manager.is_owner(ctx.author.id) and not _has_admin_access(ctx.author):
            embed = create_unauthorized_embed()
            await ctx.send(embed=embed, ephemeral=True)
            return

        uid = user_id.strip()
        duration = duration.strip().lower()
        if uid.isdigit():
            uid = int(uid)
        manager.add_subscriber(uid, note=note, role="subscriber", duration=duration)
        await ctx.send(f"Granted full dashboard access to {uid} ({note}) - Duration: {duration}.", ephemeral=True)

    @admin_group.command(name="revoke", description="Revoke subscriber dashboard access from a user (owner/admin only)")
    async def admin_revoke(ctx: commands.Context, user_id: str):
        if not manager.is_owner(ctx.author.id) and not _has_admin_access(ctx.author):
            embed = create_unauthorized_embed()
            await ctx.send(embed=embed, ephemeral=True)
            return

        uid = user_id.strip()
        if uid.isdigit():
            uid = int(uid)
        removed = manager.remove_subscriber(uid)
        if removed:
            await ctx.send(f"Revoked dashboard access from {uid}.", ephemeral=True)
        else:
            await ctx.send(f"User {uid} is not a subscriber or is the owner.", ephemeral=True)

    @admin_group.command(name="subscribers", description="List all active subscribers with expiration info (owner only)")
    async def admin_subscribers(ctx: commands.Context):
        if not manager.is_owner(ctx.author.id):
            embed = create_unauthorized_embed()
            await ctx.send(embed=embed, ephemeral=True)
            return

        subscribers = manager.get_subscribers()
        if not subscribers:
            await ctx.send("No active subscribers found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{BOT_NAME} - Active Subscribers",
            description="List of all subscribers with expiration info.",
            color=0x1475E1
        )
        for uid, data in subscribers.items():
            duration = data.get("duration", "lifetime")
            expires = data.get("expires_at", "Never")
            role = data.get("role", "subscriber")
            active = "Active" if data.get("active", False) else "Inactive"
            note = data.get("note", "")
            granted = data.get("granted_at", "Unknown")
            embed.add_field(
                name=f"<@{uid}> ({uid})",
                value=f"**Status:** {active}\n**Role:** {role}\n**Duration:** {duration}\n**Expires:** {expires}\n**Granted:** {granted}\n**Note:** {note}",
                inline=False
            )
        embed.set_footer(text=f"{BOT_NAME} - Subscriber Management", icon_url=BOT_AVATAR_URL)
        await ctx.send(embed=embed)

    # ----------------------------------------------------
    # Code Checker Slash Command & Modal
    # ----------------------------------------------------
    class CodeCheckerModal(discord.ui.Modal):
        def __init__(self):
            super().__init__(title="🔎 Code Checker — Validate Bonus Code")
            self.code_input = discord.ui.TextInput(
                label="Paste Bonus Code",
                placeholder="e.g. UIJXBQUS, STAKE7XK9, DEGENWIN",
                required=True,
                max_length=35,
                style=discord.TextStyle.short
            )
            self.platform_input = discord.ui.TextInput(
                label="Platform (optional)",
                placeholder="e.g. Stake.us, Stake.com, Degen, Rainbet",
                required=False,
                max_length=30,
                style=discord.TextStyle.short
            )
            self.add_item(self.code_input)
            self.add_item(self.platform_input)

        async def on_submit(self, interaction: discord.Interaction):
            code = self.code_input.value.strip()
            platform_str = self.platform_input.value.strip() if self.platform_input.value else ""

            if not code:
                await interaction.response.send_message("❌ No code provided.", ephemeral=True)
                return

            # Determine platform
            platform = Platform.UNKNOWN
            if platform_str:
                platform = Platform.from_str(platform_str)
            if platform == Platform.UNKNOWN:
                c_upper = code.upper()
                if c_upper.startswith("STAKEUS"):
                    platform = Platform.STAKE_US
                elif c_upper.startswith("STAKECOM"):
                    platform = Platform.STAKE_COM

            # Validate code
            status = "UNKNOWN"
            bonus_val = "N/A"
            wager = "N/A"
            claims = "N/A"
            redeem_url = ""

            try:
                if platform in (Platform.STAKE_US, Platform.STAKE_COM, Platform.DUAL_STAKE):
                    validator = StakeCodeValidator()
                    result = validator.validate(code, platform)
                    status = result.get("status", "UNKNOWN")
                    bonus_val = result.get("bonusValue", "N/A") or "N/A"
                    wager = result.get("wagerRequirement", "N/A") or "N/A"
                    claims = result.get("claimsRemaining", "N/A") or "N/A"
                else:
                    status = "ACTIVE"
            except Exception as e:
                logger.error(f"Code checker validation error: {e}")
                status = "ERROR"

            # Build claim URL
            if platform == Platform.STAKE_US:
                redeem_url = f"https://stake.us/?c={code}"
            elif platform == Platform.STAKE_COM:
                redeem_url = f"https://stake.com/?c={code}"
            elif platform == Platform.DEGEN:
                redeem_url = f"https://degen.com/r/selfmade"
            elif platform == Platform.RAINBET:
                redeem_url = f"https://rainbet.com/?r=murphy"
            elif platform == Platform.QZINO:
                redeem_url = f"https://qzino.ai/?r=SELFMADE"
            else:
                redeem_url = "https://stake.com/?c=SELFMADE"

            status_emoji = {
                "ACTIVE": "🟢",
                "FULLY_CLAIMED": "🔴",
                "EXPIRED": "⏰",
                "INVALID": "❌",
                "ERROR": "⚠️",
            }.get(status, "🟡")

            checker_embed = discord.Embed(
                title=f"🔎 Code Checker — {platform.value if platform != Platform.UNKNOWN else 'Unknown'}",
                description=f"**Code:** `{code}`\n**Status:** {status_emoji} {status}",
                color=platform.embed_color if platform != Platform.UNKNOWN else 0x1475E1,
            )
            checker_embed.add_field(name="💰 Bonus Value", value=f"`{bonus_val}`", inline=True)
            checker_embed.add_field(name="🔄 Wager", value=f"`{wager}`", inline=True)
            checker_embed.add_field(name="👥 Claims Left", value=f"`{claims}`", inline=True)
            checker_embed.add_field(name="🔗 Claim URL", value=f"[CLICK HERE TO CLAIM]({rede_url})", inline=False)
            checker_embed.add_field(name="💬 Community", value=f"[JOIN DISCORD](https://discord.gg/TvJe6BV7ge)", inline=True)
            kick_url = "https://www.kick.com/moonbootmurphy" if platform == Platform.RAINBET else "https://www.kick.com/traystrees50"
            checker_embed.add_field(name="🎥 Watch on Kick", value=f"[KICK]({kick_url})", inline=True)
            checker_embed.set_footer(text=f"{BOT_NAME} • Code Checker")

            # Save backup
            save_backup("code_check", platform.value if platform != Platform.UNKNOWN else "unknown", code, f"status={status}")

            await interaction.response.send_message(embed=checker_embed, ephemeral=True)

    @bot.tree.command(name="codechecker", description="Check a bonus code status (Active/Expired) with instant claim link")
    async def slash_codechecker(interaction: discord.Interaction):
        """Opens the Code Checker modal for instant ephemeral code validation.
        Works in DMs, servers, and all channels."""
        modal = CodeCheckerModal()
        await interaction.response.send_modal(modal)

    @bot.command(name="checkcode", aliases=["cc"])
    async def prefix_checkcode(ctx: commands.Context, *, code: str = ""):
        """
        Prefix fallback for /codechecker. Works in DMs and servers.
        Usage: !codechecker <code> [platform]
        Example: !codechecker UIJXBQUS Stake.us
        """
        if not code:
            embed = discord.Embed(
                title="🔎 Code Checker",
                description="Paste a bonus code to check its status.\n\n"
                            "**Usage:** `!codechecker <code> [platform]`\n"
                            "**Example:** `!codechecker UIJXBQUS Stake.us`\n\n"
                            "Or use the slash command: `/codechecker`",
                color=0x1475E1
            )
            await ctx.send(embed=embed)
            return

        parts = code.strip().split(maxsplit=1)
        code_str = parts[0].strip()
        platform_str = parts[1].strip() if len(parts) > 1 else ""

        # Determine platform
        platform = Platform.UNKNOWN
        if platform_str:
            platform = Platform.from_str(platform_str)
        if platform == Platform.UNKNOWN:
            c_upper = code_str.upper()
            if c_upper.startswith("STAKEUS"):
                platform = Platform.STAKE_US
            elif c_upper.startswith("STAKECOM"):
                platform = Platform.STAKE_COM

        # Validate code
        status = "UNKNOWN"
        bonus_val = "N/A"
        wager = "N/A"
        claims = "N/A"
        redeem_url = ""

        try:
            if platform in (Platform.STAKE_US, Platform.STAKE_COM, Platform.DUAL_STAKE):
                validator = StakeCodeValidator()
                result = validator.validate(code_str, platform)
                status = result.get("status", "UNKNOWN")
                bonus_val = result.get("bonusValue", "N/A") or "N/A"
                wager = result.get("wagerRequirement", "N/A") or "N/A"
                claims = result.get("claimsRemaining", "N/A") or "N/A"
            else:
                status = "ACTIVE"
        except Exception as e:
            logger.error(f"Code checker validation error: {e}")
            status = "ERROR"

        # Build claim URL
        if platform == Platform.STAKE_US:
            redeem_url = f"https://stake.us/?c={code_str}"
        elif platform == Platform.STAKE_COM:
            redeem_url = f"https://stake.com/?c={code_str}"
        elif platform == Platform.DEGEN:
            redeem_url = "https://degen.com/r/selfmade"
        elif platform == Platform.RAINBET:
            redeem_url = "https://rainbet.com/?r=murphy"
        elif platform == Platform.QZINO:
            redeem_url = "https://qzino.ai/?r=SELFMADE"
        else:
            redeem_url = "https://stake.com/?c=SELFMADE"

        status_emoji = {
            "ACTIVE": "🟢",
            "FULLY_CLAIMED": "🔴",
            "EXPIRED": "⏰",
            "INVALID": "❌",
            "ERROR": "⚠️",
        }.get(status, "🟡")

        checker_embed = discord.Embed(
            title=f"🔎 Code Checker - {platform.value if platform != Platform.UNKNOWN else 'Unknown'}",
            description=f"**Code:** `{code_str}`\n**Status:** {status_emoji} {status}",
            color=platform.embed_color if platform != Platform.UNKNOWN else 0x1475E1,
        )
        checker_embed.add_field(name="💰 Bonus Value", value=f"`{bonus_val}`", inline=True)
        checker_embed.add_field(name="🔄 Wager", value=f"`{wager}`", inline=True)
        checker_embed.add_field(name="👥 Claims Left", value=f"`{claims}`", inline=True)
        checker_embed.add_field(name="🔗 Claim URL", value=f"[CLICK HERE TO CLAIM]({rede_url})", inline=False)
        checker_embed.add_field(name="💬 Community", value=f"[JOIN DISCORD](https://discord.gg/TvJe6BV7ge)", inline=True)
        kick_url = "https://www.kick.com/moonbootmurphy" if platform == Platform.RAINBET else "https://www.kick.com/traystrees50"
        checker_embed.add_field(name="🎥 Watch on Kick", value=f"[KICK]({kick_url})", inline=True)
        checker_embed.set_footer(text=f"{BOT_NAME} - Code Checker")

        # Save backup
        save_backup("code_check", platform.value if platform != Platform.UNKNOWN else "unknown", code_str, f"status={status}")

        await ctx.send(embed=checker_embed)

    try:
        bot.run(DISCORD_BOT_TOKEN, log_handler=None)
    except Exception as e:
        logger.error(f"Error starting Discord bot: {e}", exc_info=True)
