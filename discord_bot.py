import logging
import asyncio
import re
import copy
import datetime
from typing import Optional, Dict, Any, List
import discord
from discord.ext import commands, tasks

from config import (
    DISCORD_BOT_TOKEN, BOT_NAME, BOT_AVATAR_URL, CHECK_INTERVAL_SECONDS,
    OWNER_USER_ID, PERMANENT_ADMIN_USER_IDS, DISCORD_INVITE_URL, AFFILIATE_SIGNUP_LINKS,
)
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
from stake_dashboard import get_tools_dashboard

logger = logging.getLogger("LeakedGG.DiscordBot")
logging.getLogger("discord").setLevel(logging.WARNING)

PUBLIC_APPLICATION_COMMANDS = frozenset({
    "activecodesall",
    "dashboard",
    "tools",
    "info",
    "help",
    "monthly_calc",
    "vip_calc",
})
ADMIN_APPLICATION_COMMANDS = frozenset({
    "admin", "code", "embed-editor", "post", "startmonitor", "status",
    "codechecker", "broadcast_channel",
})
PUBLIC_PREFIX_COMMANDS = frozenset({"activecodesall", "dashboard", "help", "info"})
ADMIN_PREFIX_COMMANDS = frozenset({"admin", "code", "post", "startmonitor", "status", "codechecker", "broadcast_channel"})


def prune_unused_commands(bot: commands.Bot) -> None:
    """Keep supported commands and allow them in guilds and bot DMs."""
    allowed_app_commands = PUBLIC_APPLICATION_COMMANDS | ADMIN_APPLICATION_COMMANDS
    for app_command in tuple(bot.tree.get_commands()):
        if app_command.name not in allowed_app_commands:
            bot.tree.remove_command(app_command.name)
            logger.info("Removed unsupported slash command registration: /%s", app_command.name)

    dm_contexts = discord.app_commands.AppCommandContext(guild=True, dm_channel=True)
    for app_command in bot.tree.walk_commands():
        app_command.allowed_contexts = dm_contexts

    allowed_prefix_commands = PUBLIC_PREFIX_COMMANDS | ADMIN_PREFIX_COMMANDS
    for command in tuple(bot.commands):
        if command.name not in allowed_prefix_commands:
            bot.remove_command(command.name)
            logger.info("Removed unsupported prefix command registration: !%s", command.name)
            continue
        for alias in tuple(command.aliases):
            bot.all_commands.pop(alias, None)
        command.aliases.clear()


def registered_application_command_names(bot: commands.Bot) -> set:
    return {command.name for command in bot.tree.get_commands()}


def _has_admin_access(user: discord.abc.User) -> bool:
    """
    Returns True if the user is a server administrator or has an @admin role.
    Permanent hardcoded admin user IDs are authorized across all servers.
    """
    # Permanent hardcoded admin (authorized regardless of server context)
    if getattr(user, "id", None) in PERMANENT_ADMIN_USER_IDS:
        return True
    if isinstance(user, discord.Member):
        if user.guild_permissions.administrator:
            return True
        return any(role.name.lower() == "admin" for role in user.roles)
    return False


