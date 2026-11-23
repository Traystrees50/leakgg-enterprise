import json
import logging
from typing import Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from stake_calculator import (
    TIER_LOOKUP,
    TIER_NAMES,
    VIP_TIERS,
    _build_bonus_embed,
    _build_vip_embed,
    _load_preferences,
    _save_preference,
    calculate_vip_progress,
    convert_currency,
    dice98_calculator,
    estimate_rakeback,
    estimate_weekly_bonus,
    estimate_monthly_bonus,
    format_money,
)

logger = logging.getLogger("LeakedGG.StakeDashboard")

CATEGORIES = {
    "vip": {
        "title": "VIP Tools",
        "description": "Progress, tier information, and your saved preferred tier.",
        "color": 0x00FF9D,
        "tools": [
            ("vip_progress", "VIP Progress", "Calculate progress to your next tier."),
            ("vip_tiers", "VIP Tier List", "View all VIP tiers and thresholds."),
            ("set_tier", "Set Preferred Tier", "Save a tier to preselect in calculators."),
            ("my_tier", "My Preferred Tier", "View your saved tier."),
        ],
    },
    "bonus": {
        "title": "Bonus Tools",
        "description": "Community estimates for bonuses, rakeback, and wagering.",
        "color": 0xF1C40F,
        "tools": [
            ("weekly", "Weekly Bonus", "Estimate a weekly bonus."),
            ("monthly", "Monthly Bonus", "Estimate a monthly bonus."),
            ("rakeback", "Rakeback", "Estimate rakeback from wager and house edge."),
            ("dice98", "Wager Estimate", "Estimate bet size for a wagering target."),
        ],
    },
    "other": {
        "title": "Other Tools",
        "description": "Quick Gold Coin and Sweeps Coin conversions.",
        "color": 0x1ABC9C,
        "tools": [
            ("convert", "GC / SC Converter", "Convert between USD/SC and Gold Coins."),
        ],
    },
}


def _dashboard_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Leaked.GG Tools",
        description="Choose a category to get started. Use the buttons below to navigate.",
        color=0x5865F2,
    )
    for key in ("vip", "bonus", "other"):
        category = CATEGORIES[key]
        embed.add_field(
            name=category["title"],
            value=category["description"],
            inline=True,
        )
    embed.set_footer(text="Calculator outputs are estimates, not guarantees.")
    return embed


def _category_embed(category_key: str) -> discord.Embed:
    category = CATEGORIES[category_key]
    return discord.Embed(
        title=category["title"],
        description=f"{category['description']}\n\nChoose a tool below or go back to the main menu.",
        color=category["color"],
    )


def _help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="How to use the tools",
        description=(
            "1. Choose a category from the main menu.\n"
            "2. Select a tool and follow its prompts.\n"
            "3. Use **Back** to return to the previous menu.\n\n"
            "VIP progress and bonus tools can use your saved preferred tier. "
            "Set it from **VIP Tools → Set Preferred Tier**.\n\n"
            "Bonus figures are community estimates, not official Stake formulas. "
            "Gambling outcomes are random and may result in losses."
        ),
        color=0x5865F2,
    )
    embed.set_footer(text="The monitoring controls remain available through /dashboard.")
    return embed


def _tier_ladder_embed() -> discord.Embed:
    lines = [
        f"**{tier['name']}** — {format_money(tier['threshold'])}"
        for tier in VIP_TIERS
    ]
    embed = discord.Embed(
        title="Stake VIP Tier Ladder",
        description="\n".join(lines),
        color=CATEGORIES["vip"]["color"],
    )
    embed.set_footer(text="Thresholds are informational and may change.")
    return embed


def _preferred_tier(user_id: int) -> Tuple[Optional[str], bool]:
    try:
        saved = _load_preferences().get(str(user_id), {})
    except (OSError, ValueError, json.JSONDecodeError):
        logger.exception("Could not load a saved VIP tier for the tools dashboard.")
        return None, True
    tier = saved.get("tier") if isinstance(saved, dict) else None
    return (tier if isinstance(tier, str) and tier in TIER_LOOKUP else None), False


async def _warn_saved_tier_unavailable(interaction: discord.Interaction, failed: bool) -> None:
    if failed:
        await interaction.followup.send(
            "I couldn't read your saved tier, so choose one manually. You can still use the calculator.",
            ephemeral=True,
        )


