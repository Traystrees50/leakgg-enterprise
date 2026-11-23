import json
import logging
import math
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("LeakedGG.StakeCalculator")
PREFERENCES_FILE = Path("user_prefs.json")

VIP_TIERS = [
    {"name": "Unranked", "threshold": 0, "next": "Bronze", "bonus": 20, "mult": 0.0},
    {"name": "Bronze", "threshold": 10_000, "next": "Silver", "bonus": 50, "mult": 1.0},
    {"name": "Silver", "threshold": 50_000, "next": "Gold", "bonus": 110, "mult": 1.15},
    {"name": "Gold", "threshold": 100_000, "next": "Platinum I", "bonus": 200, "mult": 1.3},
    {"name": "Platinum I", "threshold": 250_000, "next": "Platinum II", "bonus": 400, "mult": 1.5},
    {"name": "Platinum II", "threshold": 500_000, "next": "Platinum III", "bonus": 800, "mult": 1.65},
    {"name": "Platinum III", "threshold": 1_000_000, "next": "Platinum IV", "bonus": 1600, "mult": 1.8},
    {"name": "Platinum IV", "threshold": 2_500_000, "next": "Platinum V", "bonus": 3200, "mult": 1.95},
    {"name": "Platinum V", "threshold": 5_000_000, "next": "Platinum VI", "bonus": 6400, "mult": 2.1},
    {"name": "Platinum VI", "threshold": 10_000_000, "next": "Diamond I", "bonus": 12800, "mult": 2.2},
    {"name": "Diamond I", "threshold": 25_000_000, "next": "Diamond II", "bonus": None, "mult": 2.3},
    {"name": "Diamond II", "threshold": 50_000_000, "next": "Diamond III", "bonus": None, "mult": 2.35},
    {"name": "Diamond III", "threshold": 100_000_000, "next": "Diamond IV", "bonus": None, "mult": 2.4},
    {"name": "Diamond IV", "threshold": 250_000_000, "next": "Diamond V", "bonus": None, "mult": 2.4},
    {"name": "Diamond V", "threshold": 500_000_000, "next": "Obsidian", "bonus": None, "mult": 2.4},
    {"name": "Obsidian", "threshold": 1_000_000_000, "next": None, "bonus": None, "mult": 2.4},
]
TIER_NAMES = [tier["name"] for tier in VIP_TIERS]
TIER_LOOKUP = {tier["name"]: tier for tier in VIP_TIERS}
EDGES = {
    "Blackjack (≈0.5%)": 0.005,
    "Originals / Dice / Limbo (1%)": 0.01,
    "Slots (≈3.5%)": 0.035,
}


def _finite_number(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    return value


def format_money(amount: float) -> str:
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.2f}B"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount:,.2f}"


def calculate_vip_progress(
    current_tier: str,
    progress_pct: Optional[float] = None,
    total_wagered: Optional[float] = None,
) -> dict:
    if current_tier not in TIER_LOOKUP:
        raise ValueError("Choose a valid VIP tier.")

    tier = TIER_LOOKUP[current_tier]
    next_name = tier["next"]
    if next_name is None:
        return {
            "current": current_tier,
            "next": None,
            "progress_pct": 100.0,
            "remaining": 0.0,
            "gap": 0.0,
            "message": "You have reached Obsidian!",
        }

    next_tier = TIER_LOOKUP[next_name]
    gap = next_tier["threshold"] - tier["threshold"]
    if total_wagered is not None:
        total_wagered = _finite_number(total_wagered, "Total wagered")
        if total_wagered < 0:
            raise ValueError("Total wagered cannot be negative.")
        wagered_in_tier = max(0.0, total_wagered - tier["threshold"])
        progress_pct = min(100.0, wagered_in_tier / gap * 100) if gap > 0 else 100.0
    else:
        progress_pct = _finite_number(progress_pct or 0.0, "Progress")
        progress_pct = max(0.0, min(100.0, progress_pct))
        wagered_in_tier = progress_pct / 100 * gap

    remaining = max(0.0, gap - wagered_in_tier)
    costs = {name: remaining * edge for name, edge in EDGES.items()}
    return {
        "current": current_tier,
        "next": next_name,
        "progress_pct": progress_pct,
        "remaining": remaining,
        "gap": gap,
        "wagered_in_tier": wagered_in_tier,
        "costs": costs,
        "dice_spend": remaining * 0.01,
        "bet_size_10k": remaining / 10_000 * 1.02 if remaining > 0 else 0,
        "historical_bonus": tier["bonus"],
        "next_threshold": next_tier["threshold"],
    }


