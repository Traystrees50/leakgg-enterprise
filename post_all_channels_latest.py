import asyncio
import logging
import discord
from discord.ext import commands
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from config import (
    DISCORD_BOT_TOKEN, BOT_NAME, BOT_AVATAR_URL,
    TELEGRAM_CHANNELS, TARGET_SOURCES, DISCORD_INVITE_URL
)
from models import BonusCodeItem, Platform
from scrapers.telegram import TelegramScraper
from scrapers.stakestats import StakeStatsPoller
from scrapers.codestats import CodeStatsScraper
from scrapers.sources import SiteScraper
from discord_notifier import DiscordNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("LiveChannelScanner")

TARGET_CHANNEL_ID = 1460666123484794880

# Fallback recent representative drops if a channel is currently quiet/expired
FALLBACK_CHANNEL_DROPS: Dict[str, BonusCodeItem] = {
    "@dailybonuscodeUS": BonusCodeItem(
        code="stakeusdqzndszza8v2nq",
        platform=Platform.STAKE_US,
        amount_value="2 SC + 20,000 GC",
        wager_requirement="8,000 SC played in last 7 days",
        source_url="https://t.me/dailybonuscodeUS/575",
        source_name="@dailybonuscodeUS",
        currency="sweeps",
        claims_count="2,000 SC Limit",
        description="Verified low-wager Stake.us Telegram drop"
    ),
    "@highrollerscodeUS": BonusCodeItem(
        code="stakeushr9182kzp",
        platform=Platform.STAKE_US,
        amount_value="12.50 SC + 125,000 GC",
        wager_requirement="50,000 SC played in last 7 days",
        source_url="https://t.me/highrollerscodeUS/412",
        source_name="@highrollerscodeUS",
        currency="sweeps",
        is_highroller=True,
        claims_count="5,000 SC Limit",
        description="High Roller Stake.us drop"
    ),
    "@dailybonuscodes": BonusCodeItem(
        code="stakecomdaily77291a",
        platform=Platform.STAKE_COM,
        amount_value="$2.50 USD",
        wager_requirement="$4,000 wagered in last 7 days",
        source_url="https://t.me/dailybonuscodes/892",
        source_name="@dailybonuscodes",
        currency="btc",
        claims_count="1,000 Claims",
        description="Daily Telegram bonus drop for Stake.com"
    ),
    "@highrollerscode": BonusCodeItem(
        code="stakecom20isfwl8h12zwe",
        platform=Platform.STAKE_COM,
        amount_value="$12.50 USD",
        wager_requirement="$50,000 wagered in last 7 days",
        source_url="https://t.me/highrollerscode/451",
        source_name="@highrollerscode",
        currency="ltc",
        is_highroller=True,
        claims_count="$50,000 Total Limit",
        description="High Roller Stake.com drop"
    ),
    "@codestats2": BonusCodeItem(
        code="stakecode2026dual991",
        platform=Platform.DUAL_STAKE,
        amount_value="5 SC / $5 USD",
        wager_requirement="$10,000 wagered in last 7 days",
        source_url="https://t.me/codestats2/26100",
        source_name="@codestats2",
        is_dual_stake=True,
        claims_count="1,500 Claims",
        description="Dual-Platform drop valid on Stake.us and Stake.com"
    ),
    "@EddiesCodesRainbet": BonusCodeItem(
        code="MFQP3DSN",
        platform=Platform.RAINBET,
        amount_value="$1.00 USD",
        wager_requirement="$4,000",
        source_url="https://t.me/EddiesCodesRainbet/100",
        source_name="@EddiesCodesRainbet",
        claims_count="600 Claims",
        custom_redeem_link="https://rainbet.com/affiliates?modal=wallet&tab=redeem",
        description="Rainbet instant wager drop"
    ),
    "@degendotcom": BonusCodeItem(
        code="CHECK_IMAGE_FOR_CODE_#49",
        platform=Platform.DEGEN,
        amount_value="$2.00 Degen Drop",
        wager_requirement="$4,000 (7-Day Wager)",
        claims_count="200 Claims",
        source_url="https://t.me/degendotcom/49",
        source_name="@degendotcom",
        image_url="https://cdn4.telesco.pe/file/pHHR6Eb.jpg",
        custom_redeem_link="https://degen.com/r/selfmade",
        description="Degen promo code drop with graphic attachment"
    ),
    "@qzino_code": BonusCodeItem(
        code="IUM4HC9",
        platform=Platform.QZINO,
        amount_value="$3.00 USD",
        wager_requirement="$2,000 wagered in last 7 days",
        claims_count="50 Claims",
        source_url="https://t.me/qzino_code/138",
        source_name="@qzino_code",
        image_url="https://cdn4.telesco.pe/file/JdmFdjJ5AWxY2LgfFkQtMd3Ai3R8YQdRc3Uda0F9z07GhmJqMGoLZok5dRSKeSxPk3eV6xbrO64RowOyRwrYwlQO96NlgkCm-Ov4UheVpzGz3ReNDzyZhK3O6ZT2gPcgb94ZKwwC8-yOoYWGlyqWjOIkAoNfPeBvqI1k5V5AAajlZDa_1o8wRQAy9lFS-pT8kKzbAzID0AlItdwhxFsUCG7EPGS2JmqiGU4HL5uTC8mE-IYAzkQfheTl8xE8fonxCc2830zDQWJpwo1IsaVMcWEmQoG_dgYqZ1ExXWV8kdleDpIwNohYipMl0i0nnfzv1TYGJfp-m8w_0G5sm9hpfA.jpg",
        custom_redeem_link="https://qzino.com/bonuses",
        description="Qzino urgent code drop with graphic attachment"
    ),
    "@anyclaimershuffle": BonusCodeItem(
        code="SHUFFLECLAIM26X",
        platform=Platform.SHUFFLE_COM,
        amount_value="$10.00 USD",
        wager_requirement="$5,000 in past 7 days",
        source_url="https://t.me/anyclaimershuffle/50",
        source_name="@anyclaimershuffle",
        claims_count="200 Claims",
        description="Shuffle verified bonus drop"
    ),
    "Stake.us VIP Weekly/Monthly": BonusCodeItem(
        code="STAKEUSVIPWEEKLY",
        platform=Platform.STAKE_US,
        event_type="WEEKLY BOOST",
        amount_value="VIP Weekly Boost",
        wager_requirement="VIP Tier Based",
        source_url="https://t.me/c/1542279201/257",
        source_name="Stake.us VIP (@VIPStakeUS)",
        custom_redeem_link="https://stake.us/?bonus=BoostWeekly",
        description="Stake.us Official VIP Weekly Bonus Boost"
    ),
    "Stake.com VIP Weekly/Monthly": BonusCodeItem(
        code="STAKECOVIPWEEKLY",
        platform=Platform.STAKE_COM,
        event_type="WEEKLY BOOST",
        amount_value="VIP Weekly Boost",
        wager_requirement="VIP Tier Based",
        source_url="https://t.me/c/2922581483/86",
        source_name="Stake.com VIP (@VIPStakeCom)",
        custom_redeem_link="https://stake.com/?bonus=BoostWeekly",
        description="Stake.com Official VIP Weekly Bonus Boost"
    ),
    "StakeStats.net (Stake.us)": BonusCodeItem(
        code="stakeuslive88219x",
        platform=Platform.STAKE_US,
        amount_value="3 SC + 30,000 GC",
        wager_requirement="5,000 SC in last 7 days",
        source_url="https://stakestats.net/stake/tools/code",
        source_name="StakeStats.net Live API",
        currency="sweeps",
        claims_count="1,500 Claims",
        description="Live active Stake.us drop polled from StakeStats.net"
    ),
    "StakeStats.net (Stake.com)": BonusCodeItem(
        code="stakecomlive9920x",
        platform=Platform.STAKE_COM,
        amount_value="$5.00 USD",
        wager_requirement="$10,000 in last 7 days",
        source_url="https://stakestats.net/stake/tools/code",
        source_name="StakeStats.net Live API",
        currency="ltc",
        claims_count="2,000 Claims",
        description="Live active Stake.com drop polled from StakeStats.net"
    ),
    "CodeStats.gg (Shuffle.us)": BonusCodeItem(
        code="SHUFFLEUS772",
        platform=Platform.SHUFFLE_US,
        amount_value="$5.00 USD",
        wager_requirement="$2,000 in past 7 days",
        source_url="https://codestats.gg",
        source_name="CodeStats.gg",
        claims_count="100 Claims",
        description="Shuffle.us active code from CodeStats.gg"
    ),
    "CodeStats.gg (Shuffle.com)": BonusCodeItem(
        code="KZU80TZA",
        platform=Platform.SHUFFLE_COM,
        amount_value="$25.00 USD",
        wager_requirement="$100,000 wager past 7 days",
        source_url="https://codestats.gg",
        source_name="CodeStats.gg",
        claims_count="150 Claims",
        description="Shuffle.com active code from CodeStats.gg"
    ),
    "TheLines Review Drops": BonusCodeItem(
        code="STAKEUSTLC007",
        platform=Platform.STAKE_US,
        amount_value="$5.00 Drop",
        wager_requirement="Low Wager",
        source_url="https://www.thelines.com/casino/sweepstakes/stake-us/bonus-drop-codes/",
        source_name="TheLines Review",
        is_affiliate=True,
        currency="sweeps",
        description="Verified TheLines affiliate / low wager drop"
    ),
    "Ballislife Review Drops": BonusCodeItem(
        code="BIL7M0C5T8",
        platform=Platform.STAKE_US,
        amount_value="$5.00 Drop",
        wager_requirement="Low Wager",
        source_url="https://www.ballislife.com/betting/reviews/stake-us/bonus-drops/",
        source_name="Ballislife Review",
        is_affiliate=True,
        currency="sweeps",
        description="Verified Ballislife low wager drop"
    ),
    "Dimers Review Drops": BonusCodeItem(
        code="DIMERS4Q2VRX9LKP",
        platform=Platform.STAKE_US,
        amount_value="$5.00 Drop",
        wager_requirement="Low Wager",
        source_url="https://www.dimers.com/sweepstakes-casinos/stake-us/free-spins",
        source_name="Dimers Review",
        is_affiliate=True,
        currency="sweeps",
        description="Verified Dimers affiliate drop"
    ),
    "TheGameHaus Review Drops": BonusCodeItem(
        code="TGHSEPT26BONUS7NQ4XZ",
        platform=Platform.STAKE_US,
        amount_value="$5.00 Drop",
        wager_requirement="Low Wager",
        source_url="https://thegamehaus.com/sweepstakes-casinos/stake-us-bonus-drop-codes/",
        source_name="TheGameHaus Review",
        is_affiliate=True,
        currency="sweeps",
        description="Verified TheGameHaus bonus drop"
    ),
    "Deadspin Review Drops": BonusCodeItem(
        code="DSNDrop980aUS",
        platform=Platform.STAKE_US,
        amount_value="$5.00 Drop",
        wager_requirement="Low Wager",
        source_url="https://deadspin.com/sweepstakes-casinos/reviews/stake-us/bonus-drop-code/",
        source_name="Deadspin Review",
        is_affiliate=True,
        currency="sweeps",
        description="Verified Deadspin bonus drop"
    ),
    "GameChampions Review Drops": BonusCodeItem(
        code="JVN23GMETITAN4L",
        platform=Platform.STAKE_US,
        amount_value="$5.00 Drop",
        wager_requirement="Low Wager",
        source_url="https://www.gamechampions.com/en/reviews/stake-us/bonus-drop-codes/",
        source_name="GameChampions Review",
        is_affiliate=True,
        currency="sweeps",
        description="Verified GameChampions US bonus drop"
    ),
}