async def _show_main_menu(interaction: discord.Interaction) -> None:
    await interaction.response.edit_message(
        embed=_dashboard_embed(),
        view=_ToolsMainMenuView(),
    )


async def _show_category(interaction: discord.Interaction, category: str) -> None:
    await interaction.response.edit_message(
        embed=_category_embed(category),
        view=_ToolsCategoryView(category),
    )


class _BackButton(discord.ui.Button):
    def __init__(self, label: str, custom_id: str, destination: str):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=custom_id,
        )
        self.destination = destination

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.destination == "main":
            await _show_main_menu(interaction)
            return
        await _show_category(interaction, self.destination)


# Navigation is Main Menu -> Category -> Tool form -> Modal result.
# Stable custom IDs and timeout-free views let Discord restore these menus after restarts.
class _ToolsMainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="VIP Tools",
        style=discord.ButtonStyle.primary,
        emoji="🏆",
        custom_id="tools:main:vip",
    )
    async def vip_tools(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await _show_category(interaction, "vip")

    @discord.ui.button(
        label="Bonus Tools",
        style=discord.ButtonStyle.primary,
        emoji="🎁",
        custom_id="tools:main:bonus",
    )
    async def bonus_tools(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await _show_category(interaction, "bonus")

    @discord.ui.button(
        label="Other Tools",
        style=discord.ButtonStyle.primary,
        emoji="🪙",
        custom_id="tools:main:other",
    )
    async def other_tools(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await _show_category(interaction, "other")

    @discord.ui.button(
        label="Help / How to use",
        style=discord.ButtonStyle.secondary,
        emoji="❔",
        custom_id="tools:main:help",
    )
    async def help(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            embed=_help_embed(),
            view=_ToolsHelpView(),
        )


class _ToolsHelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(_BackButton("Back to Main Menu", "tools:back:main:help", "main"))


class _OpenToolButton(discord.ui.Button):
    def __init__(self, tool_key: str, label: str, description: str):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"tools:open:{tool_key}",
        )
        self.tool_key = tool_key
        self.description = description

    async def callback(self, interaction: discord.Interaction) -> None:
        await _open_tool(interaction, self.tool_key)


class _ToolsCategoryView(discord.ui.View):
    def __init__(self, category_key: str):
        super().__init__(timeout=None)
        for tool_key, label, description in CATEGORIES[category_key]["tools"]:
            self.add_item(_OpenToolButton(tool_key, label, description))
        self.add_item(
            _BackButton(
                "Back to Main Menu",
                f"tools:back:main:{category_key}",
                "main",
            )
        )


class _TierSelect(discord.ui.Select):
    def __init__(
        self,
        preferred_tier: Optional[str] = None,
        custom_id: str = "tools:vip:progress:tier",
    ):
        options = [
            discord.SelectOption(
                label=tier,
                value=tier,
                default=tier == preferred_tier,
            )
            for tier in TIER_NAMES
        ]
        super().__init__(
            placeholder="Select your current VIP tier…",
            options=options,
            custom_id=custom_id,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_DashboardProgressModal(self.values[0]))


class _VipProgressView(discord.ui.View):
    def __init__(self, preferred_tier: Optional[str] = None):
        super().__init__(timeout=None)
        self.add_item(_TierSelect(preferred_tier))
        self.add_item(
            _BackButton(
                "Back to VIP Tools",
                "tools:back:vip:progress",
                "vip",
            )
        )


class _VipDashboard(discord.ui.View):
    def __init__(self, preferred_tier: Optional[str] = None):
        super().__init__(timeout=None)
        self.add_item(
            _TierSelect(
                preferred_tier,
                custom_id="tools:vip:slash:tier",
            )
        )
        self.add_item(
            _BackButton(
                "Back to VIP Tools",
                "tools:back:vip:slash",
                "vip",
            )
        )

    @discord.ui.button(
        label="Show All Tiers",
        style=discord.ButtonStyle.secondary,
        custom_id="tools:vip:slash:tiers",
    )
    async def show_tiers(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            embed=_tier_ladder_embed(),
            ephemeral=True,
        )


class _DashboardProgressModal(discord.ui.Modal, title="VIP Progress"):
    value = discord.ui.TextInput(
        label="Progress % (0–100) or total wagered",
        placeholder="42.5 or 75000",
        required=True,
    )

    def __init__(self, tier: str):
        super().__init__()
        self.tier = tier

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            number = float(self.value.value.strip().replace(",", "").replace("$", ""))
            result = calculate_vip_progress(
                self.tier,
                total_wagered=number if number > 100 else None,
                progress_pct=None if number > 100 else number,
            )
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_build_vip_embed(result),
            view=_ToolsCategoryView("vip"),
        )


class _BonusTierSelect(discord.ui.Select):
    def __init__(self, kind: str, preferred_tier: Optional[str] = None):
        self.kind = kind
        options = [
            discord.SelectOption(
                label=tier,
                value=tier,
                default=tier == preferred_tier,
            )
            for tier in TIER_NAMES
            if tier != "Unranked"
        ]
        key = kind.lower()
        super().__init__(
            placeholder=f"Select VIP tier for {kind}…",
            options=options,
            custom_id=f"tools:bonus:{key}:tier",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_DashboardBonusModal(self.values[0], self.kind))


class _BonusToolView(discord.ui.View):
    def __init__(self, kind: str, preferred_tier: Optional[str] = None):
        super().__init__(timeout=None)
        self.kind = kind
        self.add_item(_BonusTierSelect(kind, preferred_tier))
        self.add_item(
            _BackButton(
                "Back to Bonus Tools",
                f"tools:back:bonus:{kind.lower()}",
                "bonus",
            )
        )


class _DashboardBonusModal(discord.ui.Modal):
    wager = discord.ui.TextInput(label="Total Wagered ($)", placeholder="25000", required=True)
    result = discord.ui.TextInput(
        label="Net Profit/Loss (negative for loss)",
        placeholder="-1200 or 800",
        required=True,
    )

    def __init__(self, tier: str, kind: str):
        super().__init__(title=f"{kind} Bonus Estimate")
        self.tier = tier
        self.kind = kind

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            wagered = float(self.wager.value.replace(",", "").replace("$", ""))
            net_result = float(self.result.value.replace(",", "").replace("$", ""))
            estimate = (
                estimate_weekly_bonus(self.tier, wagered, net_result)
                if self.kind == "Weekly"
                else estimate_monthly_bonus(self.tier, wagered, net_result)
            )
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_build_bonus_embed(self.kind, estimate),
            view=_ToolsCategoryView("bonus"),
        )