def create_unauthorized_embed() -> discord.Embed:
    """
    Generates an embed explaining who can access management controls.
    """
    embed = discord.Embed(
        title="🔒 Access Restricted — Owner / Admin / Subscriber Only",
        description=(
            f"Administrative and platform routing configuration is restricted to the Project Owner (<@{OWNER_USER_ID}>), "
            "server administrators, users with the `admin` role, and approved subscribers.\n\n"
            "DM the Project Owner to inquire about premium dashboard access."
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
    inquire about premium dashboard access.
    """
    embed = discord.Embed(
        title="📋 Premium Dashboard Access — Inquiry Required",
        description=(
            "Unlock the full **Interactive Dashboard** with multi-platform routing, custom webhooks, "
            "and real-time monitoring controls across all your servers."
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
    embed = discord.Embed(
        title=f"ℹ️ {BOT_NAME} — Information",
        description=(
            f"**{BOT_NAME}** monitors configured Telegram feeds, StakeStats, CodeStats, and web sources for "
            "bonus-code and VIP drops. It extracts available code, value, and wager details, filters duplicates, "
            "and sends platform-specific Discord alerts with source and redemption links.\n\n"
            "Use `/tools` for VIP bonus, wagering, and conversion tools."
        ),
        color=0x8A2BE2
    )
    embed.add_field(
        name="⚡ Core Commands",
        value=(
            "• `/dashboard` — Open the public dashboard and its navigation controls.\n"
            "• `/activecodes` — Fresh Stake.us and Stake.com codes, sorted lowest to highest.\n"
            "• `/info` and `/help` — Bot overview and usage instructions.\n"
            "• `/tools` — Interactive VIP bonus, wagering, and conversion tools."
        ),
        inline=False
    )
    embed.add_field(
        name="🔗 Useful Links",
        value=(
            f"[Stake.us]({AFFILIATE_SIGNUP_LINKS['Stake.us']}) · "
            f"[Stake.com]({AFFILIATE_SIGNUP_LINKS['Stake.com']})\n"
            f"[Official Discord]({DISCORD_INVITE_URL}) · "
            "[Traystrees50 on Kick](https://www.kick.com/traystrees50)"
        ),
        inline=False,
    )

    embed.set_footer(text=f"{BOT_NAME} • Enterprise Ready", icon_url=BOT_AVATAR_URL)
    return embed


def create_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title=f"📖 {BOT_NAME} — Help & Usage",
        description=(
            "Use `/dashboard` to open the interactive home panel. Its navigation menu and quick-action "
            "buttons open active codes, this guide, bot information, and the calculator tools."
        ),
        color=0x1475E1,
    )
    embed.add_field(
        name="🌐 Public Commands",
        value=(
            "• `/dashboard` — Public home panel; its navigation controls open the public features.\n"
            "• `/activecodes` — Poll current Stake.us and Stake.com drops, grouped by platform and sorted "
            "from lowest to highest value. Codes keep their exact casing and include claim links.\n"
            "• `/info` — Monitoring overview, public commands, and useful links.\n"
            "• `/help` — This guide and usage instructions.\n"
            "• `/tools` — Interactive VIP, bonus, wagering, and currency calculators."
        ),
        inline=False,
    )
    embed.add_field(
        name="🔒 Protected Management",
        value=(
            "The full dashboard settings and management commands remain restricted to the project owner, "
            "server administrators or `admin` role, and approved subscribers. Authorized users can access "
            "those controls from the full management dashboard."
        ),
        inline=False,
    )
    embed.add_field(
        name="🧭 Dashboard Navigation",
        value=(
            "Open `/dashboard`, then use the navigation selector or buttons to view active codes, "
            "help, bot information, or tools. In the full management dashboard, use the action selector "
            "for the same public pages alongside the protected configuration actions."
        ),
        inline=False,
    )
    embed.set_footer(text=f"{BOT_NAME} • Commands and usage")
    return embed


def _command_error_message(error: Exception) -> str:
    if isinstance(error, (commands.CommandOnCooldown, discord.app_commands.CommandOnCooldown)):
        return f"⏱️ This command is on cooldown. Try again in {error.retry_after:.1f}s."
    if isinstance(error, commands.MissingRequiredArgument):
        return f"❌ Missing argument: `{error.param.name}`"
    if isinstance(error, commands.BadArgument):
        return f"❌ Invalid argument: {error}"
    if isinstance(error, commands.MissingPermissions):
        return "❌ You don't have permission to use this command."
    return "❌ An unexpected error occurred. Check the bot logs."


async def _send_prefix_command_error(ctx: commands.Context, message: str) -> None:
    send_options = {"ephemeral": True} if ctx.interaction is not None else {}
    await ctx.send(message, **send_options)


async def _send_app_command_error(
    interaction: discord.Interaction,
    message: str,
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


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
    Generates a public-facing dashboard embed with feature navigation and signup links.
    """
    embed = discord.Embed(
        title=f"🎛️ {BOT_NAME} — Public Dashboard",
        description=(
            "Welcome to the public home panel. Use the navigation menu or buttons below to open active "
            "codes, the help guide, bot information, or calculator tools. The full management panel is "
            "available only to authorized users."
        ),
        color=0x1475E1
    )
    embed.add_field(
        name="🎛️ Public Features",
        value=(
            "• `/activecodes` — Fresh Stake.us and Stake.com drops, sorted from lowest to highest value.\n"
            "• `/info` — Monitoring overview and useful links.\n"
            "• `/help` — Instructions for using the bot and dashboard.\n"
            "• `/tools` — Interactive calculator tools."
        ),
        inline=False,
    )

    embed.add_field(
        name="🎰 Casino & Social Platforms",
        value=(
            "• 🇺🇸 **Stake.us:** [stake.us/?c=selfmade](https://www.stake.us/?c=selfmade)\n"
            "• 🌏 **Stake.com:** [stake.com/?c=SELFMADE](https://stake.com/?c=SELFMADE)\n"
            "• 🔀 **Shuffle.us:** [shuffle.us/?r=selfmade](https://shuffle.us/?r=selfmade)\n"
            "• 🟣 **Shuffle.com:** [shuffle.com/?r=selfmade](https://shuffle.com/?r=selfmade)"
        ),
        inline=False
    )
    embed.add_field(
        name="🎲 Crypto & Niche Platforms",
        value=(
            "• 🎲 **Qzino:** [qzino.ai/?r=SELFMADE](https://qzino.ai/?r=SELFMADE)\n"
            "• 🌧️ **Rainbet:** [rainbet.com/?r=smokerzsektion](https://rainbet.com/?r=smokerzsektion)\n"
            "• 🌧️ **Rainbet.us:** [rainbet.us](https://rainbet.us)\n"
            "• 🔥 **Degen:** [degen.com/r/selfmade](https://degen.com/r/selfmade)\n"
            "• 🐐 **Goated:** [goated.com/?r=selfmade](https://goated.com/?r=selfmade)\n"
            "• ⚔️ **Razed:** [razed.com](https://razed.com)"
        ),
        inline=False
    )
    embed.add_field(
        name="💎 Partner Platforms",
        value=(
            "• 🎢 **THRILL:** [thrill.com/?r=selfmade](https://thrill.com/?r=selfmade)\n"
            "• 🏆 **WINNA:** [winna.com/?bonus-center=true&SELFMADE](https://winna.com/?bonus-center=true&SELFMADE)\n"
            "• 🎲 **GAMBA:** [gamba.com?c=bonuscash](https://gamba.com?c=bonuscash)"
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

    embed.set_footer(text=f"{BOT_NAME} • Public Dashboard", icon_url=BOT_AVATAR_URL)
    return embed


class PublicDashboardView(discord.ui.View):
    """
    Public dashboard view for non-authorized users.
    """
    def __init__(self, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        self.add_item(PublicNavigationSelect())
        self.add_item(discord.ui.Button(label="💬 Join Discord", style=discord.ButtonStyle.link, row=2, url=DISCORD_INVITE_URL))
        self.add_item(discord.ui.Button(label="🎥 Follow on Kick", style=discord.ButtonStyle.link, row=2, url="https://www.kick.com/traystrees50"))

    @discord.ui.button(label="Active Codes", style=discord.ButtonStyle.success, row=1, emoji="⚡")
    async def btn_active_codes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_dashboard_section(interaction, "activecodes")

    @discord.ui.button(label="Help", style=discord.ButtonStyle.secondary, row=1, emoji="❔")
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_dashboard_section(interaction, "help")

    @discord.ui.button(label="Bot Info", style=discord.ButtonStyle.secondary, row=1, emoji="ℹ️")
    async def btn_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_dashboard_section(interaction, "info")

    @discord.ui.button(label="Tools", style=discord.ButtonStyle.primary, row=1, emoji="🧮")
    async def btn_tools(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_dashboard_section(interaction, "tools")

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=2, emoji="🔄", custom_id="public_refresh")
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=create_public_dashboard_embed(),
            view=self,
        )


class PublicNavigationSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Active Codes", value="activecodes", emoji="⚡"),
            discord.SelectOption(label="Help & Instructions", value="help", emoji="❔"),
            discord.SelectOption(label="Bot Information", value="info", emoji="ℹ️"),
            discord.SelectOption(label="Calculator Tools", value="tools", emoji="🧮"),
        ]
        super().__init__(
            placeholder="Choose a dashboard page…",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        await show_dashboard_section(interaction, self.values[0])


async def show_dashboard_section(interaction: discord.Interaction, section: str) -> None:
    if section == "info":
        await interaction.response.send_message(embed=create_info_embed(), ephemeral=True)
        return
    if section == "help":
        await interaction.response.send_message(embed=create_help_embed(), ephemeral=True)
        return
    if section == "tools":
        from stake_dashboard import get_tools_dashboard

        embed, view = get_tools_dashboard()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return
    if section != "activecodes":
        raise ValueError(f"Unknown dashboard section: {section}")

    poller = getattr(interaction.client, "stakestats_poller", None)
    if poller is None:
        logger.error("Cannot open active codes from the dashboard: StakeStats poller is unavailable.")
        await interaction.response.send_message(
            "Active codes are temporarily unavailable. Please try again later.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    loop = asyncio.get_running_loop()
    try:
        embed_dicts = await asyncio.wait_for(
            loop.run_in_executor(None, poller.format_discord_active_list),
            timeout=30,
        )
    except asyncio.TimeoutError:
        await interaction.followup.send(
            "The active-code query timed out. Please try again.",
            ephemeral=True,
        )
        return
    except Exception:
        logger.exception("Could not retrieve active codes from the dashboard.")
        await interaction.followup.send(
            "Unable to retrieve active codes right now. Please try again later.",
            ephemeral=True,
        )
        return

    if not embed_dicts:
        await interaction.followup.send("No active codes were reported right now.", ephemeral=True)
        return
    for embed_dict in embed_dicts:
        await interaction.followup.send(
            embed=discord.Embed.from_dict(embed_dict),
            ephemeral=True,
        )


def create_dashboard_embed(manager: DashboardManager, bot: commands.Bot, subscriber_uid: Optional[str] = None) -> List[discord.Embed]:
    """
    Generates compact visual status embeds representing routing configuration across all platforms.
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
                f"🎛️ {BOT_NAME} — Platform Routes"
                if idx == 0
                else f"🎛️ {BOT_NAME} — Routes (Part {idx + 1})"
            ),
            description=(
                f"{status_badge}\n"
                + (
                    f"👤 Personal Routing Mode — your own channel routes.\n"
                    if subscriber_uid
                    else "Configure channel & webhook routes per platform.\n"
                )
                if idx == 0
                else "Continued routing overview:"
            ),
            color=0x1475E1
        )

        for plat_name, data in chunk:
            emoji = data["emoji"]

            if subscriber_uid:
                specific_channels = manager.get_subscriber_channels(subscriber_uid, plat_name)
                specific_webhooks = manager.get_subscriber_webhooks(subscriber_uid, plat_name)
                sub_channels = specific_channels or manager.get_subscriber_channels(subscriber_uid, "Default") or []
                sub_webhooks = specific_webhooks or manager.get_subscriber_webhooks(subscriber_uid, "Default") or []
                ch_display = f"{len(sub_channels)} ch" if sub_channels else "❌ None"
                wh_display = f"{len(sub_webhooks)} wh" if sub_webhooks else "❌ None"
            else:
                channel_ids = data.get("channel_ids", [])
                webhook_urls = data.get("webhook_urls", [])
                ch_display = f"{len(channel_ids)} ch" if channel_ids else "❌ None"
                wh_display = f"{len(webhook_urls)} wh" if webhook_urls else "❌ None"

            embed.add_field(
                name=f"{emoji} {plat_name}",
                value=f"📺 {ch_display}  |  🔗 {wh_display}",
                inline=True
            )

        if idx == len(chunks) - 1:
            embed.add_field(
                name="📡 Active Sources",
                value=(
                    f"Telegram: `{src_summary['total_telegram_channels']}`  |  "
                    f"Web: `{src_summary['total_web_sources']}`  |  "
                    f"Custom: `{src_summary['total_custom_sources']}`"
                ),
                inline=False
            )

        embed.set_footer(
            text=f"{BOT_NAME} • Select platform + action from dropdowns",
            icon_url=BOT_AVATAR_URL
        )
        embeds.append(embed)

    return embeds

# ----------------------------------------------------
# Dashboard Interactive Modals
# ----------------------------------------------------
class AddChannelModal(discord.ui.Modal):
    def __init__(self, platforms: List[str], manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None, invoking_user_id: Optional[int] = None):
        super().__init__(title="Add Labeled Channel")
        self.platforms = platforms
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid
        self.invoking_user_id = invoking_user_id

        self.channels_input = discord.ui.TextInput(
            label="Channel ID",
            placeholder="e.g. 123456789012345678",
            required=True,
            max_length=50,
            style=discord.TextStyle.short
        )
        self.label_input = discord.ui.TextInput(
            label="Server / Channel Label",
            placeholder="e.g. My Server / #bonus-drops",
            required=True,
            max_length=80,
            style=discord.TextStyle.short
        )
        self.add_item(self.channels_input)
        self.add_item(self.label_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Per-user isolation for dashboard modals
        if self.invoking_user_id is not None and interaction.user.id != self.invoking_user_id:
            await interaction.response.send_message("🔒 This dashboard belongs to another user. Open your own with `/dashboard`.", ephemeral=True)
            return
        raw_val = self.channels_input.value.strip().replace("<#", "").replace(">", "")
        label = self.label_input.value.strip()
        try:
            channel_id = int(raw_val)
        except ValueError:
            await interaction.response.send_message("❌ Please provide a valid integer channel ID.", ephemeral=True)
            return
        if not label:
            await interaction.response.send_message("❌ Please provide a non-empty destination label.", ephemeral=True)
            return

        for plat in self.platforms:
            if self.subscriber_uid:
                self.manager.add_subscriber_channel(self.subscriber_uid, plat, channel_id, label)
            else:
                self.manager.add_channel(plat, channel_id, label)

        new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
        await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
        await interaction.followup.send(
            f"✅ Added **{label}** (<#{channel_id}>) to **{', '.join(self.platforms)}**!",
            ephemeral=True
        )


class RemoveChannelModal(discord.ui.Modal):
    def __init__(self, platforms: List[str], manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None, invoking_user_id: Optional[int] = None):
        super().__init__(title="Remove Channel ID")
        self.platforms = platforms
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid
        self.invoking_user_id = invoking_user_id

        self.channel_input = discord.ui.TextInput(
            label="Channel ID to Remove",
            placeholder="e.g. 123456789012345678",
            required=True,
            max_length=50,
            style=discord.TextStyle.short
        )
        self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Per-user isolation for dashboard modals
        if self.invoking_user_id is not None and interaction.user.id != self.invoking_user_id:
            await interaction.response.send_message("🔒 This dashboard belongs to another user. Open your own with `/dashboard`.", ephemeral=True)
            return
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
    def __init__(self, platforms: List[str], manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None, invoking_user_id: Optional[int] = None):
        super().__init__(title="Add Labeled Webhook")
        self.platforms = platforms
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid
        self.invoking_user_id = invoking_user_id

        self.webhook_input = discord.ui.TextInput(
            label="Discord Webhook URL",
            placeholder="https://discord.com/api/webhooks/...",
            required=True,
            max_length=400,
            style=discord.TextStyle.short
        )
        self.label_input = discord.ui.TextInput(
            label="Server / Destination Label",
            placeholder="e.g. My Server / #bonus-drops",
            required=True,
            max_length=80,
            style=discord.TextStyle.short
        )
        self.add_item(self.webhook_input)
        self.add_item(self.label_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Per-user isolation for dashboard modals
        if self.invoking_user_id is not None and interaction.user.id != self.invoking_user_id:
            await interaction.response.send_message("🔒 This dashboard belongs to another user. Open your own with `/dashboard`.", ephemeral=True)
            return
        url = self.webhook_input.value.strip()
        label = self.label_input.value.strip()
        if not (url.startswith("https://discord.com/api/webhooks/") or url.startswith("https://discordapp.com/api/webhooks/")):
            await interaction.response.send_message("❌ No valid Discord Webhook URLs provided (must start with `https://discord.com/api/webhooks/`).", ephemeral=True)
            return
        if not label:
            await interaction.response.send_message("❌ Please provide a non-empty destination label.", ephemeral=True)
            return

        for plat in self.platforms:
            if self.subscriber_uid:
                self.manager.add_subscriber_webhook(self.subscriber_uid, plat, url, label)
            else:
                self.manager.add_webhook(plat, url, label)

        new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
        await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
        await interaction.followup.send(
            f"✅ Added webhook **{label}** to **{', '.join(self.platforms)}**!",
            ephemeral=True
        )


class RemoveWebhookModal(discord.ui.Modal):
    def __init__(self, platforms: List[str], manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None, invoking_user_id: Optional[int] = None):
        super().__init__(title="Remove Webhook URL")
        self.platforms = platforms
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid
        self.invoking_user_id = invoking_user_id

        self.webhook_input = discord.ui.TextInput(
            label="Webhook URL or URL Fragment to Remove",
            placeholder="https://discord.com/api/webhooks/... or part of URL",
            required=True,
            max_length=200,
            style=discord.TextStyle.short
        )
        self.add_item(self.webhook_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Per-user isolation for dashboard modals
        if self.invoking_user_id is not None and interaction.user.id != self.invoking_user_id:
            await interaction.response.send_message("🔒 This dashboard belongs to another user. Open your own with `/dashboard`.", ephemeral=True)
            return
        target = self.webhook_input.value.strip()
        for plat in self.platforms:
            if self.subscriber_uid:
                current_whs = self.manager.get_subscriber_webhooks(self.subscriber_uid, plat)
                for wh in current_whs:
                    label = self.manager.get_subscriber_route_label(self.subscriber_uid, "webhooks", plat, wh)
                    if target in wh or (label and target.lower() in label.lower()):
                        self.manager.remove_subscriber_webhook(self.subscriber_uid, plat, wh)
            else:
                current_whs = self.manager.get_webhooks(plat)
                for wh in current_whs:
                    label = self.manager.get_route_label("webhooks", plat, wh)
                    if target in wh or (label and target.lower() in label.lower()):
                        self.manager.remove_webhook(plat, wh)

        new_embed = create_dashboard_embed(self.manager, interaction.client, self.subscriber_uid)
        await interaction.response.edit_message(embeds=new_embed, view=self.parent_view)
        await interaction.followup.send(
            f"✅ Removed matching webhook from **{', '.join(self.platforms)}**.",
            ephemeral=True
        )


class IntervalModal(discord.ui.Modal):
    def __init__(self, manager: DashboardManager, view: "DashboardView", subscriber_uid: Optional[str] = None, invoking_user_id: Optional[int] = None):
        super().__init__(title="Adjust Realtime Sweep Interval")
        self.manager = manager
        self.parent_view = view
        self.subscriber_uid = subscriber_uid
        self.invoking_user_id = invoking_user_id

        self.interval_input = discord.ui.TextInput(
            label="Scan Interval (in seconds)",
            placeholder="e.g. 30, 60, 120",
            required=True,
            max_length=5,
            default=str(self.manager.get_setting("check_interval_seconds", CHECK_INTERVAL_SECONDS))
        )
        self.add_item(self.interval_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Per-user isolation for dashboard modals
        if self.invoking_user_id is not None and interaction.user.id != self.invoking_user_id:
            await interaction.response.send_message("🔒 This dashboard belongs to another user. Open your own with `/dashboard`.", ephemeral=True)
            return
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
class PlatformSelect(discord.ui.Select):
    """
    Single-select dropdown to choose ONE platform to configure.
    Cleaner than multi-select — avoids selection-state issues in Discord.
    """
    def __init__(self, options: List[discord.SelectOption], row: int, label: str):
        super().__init__(
            placeholder=label,
            min_values=1,
            max_values=1,
            options=options,
            row=row
        )

    async def callback(self, interaction: discord.Interaction):
        selection = self.values[0]
        self.view.selected_platforms = [selection]
        await interaction.response.send_message(
            f"🎯 **Selected Platform:** `{selection}`\n"
            f"👉 Choose an action from **⚙️ Action Dropdown** below.",
            ephemeral=True
        )


def _platform_select_options() -> tuple[List[discord.SelectOption], List[discord.SelectOption]]:
    primary = [
            discord.SelectOption(label="Stake.us", description="Stake.us Social Casino Drops", emoji="🇺🇸", value="Stake.us"),
            discord.SelectOption(label="Stake.com", description="Stake.com Global Crypto Drops", emoji="🌍", value="Stake.com"),
            discord.SelectOption(label="Stake.us - VIP Notices", description="Stake.us VIP Weekly/Monthly Bonus Notices", emoji="👑", value="Stake.us - VIP Notices"),
            discord.SelectOption(label="Stake.com - VIP Notices", description="Stake.com VIP Weekly/Monthly Bonus Notices", emoji="👑", value="Stake.com - VIP Notices"),
            discord.SelectOption(label="Shuffle.us", description="Shuffle.us US Social Casino Drops", emoji="🔀", value="Shuffle.us"),
            discord.SelectOption(label="Shuffle.com", description="Shuffle.com Crypto Casino Drops", emoji="🟣", value="Shuffle.com"),
            discord.SelectOption(label="Rainbet", description="Rainbet.com Instant Bonus Drops", emoji="🌧️", value="Rainbet"),
            discord.SelectOption(label="Rainbet.us", description="Rainbet.us US Bonus Drops", emoji="🌧️", value="Rainbet.us"),
            discord.SelectOption(label="Degen", description="Degen Drops with Media Attachments", emoji="🔥", value="Degen"),
            discord.SelectOption(label="Qzino", description="Qzino AI Promotions", emoji="🎲", value="Qzino"),
            discord.SelectOption(label="Goated", description="Goated VIP Drops", emoji="🐐", value="Goated"),
            discord.SelectOption(label="THRILL", description="THRILL Platform Drops", emoji="🎢", value="THRILL"),
            discord.SelectOption(label="WINNA", description="WINNA Platform Drops", emoji="🏆", value="WINNA"),
        ]
    extra = [
        discord.SelectOption(label="GAMBA", description="GAMBA bonus-code route", emoji="🎲", value="GAMBA"),
        discord.SelectOption(label="Razed", description="Razed bonus-code route", emoji="⚔️", value="Razed"),
        discord.SelectOption(label="Stake.us & Stake.com", description="Dual Stake Combined Routing", emoji="🎰", value="Stake.us & Stake.com"),
        discord.SelectOption(label="Default", description="Default / Global Fallback Route", emoji="🌐", value="Default"),
    ]
    return primary, extra


class GrantAccessModal(discord.ui.Modal):
    def __init__(self, manager: DashboardManager, view: "DashboardView", invoking_user_id: Optional[int] = None):
        super().__init__(title="Grant Dashboard Access")
        self.manager = manager
        self.parent_view = view
        self.invoking_user_id = invoking_user_id

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
        # Per-user isolation for dashboard modals
        if self.invoking_user_id is not None and interaction.user.id != self.invoking_user_id:
            await interaction.response.send_message("🔒 This dashboard belongs to another user. Open your own with `/dashboard`.", ephemeral=True)
            return
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
    def __init__(self, manager: DashboardManager, view: "DashboardView", invoking_user_id: Optional[int] = None):
        super().__init__(title="Revoke Dashboard Access")
        self.manager = manager
        self.parent_view = view
        self.invoking_user_id = invoking_user_id
        self.user_input = discord.ui.TextInput(
            label="Subscriber User ID",
            placeholder="e.g. 123456789012345678",
            required=True,
            max_length=100,
            style=discord.TextStyle.short
        )
        self.add_item(self.user_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Per-user isolation for dashboard modals
        if self.invoking_user_id is not None and interaction.user.id != self.invoking_user_id:
            await interaction.response.send_message("🔒 This dashboard belongs to another user. Open your own with `/dashboard`.", ephemeral=True)
            return
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
    Action dropdown — choose what to do with the selected platform(s).
    Grouped into: Routing, Sources, Testing, Access, Public pages, Utilities.
    """
    def __init__(self, row: int = 3):
        options = [
            # ── Routing ──────────────────────────────────────────────────
            discord.SelectOption(label="Add Channel ID", value="add_channel", description="Add a labeled text channel to selected platform", emoji="➕"),
            discord.SelectOption(label="Remove Channel ID", value="remove_channel", description="Remove a specific channel ID from selected platform", emoji="➖"),
            discord.SelectOption(label="Fast-Bind Current Channel", value="bind_current", description="Bind this current Discord channel to selected platform", emoji="📢"),
            discord.SelectOption(label="Add Webhook URL", value="add_webhook", description="Add a labeled webhook to selected platform", emoji="🔗"),
            discord.SelectOption(label="Remove Webhook URL", value="remove_webhook", description="Remove a webhook URL from selected platform", emoji="✂️"),
            discord.SelectOption(label="Clear All Routes", value="clear_all", description="Wipe channels & webhooks for selected platform", emoji="🗑️"),
            # ── Sources ──────────────────────────────────────────────────
            discord.SelectOption(label="Add Monitored Source", value="add_source", description="Add a Telegram channel or Web Review URL to monitor", emoji="📡"),
            discord.SelectOption(label="Remove Custom Source", value="remove_source", description="Remove a custom Telegram channel or Web Review URL", emoji="🗑️"),
            discord.SelectOption(label="View All Active Sources", value="view_sources", description="Display all monitored Telegram channels, web feeds & APIs", emoji="📋"),
            # ── Testing ──────────────────────────────────────────────────
            discord.SelectOption(label="Test Route Dispatch", value="test_route", description="Send test drop embed to all routes for selected platform", emoji="🧪"),
            discord.SelectOption(label="Make Manual Post", value="manual_post", description="Broadcast a raw event/post to selected platform channels", emoji="📝"),
            # ── Access (admin only) ──────────────────────────────────────
            discord.SelectOption(label="Grant Access", value="grant_access", description="Grant full dashboard access to a user by ID or username", emoji="🔑"),
            discord.SelectOption(label="Revoke Access", value="revoke_access", description="Remove a subscriber's dashboard access by user ID", emoji="🔒"),
            discord.SelectOption(label="List Subscribers", value="list_subscribers", description="View active subscribers and expiration details", emoji="👥"),
            # ── Public pages ─────────────────────────────────────────────
            discord.SelectOption(label="Open Active Codes", value="public_activecodes", description="Show freshly polled Stake.us and Stake.com codes", emoji="⚡"),
            discord.SelectOption(label="Open Help", value="public_help", description="Show bot instructions and command access", emoji="❔"),
            discord.SelectOption(label="Open Bot Info", value="public_info", description="Show monitoring details and useful links", emoji="ℹ️"),
            discord.SelectOption(label="Open Tools", value="public_tools", description="Open the calculator tools dashboard", emoji="🧮"),
            # ── Utilities ────────────────────────────────────────────────
            discord.SelectOption(label="Set Polling Interval", value="set_interval", description="Configure the polling interval for monitoring", emoji="⏱️"),
            discord.SelectOption(label="Health Check", value="health_check", description="Run a comprehensive health check on the bot", emoji="🩺"),
        ]
        super().__init__(
            placeholder="⚙️ Choose an action for the selected platform...",
            min_values=1,
            max_values=1,
            options=options,
            row=row
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action.startswith("public_"):
            await show_dashboard_section(interaction, action[len("public_"):])
            return
        selected_platforms = getattr(self.view, "selected_platforms", ["Stake.us"])
        manager = self.view.manager
        uid = str(interaction.user.id)
        is_owner = manager.is_owner(uid)

        if action == "add_channel":
            modal = AddChannelModal(selected_platforms, manager, self.view, subscriber_uid=None if is_owner else uid, invoking_user_id=self.view.invoking_user_id)
            await interaction.response.send_modal(modal)
        elif action == "remove_channel":
            modal = RemoveChannelModal(selected_platforms, manager, self.view, subscriber_uid=None if is_owner else uid, invoking_user_id=self.view.invoking_user_id)
            await interaction.response.send_modal(modal)
        elif action == "bind_current":
            channel_id = interaction.channel_id
            channel_label = (
                f"{interaction.guild.name} / #{interaction.channel.name}"
                if interaction.guild and interaction.channel
                else f"Channel {channel_id}"
            )
            if is_owner:
                for plat in selected_platforms:
                    manager.add_channel(plat, channel_id, channel_label)
            else:
                for plat in selected_platforms:
                    manager.add_subscriber_channel(uid, plat, channel_id, channel_label)
                if interaction.guild_id is not None:
                    manager.set_subscriber_guild(uid, interaction.guild_id)
            new_embed = create_dashboard_embed(manager, interaction.client, None if is_owner else uid)
            await interaction.response.edit_message(embeds=new_embed, view=self.view)
            await interaction.followup.send(
                f"✅ Bound **{channel_label}** (<#{channel_id}>) to **{', '.join(selected_platforms)}**!",
                ephemeral=True
            )
        elif action == "add_webhook":
            modal = AddWebhookModal(selected_platforms, manager, self.view, subscriber_uid=None if is_owner else uid, invoking_user_id=self.view.invoking_user_id)
            await interaction.response.send_modal(modal)
        elif action == "remove_webhook":
            modal = RemoveWebhookModal(selected_platforms, manager, self.view, subscriber_uid=None if is_owner else uid, invoking_user_id=self.view.invoking_user_id)
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
                if plat_enum == Platform.UNKNOWN:
                    continue
                test_item = SAMPLE_TEST_ITEMS.get(plat_enum)
                if test_item is None:
                    test_item = BonusCodeItem(
                        code=f"{plat_enum.name}_DASHBOARD_TEST",
                        platform=plat_enum,
                        amount_value="Dashboard test notification",
                        wager_requirement="Not specified",
                        source_url=AFFILIATE_SIGNUP_LINKS.get(plat_enum.value, "https://example.com"),
                        source_name="Dashboard route test",
                        is_affiliate=False,
                        description=f"[TEST EVENT] Route test for {plat_enum.value}.",
                    )
                if notifier.send_notification(test_item, subscriber_uid=None if is_owner else uid):
                    sent_count += 1
            await interaction.followup.send(
                f"🧪 Test notification dispatched for **{sent_count} / {len(selected_platforms)} platform(s)** across all configured channels and webhooks!",
                ephemeral=True
            )
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
            modal = GrantAccessModal(manager, self.view, invoking_user_id=self.view.invoking_user_id)
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
            await interaction.response.send_modal(RevokeAccessModal(manager, self.view, invoking_user_id=self.view.invoking_user_id))
        elif action == "set_interval":
            if not is_owner:
                await interaction.response.send_message(
                    "Polling interval is managed by the bot owner.",
                    ephemeral=True
                )
                return
            modal = IntervalModal(manager, self.view, subscriber_uid=None if is_owner else uid, invoking_user_id=self.view.invoking_user_id)
            await interaction.response.send_modal(modal)
        elif action == "health_check":
            health_mon = HealthMonitor(dashboard_manager=manager)
            embed = health_mon.create_health_embed(interaction.client)
            await interaction.response.send_message(embed=embed, ephemeral=True)


class DashboardView(discord.ui.View):
    """
    Clean, compact Interactive Control Panel featuring:
    - Navigation buttons (Home, Active Codes, Settings, Help, Tools)
    - Single-select platform dropdowns (primary + extra)
    - Grouped action dropdown for routing, sources, testing, access
    - Compact embed display for all content
    """
    def __init__(self, manager: DashboardManager, bot: commands.Bot, timeout: Optional[float] = 600, initial_section: str = "home", subscriber_uid: Optional[str] = None, invoking_user_id: Optional[int] = None):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.bot = bot
        self.current_section = initial_section
        self.subscriber_uid = subscriber_uid
        self.invoking_user_id = invoking_user_id
        self.selected_platforms: List[str] = ["Stake.us"]
        self.page_index = 0
        
        # Navigation buttons (row 0) — 5 items max
        self.add_item(NavButton(label="🏠 Home", custom_id="nav_home", style=discord.ButtonStyle.primary, row=0))
        self.add_item(NavButton(label="⚡ Active Codes", custom_id="nav_activecodes", style=discord.ButtonStyle.success, row=0))
        self.add_item(NavButton(label="⚙️ Settings", custom_id="nav_settings", style=discord.ButtonStyle.secondary, row=0))
        self.add_item(NavButton(label="❓ Help", custom_id="nav_help", style=discord.ButtonStyle.secondary, row=0))
        self.add_item(NavButton(label="🔧 Tools", custom_id="nav_tools", style=discord.ButtonStyle.secondary, row=0))
        
        # Platform selectors (row 1-2) — single select each for clean UX
        primary_options, extra_options = _platform_select_options()
        self.platform_select_primary = PlatformSelect(primary_options, row=1, label="🎯 Select platform (primary group)...")
        self.platform_select_extra = PlatformSelect(extra_options, row=2, label="🎯 Select platform (extra group)...")
        self.add_item(self.platform_select_primary)
        self.add_item(self.platform_select_extra)
        
        # Action dropdown (row 3)
        self.add_item(ActionSelect(row=3))
        
        # Pagination + quick actions (row 4) — 5 items max
        self.add_item(PaginationButton(label="◀ Previous", custom_id="page_prev", style=discord.ButtonStyle.secondary, row=4, disabled=True))
        self.add_item(PaginationButton(label="Refresh 🔄", custom_id="page_refresh", style=discord.ButtonStyle.primary, row=4))
        self.add_item(PaginationButton(label="Next ▶", custom_id="page_next", style=discord.ButtonStyle.secondary, row=4, disabled=True))
        
        # Essential action buttons (row 4, remaining 2 slots)
        if not subscriber_uid or manager.is_owner(str(subscriber_uid)):
            self.add_item(QuickActionButton(label="🔄 Toggle Monitor", custom_id="action_toggle_monitor", style=discord.ButtonStyle.success, row=4))
            self.add_item(QuickActionButton(label="📡 Add Source", custom_id="action_add_source", style=discord.ButtonStyle.primary, row=4))
        else:
            self.add_item(QuickActionButton(label="📍 My Routes", custom_id="action_my_routes", style=discord.ButtonStyle.primary, row=4))
            self.add_item(QuickActionButton(label="🔔 Notifications", custom_id="action_notifications", style=discord.ButtonStyle.secondary, row=4))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Per-user isolation: only the user who opened the dashboard may interact with it
        if self.invoking_user_id is not None and interaction.user.id != self.invoking_user_id:
            embed = discord.Embed(
                title="🔒 Dashboard Locked",
                description="This dashboard belongs to another user. Use `/dashboard` to open your own.",
                color=0xED4245
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        if not self.manager.is_authorized(interaction.user.id) and not _has_admin_access(interaction.user):
            embed = create_unauthorized_embed()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        uid = str(interaction.user.id)
        self.subscriber_uid = None if self.manager.is_owner(uid) else uid
        return True

    async def update_display(self, interaction: discord.Interaction):
        """Update the embed based on current section and page."""
        embeds = await self._build_embeds(interaction)
        # Update pagination button states
        for item in self.children:
            if isinstance(item, PaginationButton):
                if item.custom_id == "page_prev":
                    item.disabled = self.page_index <= 0
                elif item.custom_id == "page_next":
                    item.disabled = self.page_index >= len(embeds) - 1
        if len(embeds) == 1:
            await interaction.response.edit_message(embed=embeds[0], view=self)
        else:
            await interaction.response.edit_message(embeds=embeds, view=self)

    async def _build_embeds(self, interaction: discord.Interaction) -> List[discord.Embed]:
        """Build embeds for the current section."""
        if self.current_section == "home":
            return [await self._build_home_embed(interaction)]
        elif self.current_section == "activecodes":
            return await self._build_activecodes_embeds(interaction)
        elif self.current_section == "settings":
            return [await self._build_settings_embed(interaction)]
        elif self.current_section == "help":
            return [await self._build_help_embed(interaction)]
        elif self.current_section == "tools":
            embed, _ = get_tools_dashboard()
            return [embed]
        else:
            return [await self._build_home_embed(interaction)]

    async def _build_home_embed(self, interaction: discord.Interaction) -> discord.Embed:
        is_realtime = self.manager.get_setting("realtime_monitoring_enabled", True)
        interval = self.manager.get_setting("check_interval_seconds", CHECK_INTERVAL_SECONDS)
        summary = self.manager.get_all_routes_summary()
        src_summary = self.manager.get_all_monitored_sources_summary()
        
        status_badge = f"🟢 **ACTIVE** (Every {interval}s)" if is_realtime else "🔴 **PAUSED**"
        
        embed = discord.Embed(
            title=f"🎛️ {BOT_NAME} — Control Panel",
            description=(
                f"{status_badge}\n"
                + (
                    f"👤 **Personal Routing Mode** — Configure your own channel routes.\n"
                    if self.subscriber_uid
                    else "Configure channel & webhook routes per platform.\n"
                    "Use navigation buttons above or dropdowns below."
                )
            ),
            color=0x1475E1
        )
        
        # Platform overview (first 10, single-line inline fields)
        platform_items = list(summary.items())[:10]
        for plat_name, data in platform_items:
            emoji = data["emoji"]
            
            if self.subscriber_uid:
                channels = self.manager.get_subscriber_channels(self.subscriber_uid, plat_name)
                webhooks = self.manager.get_subscriber_webhooks(self.subscriber_uid, plat_name)
                ch_count = len(channels)
                wh_count = len(webhooks)
                ch_display = f"{ch_count} channel(s)" if ch_count else "❌ None"
                wh_display = f"{wh_count} webhook(s)" if wh_count else "❌ None"
            else:
                channel_ids = data.get("channel_ids", [])
                webhook_urls = data.get("webhook_urls", [])
                ch_count = len(channel_ids)
                wh_count = len(webhook_urls)
                ch_display = f"{ch_count} channel(s)" if ch_count else "❌ None"
                wh_display = f"{wh_count} webhook(s)" if wh_count else "❌ None"
            
            embed.add_field(
                name=f"{emoji} {plat_name}",
                value=f"📺 {ch_display}  |  🔗 {wh_display}",
                inline=True
            )
        
        embed.add_field(
            name="📡 Active Sources",
            value=(
                f"Telegram: `{src_summary['total_telegram_channels']}`  |  "
                f"Web: `{src_summary['total_web_sources']}`  |  "
                f"Custom: `{src_summary['total_custom_sources']}`"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"{BOT_NAME} • Select platform + action from dropdowns", icon_url=BOT_AVATAR_URL)
        return embed

    async def _build_activecodes_embeds(self, interaction: discord.Interaction) -> List[discord.Embed]:
        """Build single unified embed for all active codes."""
        poller = getattr(self.bot, "stakestats_poller", None)
        if poller is None:
            return [discord.Embed(
                title="⚡ Active Codes",
                description="Active codes are temporarily unavailable. Please try again later.",
                color=0xFF5555
            )]
        
        loop = asyncio.get_running_loop()
        try:
            # Get all codes without platform filter for unified display
            embed_dicts = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: poller.format_discord_active_list(platform=None)),
                timeout=30,
            )
        except Exception as e:
            logger.error(f"Failed to get active codes: {e}")
            return [discord.Embed(
                title="⚡ Active Codes",
                description="Unable to retrieve active codes right now. Please try again later.",
                color=0xFF5555
            )]
        
        if not embed_dicts:
            return [discord.Embed(
                title="⚡ Active Codes",
                description="No active codes were reported right now.",
                color=0xFFAA00
            )]
        
        # Convert to single unified embed (merge all pages)
        all_fields = []
        for embed_dict in embed_dicts:
            all_fields.extend(embed_dict.get("fields", []))
        
        # Get title and description from first embed
        first = embed_dicts[0]
        title = "⚡ ALL ACTIVE BONUS CODES — UNIFIED VIEW"
        description = first.get("description", "")
        
        # Create single embed with all fields (Discord limit: 25 fields, 6000 chars)
        # Split if needed but try to keep as one
        unified_embed = discord.Embed(
            title=title,
            description=description,
            color=0x00FF88
        )
        
        # Add all fields, respecting Discord limits
        char_count = len(title) + len(description)
        fields_added = 0
        for field in all_fields:
            if fields_added >= 25:
                break
            field_size = len(field.get("name", "")) + len(field.get("value", ""))
            if char_count + field_size > 5500:
                break
            unified_embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", False)
            )
            char_count += field_size
            fields_added += 1
        
        unified_embed.set_footer(
            text=f"{BOT_NAME} • {fields_added} codes shown • Sorted by value (lowest first)",
            icon_url=BOT_AVATAR_URL
        )
        unified_embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        
        return [unified_embed]

    async def _build_settings_embed(self, interaction: discord.Interaction) -> discord.Embed:
        embed = discord.Embed(
            title=f"⚙️ {BOT_NAME} — Settings & Configuration",
            description="Configure monitoring, intervals, and routing preferences.",
            color=0x7289DA
        )
        
        is_realtime = self.manager.get_setting("realtime_monitoring_enabled", True)
        interval = self.manager.get_setting("check_interval_seconds", CHECK_INTERVAL_SECONDS)
        
        embed.add_field(
            name="🔄 Monitoring Status",
            value=f"**Realtime:** {'🟢 ENABLED' if is_realtime else '🔴 DISABLED'}\n**Interval:** {interval}s",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Selected Platforms",
            value=", ".join(self.selected_platforms) if self.selected_platforms else "None",
            inline=True
        )
        
        embed.add_field(
            name="📊 Quick Stats",
            value=(
                f"• Platforms Configured: {len(self.manager.get_all_routes_summary())}\n"
                f"• Telegram Channels: {sum(len(v) for v in self.manager.get_telegram_sources().values())}\n"
                f"• Web Sources: {len(self.manager.get_web_sources())}"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"{BOT_NAME} • Use Action dropdown for quick operations", icon_url=BOT_AVATAR_URL)
        return embed

    async def _build_help_embed(self, interaction: discord.Interaction) -> discord.Embed:
        embed = discord.Embed(
            title=f"❓ {BOT_NAME} — Help & Commands",
            description="Navigate the dashboard using the buttons above.",
            color=0x5865F2
        )
        
        embed.add_field(
            name="🧭 Navigation",
            value=(
                "• **🏠 Home** — Overview of monitoring status and platform routes\n"
                "• **⚡ Active Codes** — Unified view of all live bonus drops\n"
                "• **⚙️ Settings** — Configure monitoring and preferences\n"
                "• **❓ Help** — This help panel\n"
                "• **🔧 Tools** — Stake calculators and utilities"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎮 Quick Actions",
            value=(
                "• **Platform Dropdowns** — Select platforms for bulk operations\n"
                "• **Action Dropdown** — Add/remove channels, webhooks, sources\n"
                "• **Pagination** — Navigate through multiple pages\n"
                "• **Refresh** — Update data in real-time"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📋 Slash Commands",
            value=(
                "`/activecodes` — All active Stake.us & Stake.com codes\n"
                "`/activeus` — Only Stake.us codes\n"
                "`/activecom` — Only Stake.com codes\n"
                "`/dashboard` — Open this control panel\n"
                "`/help` — Show this help\n"
                "`/info` — Bot information\n"
                "`/links` — Affiliate & community links"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"{BOT_NAME} • Enterprise Ready", icon_url=BOT_AVATAR_URL)
        return embed


# =============================================
# Navigation Button
# =============================================
class NavButton(discord.ui.Button):
    def __init__(self, label: str, custom_id: str, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, custom_id=custom_id, style=style, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        view: DashboardView = self.view
        section_map = {
            "nav_home": "home",
            "nav_activecodes": "activecodes",
            "nav_settings": "settings",
            "nav_help": "help",
            "nav_tools": "tools",
        }
        view.current_section = section_map.get(self.custom_id, "home")
        view.page_index = 0
        await view.update_display(interaction)


# =============================================
# Pagination Button
# =============================================
class PaginationButton(discord.ui.Button):
    def __init__(self, label: str, custom_id: str, style: discord.ButtonStyle, row: int, disabled: bool = False):
        super().__init__(label=label, custom_id=custom_id, style=style, row=row, disabled=disabled)
    
    async def callback(self, interaction: discord.Interaction):
        view: DashboardView = self.view
        if self.custom_id == "page_prev":
            view.page_index = max(0, view.page_index - 1)
        elif self.custom_id == "page_next":
            view.page_index += 1
        elif self.custom_id == "page_refresh":
            view.page_index = 0
        await view.update_display(interaction)


# =============================================
# Quick Action Button
# =============================================
class QuickActionButton(discord.ui.Button):
    def __init__(self, label: str, custom_id: str, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, custom_id=custom_id, style=style, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        view: DashboardView = self.view
        if self.custom_id == "action_add_channel":
            if view.subscriber_uid:
                await interaction.response.send_message("Channel management is owner-controlled.", ephemeral=True)
                return
            modal = AddChannelModal(view.selected_platforms, view.manager, view, view.subscriber_uid, invoking_user_id=view.invoking_user_id)
            await interaction.response.send_modal(modal)
        elif self.custom_id == "action_remove_channel":
            if view.subscriber_uid:
                await interaction.response.send_message("Channel management is owner-controlled.", ephemeral=True)
                return
            modal = RemoveChannelModal(view.selected_platforms, view.manager, view, view.subscriber_uid, invoking_user_id=view.invoking_user_id)
            await interaction.response.send_modal(modal)
        elif self.custom_id == "action_add_webhook":
            if view.subscriber_uid:
                await interaction.response.send_message("Webhook management is owner-controlled.", ephemeral=True)
                return
            modal = AddWebhookModal(view.selected_platforms, view.manager, view, view.subscriber_uid, invoking_user_id=view.invoking_user_id)
            await interaction.response.send_modal(modal)
        elif self.custom_id == "action_remove_webhook":
            if view.subscriber_uid:
                await interaction.response.send_message("Webhook management is owner-controlled.", ephemeral=True)
                return
            modal = RemoveWebhookModal(view.selected_platforms, view.manager, view, view.subscriber_uid, invoking_user_id=view.invoking_user_id)
            await interaction.response.send_modal(modal)
        elif self.custom_id == "action_submitted_codes":
            modal = SubmittedCodesRoutingModal(view.manager, view, view.subscriber_uid)
            await interaction.response.send_modal(modal)
        elif self.custom_id == "action_add_source":
            modal = AddSourceModal(
                view.manager,
                view,
                view.selected_platforms[0] if view.selected_platforms else None,
                subscriber_uid=view.subscriber_uid
            )
            await interaction.response.send_modal(modal)
        elif self.custom_id == "action_my_routes":
            embed = create_sources_embed(view.manager)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif self.custom_id == "action_notifications":
            await interaction.response.send_message("Notification preferences coming soon!", ephemeral=True)
        elif self.custom_id == "action_toggle_monitor":
            if view.subscriber_uid:
                await interaction.response.send_message(
                    "Monitoring is managed by the bot owner. Your subscriber dashboard controls personal routes only.",
                    ephemeral=True
                )
                return
            current = view.manager.get_setting("realtime_monitoring_enabled", True)
            new_state = not current
            view.manager.set_setting("realtime_monitoring_enabled", new_state)

            if hasattr(interaction.client, "background_monitor_task"):
                if new_state and not interaction.client.background_monitor_task.is_running():
                    interaction.client.background_monitor_task.start()
                elif not new_state and interaction.client.background_monitor_task.is_running():
                    interaction.client.background_monitor_task.cancel()

            new_embed = create_dashboard_embed(view.manager, interaction.client, view.subscriber_uid)
            await interaction.response.edit_message(embeds=new_embed, view=view)
            state_str = "ENABLED 🟢" if new_state else "PAUSED 🔴"
            await interaction.followup.send(f"Real-time monitoring is now **{state_str}**.", ephemeral=True)


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
    from stake_calculator import register_stake_calculator_commands

    register_stake_calculator_commands(bot)
    manager = DashboardManager()
    tracker = CodeTracker()
    notifier = DiscordNotifier(dashboard_manager=manager, bot_client=bot)
    code_validator = StakeCodeValidator()
    engine = ScraperEngine(tracker=tracker, notifier=notifier, code_validator=code_validator)
    poller = StakeStatsPoller()
    bot.stakestats_poller = poller
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
        allowed_names = registered_application_command_names(bot)
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
                        logger.info(f"Removed stale guild slash command /{cmd['name']} from {guild.name}")
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
                name="Leaked.GG bonus codes | /tools"
            )
        )
        logger.info(f"{BOT_NAME} Discord Bot connected as {bot.user} (ID: {bot.user.id})")
        print(f"\n==================================================================", flush=True)
        print(f" ✅ {BOT_NAME} DISCORD BOT IS ONLINE & RUNNING", flush=True)
        print(f" Connected User: {bot.user} (ID: {bot.user.id})", flush=True)
        print(f" Realtime Monitor: {'ENABLED (Every ' + str(interval_secs) + 's)' if manager.get_setting('realtime_monitoring_enabled', True) else 'PAUSED'}", flush=True)
        print(f" Slash Commands: {', '.join('/' + name for name in sorted(registered_application_command_names(bot)))}", flush=True)
        print(f" Prefix Commands: {', '.join('!' + command.name for command in sorted(bot.commands, key=lambda command: command.name))}", flush=True)
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
        if isinstance(error, commands.CommandNotFound):
            return
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=True)
        await _send_prefix_command_error(ctx, _command_error_message(error))

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ):
        command_name = interaction.command.qualified_name if interaction.command else "unknown"
        logger.error(
            "Application command /%s failed: %s",
            command_name,
            error,
            exc_info=(type(error), error, error.__traceback__),
        )
        await _send_app_command_error(interaction, _command_error_message(error))

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
        with_app_command=True,
        description="Show bot instructions and dashboard navigation"
    )
    async def cmd_help(ctx: commands.Context):
        await ctx.send(embed=create_help_embed())

    @bot.hybrid_command(name="info", with_app_command=True, description="Monitoring overview, public commands, and useful links")
    async def cmd_info(ctx: commands.Context):
        """Show the monitoring overview, public commands, and useful links."""
        embed = create_info_embed()
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="commands", with_app_command=True, description="List monitoring and calculator commands")
    async def cmd_commands(ctx: commands.Context):
        """Standalone /commands command — lists all available commands."""
        embed = discord.Embed(
            title=f"📋 {BOT_NAME} — Available Commands",
            description="Use slash commands or their prefix forms where available.\n🔒 Restricted dashboard actions require owner, subscriber, or server-admin access.",
            color=0x1475E1
        )
        embed.add_field(
            name="🎁 Public Commands",
            value=(
                "• `/activecodes` — All active Stake.us and Stake.com codes.\n"
                "• `/activeus` — Stake.us codes only. `/activecom` — Stake.com codes only.\n"
                "• `/codes [platform]` — Query active codes with an optional platform filter; `/codes` shows both Stake sites.\n"
                "• `/codechecker` — Check a bonus code status (Active/Expired) with instant claim link.\n"
                "  *Prefix:* `!codechecker <code> [platform]`, `!checkcode`, or `!cc`\n"
                "• `/info` — Monitoring overview, public commands, and useful links.\n"
                "• `/help` — Commands and dashboard guide.\n"
                "• `/commands` — List all available commands.\n"
                "• `/tools` — Open the VIP, bonus, and conversion tools dashboard.\n"
                "• `/links` — View all affiliate/signup links for every platform.\n"
                "• `/subscribe` — Inquire about premium dashboard access.\n"
                "• `/dashboard` — Configure labeled platform channels and webhooks."
            ),
            inline=False
        )
        embed.add_field(
            name="🎲 Calculator Commands",
            value=(
                "• `/vip`, `/vip_calc`, `/vip_tiers` — VIP progress and tier ladder.\n"
                "• `/weekly`, `/weekly_calc`, `/monthly`, `/monthly_calc` — Bonus estimates.\n"
                "• `/rakeback`, `/dice98`, `/convert` — Rakeback, wagering, and currency estimates.\n"
                "• `/set_tier`, `/my_tier` — Save or view your preferred tier."
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
                "• `/post` or `!post` — Manually broadcast a raw event/post to selected platform channels.\n"
                "• `/broadcast_channel <channel_id>` — Set a global broadcast channel for all events (admin).\n"
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
                "Prefix equivalents: `!admin grant`, `!admin revoke`, and `!admin subscribers`."
            ),
            inline=False
        )
        embed.add_field(
            name="💬 Community",
            value=(
                f"DM <@{OWNER_USER_ID}> to inquire about premium dashboard access.\n"
                f"Visit [JOIN DISCORD]({DISCORD_INVITE_URL}) to join the community."
            ),
            inline=False
        )
        embed.set_footer(text=f"{BOT_NAME} • Enterprise Monitoring", icon_url=BOT_AVATAR_URL)
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="subscribe", with_app_command=True, description="Inquire about premium dashboard access")
    async def cmd_subscribe(ctx: commands.Context):
        """Standalone /subscribe command — premium access inquiry."""
        embed = create_subscribe_embed()
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="links", with_app_command=True, description="View all affiliate/signup links for every platform")
    async def cmd_links(ctx: commands.Context):
        embed = create_links_embed()
        await ctx.send(embed=embed)

    # ----------------------------------------------------
    # Dashboard & Configuration Commands (Hybrid: Slash & Prefix)
    # ----------------------------------------------------
    @bot.hybrid_command(name="dashboard", with_app_command=True, description="Open the public dashboard or authorized management panel")
    async def cmd_dashboard(ctx: commands.Context):
        """
        Opens the public feature dashboard or the restricted management panel.
        """
        is_auth = manager.is_authorized(ctx.author.id) or _has_admin_access(ctx.author)

        if is_auth:
            uid = str(ctx.author.id)
            is_owner = manager.is_owner(uid)
            view = DashboardView(manager, bot, subscriber_uid=None if is_owner else uid, invoking_user_id=ctx.author.id)
            await ctx.send(view=view, ephemeral=False)
        else:
            embed = create_public_dashboard_embed()
            view = PublicDashboardView()
            await ctx.send(embed=embed, view=view, ephemeral=True)



    @bot.hybrid_command(name="status", with_app_command=True, description="Display real-time monitoring engine status and tracked drop statistics")
    async def cmd_status(ctx: commands.Context):
        """
        Displays the current real-time monitoring engine status and active code statistics.
        """
        if not manager.is_authorized(ctx.author.id) and not _has_admin_access(ctx.author):
            send_options = {"ephemeral": True} if ctx.interaction is not None else {}
            await ctx.send(embed=create_unauthorized_embed(), **send_options)
            return

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

    @bot.hybrid_command(name="broadcast_channel", with_app_command=True, description="Set a global broadcast channel ID to receive all bonus events across all platforms")
    async def cmd_broadcast_channel(ctx: commands.Context, channel_id: str):
        """
        Admin command: Set a global broadcast channel that receives ALL bonus events
        across every platform. The channel is added to the 'Default' platform route,
        which acts as a fallback for any platform without its own dedicated channels.
        """
        if not manager.is_authorized(ctx.author.id) and not _has_admin_access(ctx.author):
            embed = create_unauthorized_embed()
            await ctx.send(embed=embed, ephemeral=True)
            return
        raw_val = channel_id.strip().replace("<#", "").replace(">", "")
        try:
            cid = int(raw_val)
        except ValueError:
            await ctx.send("❌ Please provide a valid integer channel ID.", ephemeral=True)
            return
        manager.add_channel("Default", cid, "Global Broadcast Channel")
        await ctx.send(
            f"✅ Global broadcast channel set: <#{cid}>\n"
            f"All bonus events will now be sent to this channel across all platforms "
            f"(as the Default route fallback).",
            ephemeral=False
        )

    # ----------------------------------------------------
    # On-Demand Code Polling & Scan Commands (Consolidated)
    # ----------------------------------------------------
    @bot.hybrid_command(
        name="codes",
        aliases=["livecodes"],
        with_app_command=True,
        description="Query active Stake.us and Stake.com bonus drops. Usage: /codes [platform]"
    )
    async def cmd_codes(ctx: commands.Context, platform: str = "all"):
        """
        Polls StakeStats live API and displays active codes.
        Usage: /codes [platform]
        Examples:
          /codes — Stake.us and Stake.com
          /codes stake.com — Stake.com only
          /codes stake.us — Stake.us only
          /codes qzino — Qzino only
          /codes degen — Degen only
        Without a platform filter, returns active Stake.us and Stake.com codes.
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
                await ctx.send(f"No active codes found for **{platform.value}** right now.")
                return
            for embed_dict in embed_dicts:
                await ctx.send(embed=discord.Embed.from_dict(embed_dict))
        except asyncio.TimeoutError:
            await ctx.send("⏱️ The active-code query timed out. Please try again.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in filtered active-code command: {e}", exc_info=True)
            await ctx.send("❌ Unable to retrieve active codes right now.", ephemeral=True)

    @bot.hybrid_command(name="activecodes", with_app_command=True, description="Display all active Stake.us and Stake.com bonus codes")
    async def cmd_activecodes(ctx: commands.Context):
        await cmd_codes(ctx, "all")

    @bot.hybrid_command(name="activeus", aliases=["activecodesus"], with_app_command=True, description="Display only active Stake.us bonus codes")
    async def cmd_activeus(ctx: commands.Context):
        await send_filtered_active_codes(ctx, Platform.STAKE_US)

    @bot.hybrid_command(name="activecom", with_app_command=True, description="Display only active Stake.com bonus codes")
    async def cmd_activecom(ctx: commands.Context):
        await send_filtered_active_codes(ctx, Platform.STAKE_COM)

    @bot.hybrid_command(name="activecodescom", with_app_command=True, description="Display only active Stake.com bonus codes")
    async def cmd_activecodescom(ctx: commands.Context):
        await send_filtered_active_codes(ctx, Platform.STAKE_COM)

    @bot.hybrid_command(name="activecodesall", with_app_command=True, description="Display all active Stake.us and Stake.com bonus codes")
    async def cmd_activecodesall(ctx: commands.Context):
        await cmd_codes(ctx, "all")

    # ----------------------------------------------------
    # Information & Guide Commands (Consolidated)
    # ----------------------------------------------------
    def create_links_embed() -> discord.Embed:
        embed = discord.Embed(
            title=f"🔗 {BOT_NAME} — All Affiliate & Signup Links",
            description="Configured signup links for monitored platforms.",
            color=0x1475E1
        )
        link_lines = [f"• **{name}:** <{url}>" for name, url in AFFILIATE_SIGNUP_LINKS.items()]
        for index in range(0, len(link_lines), 8):
            embed.add_field(
                name=f"🎰 Platform Links ({index // 8 + 1})",
                value="\n".join(link_lines[index:index + 8]),
                inline=False,
            )
        embed.add_field(
            name="🌐 Community & Social",
            value=(
                f"• 💬 **Official Discord:** [JOIN DISCORD]({DISCORD_INVITE_URL})\n"
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
                    discord.SelectOption(label="Stake.us", description="Stake.us Social Casino", emoji="🇺🇸"),
                    discord.SelectOption(label="Stake.com", description="Stake.com Global Crypto", emoji="🌍"),
                    discord.SelectOption(label="Shuffle.us", description="Shuffle.us US Social Casino", emoji="🔀"),
                    discord.SelectOption(label="Shuffle.com", description="Shuffle.com Crypto Casino", emoji="🟣"),
                    discord.SelectOption(label="Rainbet", description="Rainbet Instant Bonus Drops", emoji="🌧️"),
                    discord.SelectOption(label="Degen", description="Degen Drops with Media", emoji="🔥"),
                    discord.SelectOption(label="Qzino", description="Qzino AI Promotions", emoji="🎲"),
                    discord.SelectOption(label="Goated", description="Goated VIP Drops", emoji="🐐"),
                    discord.SelectOption(label="THRILL", description="THRILL Platform", emoji="🎢"),
                    discord.SelectOption(label="WINNA", description="WINNA Platform", emoji="🏆"),
                    discord.SelectOption(label="Stake.us & Stake.com", description="Dual Stake Combined", emoji="🎰"),
                    discord.SelectOption(label="Default", description="Default / Global Fallback", emoji="🌐"),
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

    @bot.command(name="post")
    async def prefix_post(ctx: commands.Context):
        if not manager.is_authorized(ctx.author.id) and not _has_admin_access(ctx.author):
            await ctx.send(embed=create_unauthorized_embed())
            return

        view = ManualPostView(manager, bot)
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
        await ctx.send(embed=embed, view=view)

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
                    "thrill": Platform.THRILL, "thrillcodes": Platform.THRILL,
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
    @bot.hybrid_group(name="admin", description="Admin management commands: grant, revoke, and subscriber listing")
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

    @bot.command(name="codechecker", aliases=["checkcode", "cc"])
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

    prune_unused_commands(bot)
    logger.info(
        "Registered public commands: %s; protected commands: %s",
        ", ".join(sorted(PUBLIC_APPLICATION_COMMANDS)),
        ", ".join(sorted(ADMIN_APPLICATION_COMMANDS)),
    )

    try:
        bot.run(DISCORD_BOT_TOKEN, log_handler=None)
    except Exception as e:
        logger.error(f"Error starting Discord bot: {e}", exc_info=True)