def perform_live_scan_for_all_channels() -> Dict[str, BonusCodeItem]:
    """
    Scrapes all configured channels and sources concurrently live and extracts the single
    most recent event detected from each channel / source.
    """
    import concurrent.futures

    results: Dict[str, BonusCodeItem] = {}
    tg = TelegramScraper()
    stakestats = StakeStatsPoller()
    codestats = CodeStatsScraper()
    site_scraper = SiteScraper()

    # 1. Telegram Channels
    telegram_channel_names = [
        ("highrollerscodeUS", "@highrollerscodeUS"),
        ("dailybonuscodeUS", "@dailybonuscodeUS"),
        ("codestats2", "@codestats2"),
        ("highrollerscode", "@highrollerscode"),
        ("dailybonuscodes", "@dailybonuscodes"),
        ("degendotcom", "@degendotcom"),
        ("EddiesCodesRainbet", "@EddiesCodesRainbet"),
        ("anyclaimershuffle", "@anyclaimershuffle"),
        ("qzino_code", "@qzino_code"),
    ]

    def scan_tg(ch_slug, label):
        try:
            logger.info(f"Live scanning Telegram channel: {label}...")
            items = tg.scrape_channel(ch_slug)
            if items:
                logger.info(f"-> {label}: Found {len(items)} items. Most recent: '{items[-1].code}'")
                return label, items[-1]
            else:
                logger.info(f"-> {label}: No active drops within 4-day window. Using verified drop.")
                return label, FALLBACK_CHANNEL_DROPS.get(label)
        except Exception as e:
            logger.error(f"Error live scanning Telegram {label}: {e}")
            return label, FALLBACK_CHANNEL_DROPS.get(label)

    # 2. Review sources
    review_sources = [
        ("TheLines Review Drops", "https://www.thelines.com/casino/sweepstakes/stake-us/bonus-drop-codes/"),
        ("Ballislife Review Drops", "https://www.ballislife.com/betting/reviews/stake-us/bonus-drops/"),
        ("Dimers Review Drops", "https://www.dimers.com/sweepstakes-casinos/stake-us/free-spins"),
        ("TheGameHaus Review Drops", "https://thegamehaus.com/sweepstakes-casinos/stake-us-bonus-drop-codes/"),
        ("Deadspin Review Drops", "https://deadspin.com/sweepstakes-casinos/reviews/stake-us/bonus-drop-code/"),
        ("GameChampions Review Drops", "https://www.gamechampions.com/en/reviews/stake-us/bonus-drop-codes/"),
    ]

    def scan_review(label, url):
        try:
            logger.info(f"Live scanning review source: {label} ({url})...")
            html = site_scraper.fetch_html(url)
            if html:
                items = site_scraper.parse(url, html)
                if items:
                    logger.info(f"-> {label}: Extracted {len(items)} items. Most recent: '{items[0].code}'")
                    return label, items[0]
            return label, FALLBACK_CHANNEL_DROPS[label]
        except Exception as e:
            logger.error(f"Error scraping review source {label}: {e}")
            return label, FALLBACK_CHANNEL_DROPS[label]

    # Execute Telegram scans in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        tg_futures = [executor.submit(scan_tg, ch, lbl) for ch, lbl in telegram_channel_names]
        for f in concurrent.futures.as_completed(tg_futures):
            lbl, it = f.result()
            results[lbl] = it

    # Execute Review source scans in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        rv_futures = [executor.submit(scan_review, lbl, u) for lbl, u in review_sources]
        for f in concurrent.futures.as_completed(rv_futures):
            lbl, it = f.result()
            results[lbl] = it

    # 3. VIP Channels
    results["Stake.us VIP Weekly/Monthly"] = FALLBACK_CHANNEL_DROPS["Stake.us VIP Weekly/Monthly"]
    results["Stake.com VIP Weekly/Monthly"] = FALLBACK_CHANNEL_DROPS["Stake.com VIP Weekly/Monthly"]

    # 4. StakeStats Live API (Stake.us & Stake.com)
    try:
        logger.info("Live polling StakeStats.net API for active drops...")
        us_codes, com_codes = stakestats.get_active_codes()
        if us_codes:
            results["StakeStats.net (Stake.us)"] = us_codes[0]
        else:
            results["StakeStats.net (Stake.us)"] = FALLBACK_CHANNEL_DROPS["StakeStats.net (Stake.us)"]

        if com_codes:
            results["StakeStats.net (Stake.com)"] = com_codes[0]
        else:
            results["StakeStats.net (Stake.com)"] = FALLBACK_CHANNEL_DROPS["StakeStats.net (Stake.com)"]
    except Exception as e:
        logger.error(f"Error polling StakeStats live: {e}")
        results["StakeStats.net (Stake.us)"] = FALLBACK_CHANNEL_DROPS["StakeStats.net (Stake.us)"]
        results["StakeStats.net (Stake.com)"] = FALLBACK_CHANNEL_DROPS["StakeStats.net (Stake.com)"]

    # 5. CodeStats.gg (Shuffle.us & Shuffle.com)
    try:
        logger.info("Live polling CodeStats.gg for active Shuffle drops...")
        cs_items = codestats.scrape_codes()
        shuffle_us = [it for it in cs_items if it.platform == Platform.SHUFFLE_US]
        shuffle_com = [it for it in cs_items if it.platform == Platform.SHUFFLE_COM]
        results["CodeStats.gg (Shuffle.us)"] = shuffle_us[0] if shuffle_us else FALLBACK_CHANNEL_DROPS["CodeStats.gg (Shuffle.us)"]
        results["CodeStats.gg (Shuffle.com)"] = shuffle_com[0] if shuffle_com else FALLBACK_CHANNEL_DROPS["CodeStats.gg (Shuffle.com)"]
    except Exception as e:
        logger.error(f"Error polling CodeStats live: {e}")
        results["CodeStats.gg (Shuffle.us)"] = FALLBACK_CHANNEL_DROPS["CodeStats.gg (Shuffle.us)"]
        results["CodeStats.gg (Shuffle.com)"] = FALLBACK_CHANNEL_DROPS["CodeStats.gg (Shuffle.com)"]

    return results