class _SetTierSelect(discord.ui.Select):
    def __init__(self, preferred_tier: Optional[str] = None):
        options = [
            discord.SelectOption(
                label=tier,
                value=tier,
                default=tier == preferred_tier,
            )
            for tier in TIER_NAMES
        ]
        super().__init__(
            placeholder="Choose your preferred tier…",
            options=options,
            custom_id="tools:vip:set-tier:select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        tier = self.values[0]
        try:
            _save_preference(interaction.user.id, tier)
        except (OSError, ValueError, json.JSONDecodeError):
            logger.exception("Could not save preferred VIP tier from the tools dashboard.")
            await interaction.response.send_message(
                "Could not save your tier preference. Check the bot's data file and try again.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            content=f"Preferred tier saved: **{tier}**.",
            embed=_category_embed("vip"),
            view=_ToolsCategoryView("vip"),
        )


class _SetTierView(discord.ui.View):
    def __init__(self, preferred_tier: Optional[str] = None):
        super().__init__(timeout=None)
        self.add_item(_SetTierSelect(preferred_tier))
        self.add_item(
            _BackButton(
                "Back to VIP Tools",
                "tools:back:vip:set-tier",
                "vip",
            )
        )


class _OpenModalButton(discord.ui.Button):
    def __init__(self, label: str, custom_id: str, modal_type: type):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success,
            custom_id=custom_id,
        )
        self.modal_type = modal_type

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(self.modal_type())


class _RakebackView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            _OpenModalButton(
                "Enter wager and house edge",
                "tools:bonus:rakeback:open",
                _RakebackModal,
            )
        )
        self.add_item(
            _BackButton(
                "Back to Bonus Tools",
                "tools:back:bonus:rakeback",
                "bonus",
            )
        )