def _estimate_bonus(tier: str, wagered: float, net_result: float, monthly: bool) -> dict:
    if tier not in TIER_LOOKUP or tier == "Unranked":
        raise ValueError("Choose a valid VIP tier.")
    wagered = _finite_number(wagered, "Wagered amount")
    net_result = _finite_number(net_result, "Net result")
    if wagered < 0:
        raise ValueError("Wagered amount cannot be negative.")

    multiplier = TIER_LOOKUP[tier]["mult"] or 1.0
    base = wagered * (0.0028 if monthly else 0.0007) * multiplier
    if net_result < 0:
        base += abs(net_result) * (0.015 if monthly else 0.01) * multiplier
    elif net_result > 0:
        base -= min(base * 0.25, net_result * (0.003 if monthly else 0.002))

    return {
        "likely": max(0.0, base),
        "low": max(0.0, base * 0.75),
        "high": max(0.0, base * 1.60),
        "base_pct": (0.28 if monthly else 0.07) * multiplier,
        "tier": tier,
        "wagered": wagered,
        "net_result": net_result,
    }


def estimate_weekly_bonus(tier: str, wagered: float, net_result: float = 0.0) -> dict:
    return _estimate_bonus(tier, wagered, net_result, monthly=False)


def estimate_monthly_bonus(tier: str, wagered: float, net_result: float = 0.0) -> dict:
    return _estimate_bonus(tier, wagered, net_result, monthly=True)


def estimate_rakeback(wagered: float, edge: float = 0.01) -> dict:
    wagered = _finite_number(wagered, "Wagered amount")
    edge = _finite_number(edge, "House edge")
    if wagered < 0:
        raise ValueError("Wagered amount cannot be negative.")
    if not 0 <= edge <= 1:
        raise ValueError("House edge must be between 0 and 1.")
    return {"wagered": wagered, "edge": edge, "rakeback": wagered * edge * 0.035}


def convert_currency(amount: float, from_unit: str, to_unit: str) -> dict:
    amount = _finite_number(amount, "Amount")
    if amount < 0:
        raise ValueError("Amount cannot be negative.")
    if from_unit not in {"usd", "gc"} or to_unit not in {"usd", "gc"}:
        raise ValueError("Choose valid conversion units.")
    if from_unit == to_unit:
        converted = amount
    elif from_unit == "usd":
        converted = amount * 2_000_000
    else:
        converted = amount / 2_000_000
    return {
        "amount": amount,
        "from_unit": from_unit,
        "to_unit": to_unit,
        "result": converted,
    }


def dice98_calculator(required_wager: float, bankroll: float = 0, bet_count: int = 10_000) -> dict:
    required_wager = _finite_number(required_wager, "Required wager")
    bankroll = _finite_number(bankroll, "Bankroll")
    if required_wager <= 0:
        raise ValueError("Required wager must be greater than zero.")
    if bankroll < 0:
        raise ValueError("Bankroll cannot be negative.")
    if bet_count <= 0:
        raise ValueError("Number of bets must be greater than zero.")

    expected_cost = required_wager * 0.01
    return {
        "required_wager": required_wager,
        "bet_count": bet_count,
        "recommended_bet": required_wager / bet_count * 1.02,
        "expected_cost": expected_cost,
        "bankroll": bankroll,
        "expected_remaining": bankroll - expected_cost if bankroll > 0 else None,
        "edge": 0.01,
    }