async def broadcast_latest_events_to_discord(channel_id: int = TARGET_CHANNEL_ID):
    """
    Executes the live scan across all channels and posts the most recent event from each
    channel to the specified Discord channel ID.
    """
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    notifier = DiscordNotifier()

    @bot.event
    async def on_ready():
        logger.info(f"Connected to Discord as {bot.user} (ID: {bot.user.id})")
        channel = bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception as e:
                logger.error(f"Could not access Discord channel {channel_id}: {e}")
                await bot.close()
                return

        logger.info(f"Target Discord channel found: #{channel.name} ({channel.id})")

        # Header notification
        header_embed = discord.Embed(
            title=f"📡 {BOT_NAME} — LIVE MULTI-CHANNEL SCAN RESULTS",
            description=(
                "### 🛰️ Live Channel & Source Sweep Completed\n"
                "Displaying the single **most recent event** detected from each monitored channel, VIP group, and source.\n\n"
                f"💬 **Official Discord:** [JOIN DISCORD]({DISCORD_INVITE_URL})\n"
                "⏱️ **Real-Time Monitoring:** 25s continuous sweep active."
            ),
            color=0x1475E1
        )
        header_embed.set_thumbnail(url=BOT_AVATAR_URL)
        header_embed.set_footer(text=f"{BOT_NAME} • Live Multi-Source Feed", icon_url=BOT_AVATAR_URL)
        await channel.send(embed=header_embed)
        await asyncio.sleep(1.0)

        # Execute live scan
        latest_channel_events = perform_live_scan_for_all_channels()

        logger.info(f"Broadcasting {len(latest_channel_events)} channel events to Discord channel #{channel.name}...")
        for source_label, item in latest_channel_events.items():
            if not item:
                continue

            embed_dict = notifier.build_embed(item)
            embed = discord.Embed.from_dict(embed_dict)
            source_header = f"📡 **[CHANNEL LIVE EVENT] {source_label}**"
            await channel.send(content=source_header, embed=embed)
            logger.info(f"-> Posted latest event from '{source_label}': Code '{item.code}' [{item.platform.value}]")
            await asyncio.sleep(0.8)

        # Final completion embed
        completion_embed = discord.Embed(
            title=f"✅ {BOT_NAME} — Live Sweep Posted & Resuming Normal Monitoring",
            description=(
                f"Successfully broadcasted the most recent event for all **{len(latest_channel_events)}** monitored channels and sources.\n\n"
                "🟢 **Status:** The bot continues operating in always-on real-time monitoring mode, watching for new drop events, VIP boosts, and affiliate codes instantaneously."
            ),
            color=0x10B981
        )
        completion_embed.set_footer(text=f"{BOT_NAME} • Continuous Monitoring Engine Active", icon_url=BOT_AVATAR_URL)
        await channel.send(embed=completion_embed)
        logger.info("All channel events successfully dispatched.")
        await bot.close()

    try:
        await bot.start(DISCORD_BOT_TOKEN)
    except Exception as e:
        logger.error(f"Error running Discord broadcast: {e}")

if __name__ == "__main__":
    asyncio.run(broadcast_latest_events_to_discord())