class _RakebackModal(discord.ui.Modal, title="Rakeback Estimate"):
    wagered = discord.ui.TextInput(label="Amount wagered ($)", placeholder="10000", required=True)
    edge = discord.ui.TextInput(
        label="House edge (decimal; default 0.01)",
        placeholder="0.01",
        default="0.01",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            result = estimate_rakeback(
                float(self.wagered.value.replace(",", "").replace("$", "")),
                float(self.edge.value or "0.01"),
            )
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        embed = discord.Embed(title="Stake Rakeback Estimate", color=0x3498DB)
        embed.add_field(name="Wagered", value=format_money(result["wagered"]), inline=True)
        embed.add_field(name="House Edge", value=f"{result['edge'] * 100:.2f}%", inline=True)
        embed.add_field(
            name="Estimated Rakeback",
            value=f"**{format_money(result['rakeback'])}**",
            inline=False,
        )
        embed.set_footer(text="Estimate only; actual rates may differ.")
        await interaction.response.send_message(
            embed=embed,
            view=_ToolsCategoryView("bonus"),
        )


class _Dice98View(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            _OpenModalButton(
                "Enter wagering details",
                "tools:bonus:dice98:open",
                _Dice98Modal,
            )
        )
        self.add_item(
            _BackButton(
                "Back to Bonus Tools",
                "tools:back:bonus:dice98",
                "bonus",
            )
        )


class _Dice98Modal(discord.ui.Modal, title="Wagering Estimate"):
    required_wager = discord.ui.TextInput(
        label="Required wager volume ($)",
        placeholder="10000",
        required=True,
    )
    bankroll = discord.ui.TextInput(
        label="Current bankroll ($, optional)",
        placeholder="500",
        required=False,
    )
    bets = discord.ui.TextInput(
        label="Number of bets (default 10,000)",
        placeholder="10000",
        default="10000",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            result = dice98_calculator(
                float(self.required_wager.value.replace(",", "").replace("$", "")),
                float((self.bankroll.value or "0").replace(",", "").replace("$", "")),
                int((self.bets.value or "10000").replace(",", "")),
            )
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        embed = discord.Embed(title="Wagering Estimate", color=0x9B59B6)
        embed.add_field(
            name="Required Wager Volume",
            value=format_money(result["required_wager"]),
            inline=True,
        )
        embed.add_field(
            name="Illustrative Bet Size",
            value=f"${result['recommended_bet']:.4f}",
            inline=True,
        )
        embed.add_field(name="Number of Bets", value=f"{result['bet_count']:,}", inline=True)
        embed.add_field(
            name="Estimated Cost at 1% Edge",
            value=format_money(result["expected_cost"]),
            inline=False,
        )
        if result["bankroll"] > 0:
            embed.add_field(
                name="Bankroll after estimated cost",
                value=format_money(result["expected_remaining"]),
                inline=False,
            )
        embed.set_footer(
            text="Illustration only; outcomes are random and losses may exceed this estimate."
        )
        await interaction.response.send_message(
            embed=embed,
            view=_ToolsCategoryView("bonus"),
        )


class _UnitSelect(discord.ui.Select):
    def __init__(
        self,
        owner: "_ConvertView",
        direction: str,
        default_value: str,
        custom_id: str,
    ):
        self.owner = owner
        self.direction = direction
        options = [
            discord.SelectOption(
                label="USD / SC",
                value="usd",
                default=default_value == "usd",
            ),
            discord.SelectOption(
                label="Gold Coins (GC)",
                value="gc",
                default=default_value == "gc",
            ),
        ]
        super().__init__(
            placeholder=f"Select {'source' if direction == 'from_unit' else 'target'} unit",
            options=options,
            custom_id=custom_id,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        setattr(self.owner, self.direction, self.values[0])
        await interaction.response.defer()


class _ConvertView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.from_unit = "usd"
        self.to_unit = "gc"
        self.add_item(
            _UnitSelect(
                self,
                "from_unit",
                "usd",
                "tools:other:convert:from",
            )
        )
        self.add_item(
            _UnitSelect(
                self,
                "to_unit",
                "gc",
                "tools:other:convert:to",
            )
        )
        self.add_item(
            _OpenConvertModalButton(
                self,
                "tools:other:convert:open",
            )
        )
        self.add_item(
            _BackButton(
                "Back to Other Tools",
                "tools:back:other:convert",
                "other",
            )
        )


class _OpenConvertModalButton(discord.ui.Button):
    def __init__(self, owner: _ConvertView, custom_id: str):
        super().__init__(
            label="Enter amount",
            style=discord.ButtonStyle.success,
            custom_id=custom_id,
        )
        self.owner = owner

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            _ConvertModal(self.owner.from_unit, self.owner.to_unit)
        )


class _ConvertModal(discord.ui.Modal, title="GC / SC Converter"):
    amount = discord.ui.TextInput(label="Amount", placeholder="10", required=True)

    def __init__(self, from_unit: str, to_unit: str):
        super().__init__()
        self.from_unit = from_unit
        self.to_unit = to_unit

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            amount = float(self.amount.value.replace(",", "").replace("$", ""))
            result = convert_currency(amount, self.from_unit, self.to_unit)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        embed = discord.Embed(title="Stake.us Conversion", color=0x1ABC9C)
        embed.add_field(
            name="Input",
            value=f"{result['amount']:,.4f} {result['from_unit'].upper()}",
            inline=True,
        )
        embed.add_field(
            name="Output",
            value=f"**{result['result']:,.4f} {result['to_unit'].upper()}**",
            inline=True,
        )
        embed.set_footer(text="Approximate community rates: 1 SC ≈ $1; 2,000,000 GC ≈ $1.")
        await interaction.response.send_message(
            embed=embed,
            view=_ToolsCategoryView("other"),
        )


async def _open_tool(interaction: discord.Interaction, tool_key: str) -> None:
    if tool_key == "vip_progress":
        preferred_tier, failed = _preferred_tier(interaction.user.id)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="VIP Progress",
                description="Choose your current tier, then enter your progress or total wagered.",
                color=CATEGORIES["vip"]["color"],
            ),
            view=_VipProgressView(preferred_tier),
        )
        await _warn_saved_tier_unavailable(interaction, failed)
    elif tool_key == "vip_tiers":
        await interaction.response.edit_message(
            embed=_tier_ladder_embed(),
            view=_ToolsCategoryView("vip"),
        )
    elif tool_key == "set_tier":
        preferred_tier, failed = _preferred_tier(interaction.user.id)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Set Preferred VIP Tier",
                description="Choose a tier to save and use as the default in calculator menus.",
                color=CATEGORIES["vip"]["color"],
            ),
            view=_SetTierView(preferred_tier),
        )
        await _warn_saved_tier_unavailable(interaction, failed)
    elif tool_key == "my_tier":
        try:
            saved = _load_preferences().get(str(interaction.user.id), {})
            tier = saved.get("tier") if isinstance(saved, dict) else None
        except (OSError, ValueError, json.JSONDecodeError):
            logger.exception("Could not load preferred VIP tier from the tools dashboard.")
            await interaction.response.send_message(
                "Could not load your saved tier. Check the bot's data file and try again.",
                ephemeral=True,
            )
            return
        if not isinstance(tier, str) or tier not in TIER_LOOKUP:
            message = "No valid saved tier. Choose **Set Preferred Tier** to save one."
        else:
            message = f"Your saved preferred tier is **{tier}**."
        await interaction.response.send_message(message, ephemeral=True)
    elif tool_key in {"weekly", "monthly"}:
        kind = tool_key.capitalize()
        preferred_tier, failed = _preferred_tier(interaction.user.id)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"{kind} Bonus Estimate",
                description="Choose a VIP tier, then enter your wager and net result.",
                color=CATEGORIES["bonus"]["color"],
            ),
            view=_BonusToolView(kind, preferred_tier),
        )
        await _warn_saved_tier_unavailable(interaction, failed)
    elif tool_key == "rakeback":
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Rakeback Estimate",
                description="Enter your wager and house edge to calculate an estimate.",
                color=CATEGORIES["bonus"]["color"],
            ),
            view=_RakebackView(),
        )
    elif tool_key == "dice98":
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Wagering Estimate",
                description="Enter the target wager volume and optional bankroll and bet count.",
                color=CATEGORIES["bonus"]["color"],
            ),
            view=_Dice98View(),
        )
    elif tool_key == "convert":
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="GC / SC Converter",
                description="Choose source and target units, then enter the amount.",
                color=CATEGORIES["other"]["color"],
            ),
            view=_ConvertView(),
        )


def register_tools_dashboard(bot: commands.Bot) -> None:
    # Register static menu layouts so already-sent dashboard messages remain interactive.
    persistent_views = [
        _ToolsMainMenuView(),
        _ToolsHelpView(),
        *[_ToolsCategoryView(category) for category in CATEGORIES],
        _VipProgressView(),
        _VipDashboard(),
        _BonusToolView("Weekly"),
        _BonusToolView("Monthly"),
        _SetTierView(),
        _RakebackView(),
        _Dice98View(),
        _ConvertView(),
    ]
    for view in persistent_views:
        bot.add_view(view)

    @bot.tree.command(name="tools", description="Open the interactive calculator tools dashboard")
    async def tools_dashboard(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=_dashboard_embed(),
            view=_ToolsMainMenuView(),
        )