def _build_vip_embed(result: dict) -> discord.Embed:
    if result.get("next") is None:
        return discord.Embed(
            title="Obsidian Reached!",
            description=result.get("message", ""),
            color=0x9B59B6,
        )

    embed = discord.Embed(
        title=f"VIP Progress — {result['current']} → {result['next']}",
        color=0x00FF9D,
    )
    embed.add_field(name="Progress", value=f"**{result['progress_pct']:.2f}%**", inline=True)
    embed.add_field(name="Remaining", value=f"**{format_money(result['remaining'])}**", inline=True)
    embed.add_field(name="Gap", value=format_money(result["gap"]), inline=True)
    cost_lines = [f"• {name}: **{format_money(value)}**" for name, value in result["costs"].items()]
    embed.add_field(name="Estimated Cost to Level", value="\n".join(cost_lines), inline=False)
    embed.add_field(
        name="Illustrative 10,000-bet figures",
        value=(
            f"Estimated cost at 1% edge: **{format_money(result['dice_spend'])}**\n"
            f"Bet size: **${result['bet_size_10k']:.2f}**"
        ),
        inline=False,
    )
    if result.get("historical_bonus"):
        embed.add_field(
            name="Historical Level-Up",
            value=f"≈ **${result['historical_bonus']}**",
            inline=False,
        )
    else:
        embed.add_field(name="Level-Up Bonus", value="Host-negotiated", inline=False)
    embed.set_footer(text="Estimates only; gambling outcomes and bonus amounts are not guaranteed.")
    return embed


def _build_bonus_embed(kind: str, result: dict) -> discord.Embed:
    color = 0xF1C40F if kind == "Weekly" else 0xE67E22
    embed = discord.Embed(title=f"Stake {kind} Bonus Estimate", color=color)
    embed.add_field(name="Tier", value=result["tier"], inline=True)
    embed.add_field(name="Wagered", value=format_money(result["wagered"]), inline=True)
    embed.add_field(
        name="Net Result",
        value=f"{'+' if result['net_result'] >= 0 else ''}{format_money(result['net_result'])}",
        inline=True,
    )
    embed.add_field(
        name="Estimate",
        value=(
            f"**Likely: {format_money(result['likely'])}**\n"
            f"Range: {format_money(result['low'])} – {format_money(result['high'])}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Notes",
        value="Community estimate only; the official Stake formula is private.",
        inline=False,
    )
    embed.set_footer(text="Estimates are not guaranteed.")
    return embed


def _load_preferences() -> dict:
    try:
        with PREFERENCES_FILE.open("r", encoding="utf-8") as file:
            preferences = json.load(file)
    except FileNotFoundError:
        return {}
    if not isinstance(preferences, dict):
        raise ValueError("Saved tier preferences must be a JSON object.")
    return preferences


def _save_preference(user_id: int, tier: str) -> None:
    preferences = _load_preferences()
    preferences[str(user_id)] = {"tier": tier}
    temporary_path = PREFERENCES_FILE.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(preferences, file, indent=2)
    temporary_path.replace(PREFERENCES_FILE)


class _ProgressModal(discord.ui.Modal, title="VIP Progress Input"):
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
        await interaction.response.send_message(embed=_build_vip_embed(result))


class _TierSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=tier, value=tier) for tier in TIER_NAMES]
        super().__init__(placeholder="Select current VIP tier…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_ProgressModal(self.values[0]))


class _VipDashboard(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(_TierSelect())

    @discord.ui.button(label="Show All Tiers", style=discord.ButtonStyle.secondary)
    async def show_tiers(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        lines = [
            f"**{tier['name']}** — {format_money(tier['threshold'])}"
            for tier in VIP_TIERS
        ]
        embed = discord.Embed(
            title="Stake VIP Tier Ladder",
            description="\n".join(lines),
            color=0x00FF9D,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class _BonusModal(discord.ui.Modal):
    wager = discord.ui.TextInput(label="Total Wagered ($)", placeholder="25000", required=True)
    result = discord.ui.TextInput(
        label="Net Profit/Loss (negative for loss)",
        placeholder="-1200 or 800",
        required=True,
    )

    def __init__(self, tier: str, kind: str):
        super().__init__(title=f"{kind} Bonus Calculator")
        self.tier = tier
        self.kind = kind

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            wagered = float(self.wager.value.replace(",", "").replace("$", ""))
            net = float(self.result.value.replace(",", "").replace("$", ""))
            estimate = (
                estimate_weekly_bonus(self.tier, wagered, net)
                if self.kind == "Weekly"
                else estimate_monthly_bonus(self.tier, wagered, net)
            )
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(embed=_build_bonus_embed(self.kind, estimate))


class _BonusTierSelect(discord.ui.Select):
    def __init__(self, kind: str):
        self.kind = kind
        options = [
            discord.SelectOption(label=tier, value=tier)
            for tier in TIER_NAMES
            if tier != "Unranked"
        ]
        super().__init__(placeholder=f"Select VIP tier for {kind}…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_BonusModal(self.values[0], self.kind))


class _BonusDashboard(discord.ui.View):
    def __init__(self, kind: str):
        super().__init__(timeout=300)
        self.add_item(_BonusTierSelect(kind))


def register_stake_calculator_commands(bot: commands.Bot) -> None:
    tier_choices = [app_commands.Choice(name=tier, value=tier) for tier in TIER_NAMES]
    bonus_tier_choices = [
        app_commands.Choice(name=tier, value=tier)
        for tier in TIER_NAMES
        if tier != "Unranked"
    ]

    @bot.tree.command(name="vip", description="Open the interactive VIP progress calculator")
    async def vip_dashboard(interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Stake VIP Progress Calculator",
            description="Select your current tier, then enter progress % or total wagered.",
            color=0x00FF9D,
        )
        await interaction.response.send_message(embed=embed, view=_VipDashboard())

    @bot.tree.command(name="weekly", description="Open the weekly bonus estimator")
    async def weekly_dashboard(interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Stake Weekly Bonus Estimator",
            description="Select your tier, then enter wager and net result.",
            color=0xF1C40F,
        )
        await interaction.response.send_message(embed=embed, view=_BonusDashboard("Weekly"))

    @bot.tree.command(name="monthly", description="Open the monthly bonus estimator")
    async def monthly_dashboard(interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Stake Monthly Bonus Estimator",
            description="Select your tier, then enter wager and net result.",
            color=0xE67E22,
        )
        await interaction.response.send_message(embed=embed, view=_BonusDashboard("Monthly"))

    @bot.tree.command(name="vip_calc", description="Calculate VIP progress directly")
    @app_commands.describe(tier="Current VIP tier", progress="Progress percent, or total wagered if over 100")
    @app_commands.choices(tier=tier_choices)
    async def vip_calc(interaction: discord.Interaction, tier: str, progress: float) -> None:
        try:
            result = calculate_vip_progress(
                tier,
                total_wagered=progress if progress > 100 else None,
                progress_pct=None if progress > 100 else progress,
            )
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(embed=_build_vip_embed(result))

    @bot.tree.command(name="weekly_calc", description="Estimate a weekly bonus")
    @app_commands.describe(tier="VIP tier", wagered="7-day wager", net_result="Net profit or loss")
    @app_commands.choices(tier=bonus_tier_choices)
    async def weekly_calc(
        interaction: discord.Interaction,
        tier: str,
        wagered: float,
        net_result: float = 0.0,
    ) -> None:
        try:
            result = estimate_weekly_bonus(tier, wagered, net_result)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(embed=_build_bonus_embed("Weekly", result))

    @bot.tree.command(name="monthly_calc", description="Estimate a monthly bonus")
    @app_commands.describe(tier="VIP tier", wagered="Period wager", net_result="Net profit or loss")
    @app_commands.choices(tier=bonus_tier_choices)
    async def monthly_calc(
        interaction: discord.Interaction,
        tier: str,
        wagered: float,
        net_result: float = 0.0,
    ) -> None:
        try:
            result = estimate_monthly_bonus(tier, wagered, net_result)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(embed=_build_bonus_embed("Monthly", result))

    @bot.tree.command(name="rakeback", description="Estimate rakeback from wager and house edge")
    @app_commands.describe(wagered="Amount wagered", edge="House edge as a decimal (default 0.01)")
    async def rakeback(
        interaction: discord.Interaction,
        wagered: float,
        edge: float = 0.01,
    ) -> None:
        try:
            result = estimate_rakeback(wagered, edge)
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
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="set_tier", description="Save your preferred VIP tier")
    @app_commands.describe(tier="Your current VIP tier")
    @app_commands.choices(tier=tier_choices)
    async def set_tier(interaction: discord.Interaction, tier: str) -> None:
        try:
            _save_preference(interaction.user.id, tier)
        except (OSError, ValueError, json.JSONDecodeError):
            logger.exception("Could not save preferred VIP tier.")
            await interaction.response.send_message(
                "Could not save your tier preference. Check the bot's data file and try again.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Preferred tier set to **{tier}**.",
            ephemeral=True,
        )

    @bot.tree.command(name="my_tier", description="Show your saved VIP tier")
    async def my_tier(interaction: discord.Interaction) -> None:
        try:
            saved_preferences = _load_preferences().get(str(interaction.user.id), {})
            tier = saved_preferences.get("tier") if isinstance(saved_preferences, dict) else None
        except (OSError, ValueError, json.JSONDecodeError):
            logger.exception("Could not load preferred VIP tier.")
            await interaction.response.send_message(
                "Could not load your saved tier. Check the bot's data file and try again.",
                ephemeral=True,
            )
            return
        if not isinstance(tier, str) or tier not in TIER_LOOKUP:
            await interaction.response.send_message(
                "No valid saved tier. Use `/set_tier` to save one.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Your saved tier is **{tier}**.",
            ephemeral=True,
        )

    @bot.tree.command(name="convert", description="Convert between USD/SC and Gold Coins")
    @app_commands.choices(
        from_unit=[
            app_commands.Choice(name="USD / SC", value="usd"),
            app_commands.Choice(name="Gold Coins (GC)", value="gc"),
        ],
        to_unit=[
            app_commands.Choice(name="USD / SC", value="usd"),
            app_commands.Choice(name="Gold Coins (GC)", value="gc"),
        ],
    )
    async def convert(
        interaction: discord.Interaction,
        amount: float,
        from_unit: str,
        to_unit: str,
    ) -> None:
        try:
            result = convert_currency(amount, from_unit, to_unit)
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
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="dice98", description="Estimate bet size for a wagering target")
    @app_commands.describe(
        required_wager="Total wager volume",
        bankroll="Current bankroll (optional)",
        bets="Number of bets to spread over (default 10,000)",
    )
    async def dice98(
        interaction: discord.Interaction,
        required_wager: float,
        bankroll: float = 0.0,
        bets: int = 10_000,
    ) -> None:
        try:
            result = dice98_calculator(required_wager, bankroll, bets)
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
        embed.set_footer(text="Illustration only; outcomes are random and losses may exceed this estimate.")
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="vip_tiers", description="Show the full Stake VIP tier ladder")
    async def vip_tiers(interaction: discord.Interaction) -> None:
        lines = [
            f"**{tier['name']}** — {format_money(tier['threshold'])}"
            for tier in VIP_TIERS
        ]
        embed = discord.Embed(
            title="Stake VIP Tier Ladder",
            description="\n".join(lines),
            color=0x00FF9D,
        )
        embed.set_footer(text="Thresholds are informational and may change.")
        await interaction.response.send_message(embed=embed)

    from stake_dashboard import register_tools_dashboard

    register_tools_dashboard(bot)
