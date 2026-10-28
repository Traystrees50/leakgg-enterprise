import sys
import os
import time
import signal
import logging
import argparse
import asyncio
from typing import List
from dotenv import load_dotenv

# Ensure we run from the script's directory so config/state files are found
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Use SelectorEventLoop on Windows to avoid ProactorEventLoop issues with threaded I/O
# (discord.py gateway heartbeat can cause crashes with ProactorEventLoop)
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except (DeprecationWarning, RuntimeError):
        pass

from config import (
    BOT_NAME, CHECK_INTERVAL_SECONDS, DISCORD_WEBHOOK_URL,
    DISCORD_WEBHOOK_STAKE_COM, DISCORD_WEBHOOK_STAKE_US, STATE_FILE_PATH,
    DISCORD_BOT_TOKEN
)
from models import BonusCodeItem, Platform
from tracker import CodeTracker
from dashboard_manager import DashboardManager
from discord_notifier import DiscordNotifier
from scrapers.engine import ScraperEngine
from scrapers.stakestats import StakeStatsPoller
from scrapers.telegram import TelegramScraper
from scrapers.validator import StakeCodeValidator
from health_monitor import HealthMonitor
from discord_bot import run_discord_bot

# Ensure UTF-8 output on Windows terminal
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Configure logging to both stdout and bot_runtime.log
_file_handler = logging.FileHandler("bot_runtime.log", encoding="utf-8", delay=True)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
    handlers=[logging.StreamHandler(sys.stdout), _file_handler]
)
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.client").setLevel(logging.WARNING)
logger = logging.getLogger("LeakedGG.Bot")

running = True

def handle_sigint(signum, frame):
    global running
    logger.info("Shutdown signal received. Stopping Leaked.GG Code Monitoring bot gracefully...")
    running = False

signal.signal(signal.SIGINT, handle_sigint)
try:
    signal.signal(signal.SIGTERM, handle_sigint)
except AttributeError:
    pass

def cmd_poll_stakestats(notify: bool = False):
    logger.info("=== Polling StakeStats.net Live Active Codes ===")
    poller = StakeStatsPoller()
    active_us, active_com = poller.get_active_codes()
    notifier = DiscordNotifier()

    print("\n" + "=" * 80)
    print(f" 🇺🇸 STAKE.US ACTIVE DROPS ({len(active_us)} Active Codes Detected)")
    print("=" * 80)
    for c in active_us:
        hr = "🔥 [HIGHROLLER] " if c.is_highroller else ""
        print(f" • {hr}Code: {c.code}")
        print(f"   Value:       {c.amount_value}")
        print(f"   Wager Req:   {c.wager_requirement}")
        print(f"   Redeem Link: {c.redeem_link}")
        print(f"   Signup Link: {c.affiliate_signup_link}")
        print("-" * 80)

    print("\n" + "=" * 80)
    print(f" 🌏 STAKE.COM ACTIVE DROPS ({len(active_com)} Active Codes Detected)")
    print("=" * 80)
    for c in active_com:
        hr = "🔥 [HIGHROLLER] " if c.is_highroller else ""
        print(f" • {hr}Code: {c.code}")
        print(f"   Value:       {c.amount_value}")
        print(f"   Wager Req:   {c.wager_requirement}")
        print(f"   Redeem Link: {c.redeem_link}")
        print(f"   Signup Link: {c.affiliate_signup_link}")
        print("-" * 80)

    if notify:
        for c in active_us + active_com:
            notifier.send_notification(c)

def cmd_poll_telegram(notify: bool = False):
    logger.info("=== Polling Monitored Telegram Drop Channels ===")
    tg_scraper = TelegramScraper()
    items = tg_scraper.scrape_all_channels()
    notifier = DiscordNotifier()

    print("\n" + "=" * 80)
    print(f" TELEGRAM DROPS DETECTED ({len(items)} Items Found)")
    print("=" * 80)
    for c in items:
        hr = "🔥 [HIGHROLLER] " if c.is_highroller else ""
        print(f" • [{c.platform.value}] {hr}Code: {c.code}")
        print(f"   Value:       {c.amount_value}")
        print(f"   Wager Req:   {c.wager_requirement}")
        if c.claims_count:
            print(f"   Claims:      {c.claims_count}")
        print(f"   Redeem Link: {c.redeem_link}")
        print(f"   Source:      {c.source_name} ({c.source_url})")
        if c.image_url:
            print(f"   Media:       {c.image_url}")
        print("-" * 80)

    if notify:
        for c in items:
            notifier.send_notification(c)

def cmd_check_once(notify: bool = False):
    logger.info(f"=== {BOT_NAME} - Multi-Source Scan ===")
    tracker = CodeTracker(STATE_FILE_PATH)
    notifier = DiscordNotifier()
    engine = ScraperEngine(tracker=tracker, notifier=notifier, code_validator=StakeCodeValidator())
    
    new_codes = engine.run_check(notify=notify)
    print("\n" + "=" * 80)
    print(f" SCAN COMPLETED: {len(new_codes)} new bonus codes detected")
    print("=" * 80)
    for c in new_codes:
        hr = "🔥 [HIGHROLLER] " if c.is_highroller else ""
        print(f" • [{c.platform.value}] {hr}Code: {c.code}")
        print(f"   Amount / Value: {c.amount_value}")
        print(f"   Wager Req:      {c.wager_requirement}")
        print(f"   Redeem Link:    {c.redeem_link}")
        print(f"   Signup Link:    {c.affiliate_signup_link}")
        print(f"   Source:         {c.source_name} ({c.source_url})")
        print("-" * 80)

def cmd_run():
    if DISCORD_BOT_TOKEN:
        logger.info(f"=== Starting {BOT_NAME} Discord Bot & Always-On Real-Time Daemon ===")
        run_discord_bot()
    else:
        manager = DashboardManager()
        interval = manager.get_setting("check_interval_seconds", CHECK_INTERVAL_SECONDS)
        logger.info(f"=== Starting {BOT_NAME} Webhook Daemon (Always-On Real-Time Monitoring) ===")
        logger.info(f"Check Interval: {interval} seconds")
        logger.info(f"State File: {STATE_FILE_PATH}")
        
        tracker = CodeTracker(STATE_FILE_PATH)
        notifier = DiscordNotifier(dashboard_manager=manager)
        engine = ScraperEngine(tracker=tracker, notifier=notifier, code_validator=StakeCodeValidator())

        while running:
            interval = manager.get_setting("check_interval_seconds", CHECK_INTERVAL_SECONDS)
            is_enabled = manager.get_setting("realtime_monitoring_enabled", True)

            if is_enabled:
                logger.info("Initiating scheduled real-time bonus code monitoring sweep...")
                try:
                    new_codes = engine.run_check(notify=True)
                    if new_codes:
                        logger.info(f"✅ Sweep complete. Found and broadcasted {len(new_codes)} new codes.")
                    else:
                        logger.info("Sweep complete. No new unannounced codes detected.")
                except Exception as e:
                    logger.error(f"Error during scan loop: {e}", exc_info=True)
            else:
                logger.info("Realtime monitoring is currently PAUSED via Dashboard. Sleeping...")

            logger.info(f"Sleeping for {interval} seconds until next scan...")
            slept = 0
            while running and slept < interval:
                time.sleep(1)
                slept += 1

        logger.info("Bot execution finished.")

def cmd_test_discord():
    logger.info(f"=== Sending Test Embeds for All Platforms to Discord Webhook ===")
    notifier = DiscordNotifier()

    sample_items = [
        BonusCodeItem(
            code="LEAKEDVIPCOM",
            platform=Platform.STAKE_COM,
            amount_value="200% Deposit Match up to $3,000 + 10% Rakeback",
            wager_requirement="40x Rollover on Deposit Bonus",
            source_url="https://stake.com",
            source_name="Leaked.GG VIP",
            is_affiliate=True,
            currency="ltc",
            description="Verified exclusive VIP partner bonus"
        ),
        BonusCodeItem(
            code="stakeusdqzndszza8v2nq",
            platform=Platform.STAKE_US,
            amount_value="2 SC + 20,000 GC",
            wager_requirement="8,000 SC played in last 7 days",
            source_url="https://t.me/dailybonuscodeUS/575",
            source_name="@dailybonuscodeUS",
            is_affiliate=False,
            is_highroller=False,
            currency="sweeps",
            claims_count="2,000 SC Limit",
            description="Fresh Stake.us low wager drop code"
        ),
        BonusCodeItem(
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
            description="High Roller Stake.com drop"
        ),
        BonusCodeItem(
            code="KZU80TZA",
            platform=Platform.SHUFFLE_COM,
            amount_value="$25.00 USD",
            wager_requirement="$100,000 wager past 7 days",
            source_url="https://t.me/codestats2/26027",
            source_name="@codestats2",
            is_affiliate=False,
            claims_count="150 Claims",
            description="Shuffle.com verified bonus drop"
        ),
        BonusCodeItem(
            code="NK60ZYU0",
            platform=Platform.SHUFFLE_US,
            amount_value="1.5 SC + 15,000 GC",
            wager_requirement="2,500 SC played in last 7 days",
            source_url="https://t.me/codestats2/26029",
            source_name="@codestats2",
            is_affiliate=False,
            claims_count="500 Claims",
            description="Shuffle.us social casino drop"
        ),
        BonusCodeItem(
            code="MFQP3DSN",
            platform=Platform.RAINBET,
            amount_value="$10.00",
            wager_requirement="$4,000 Wager Required",
            source_url="https://t.me/EddiesCodesRainbet/2083",
            source_name="@EddiesCodesRainbet",
            is_affiliate=False,
            claims_count="600 Claims",
            description="Rainbet instant drop code"
        ),
        BonusCodeItem(
            code="DEGENVIP88",
            platform=Platform.DEGEN,
            amount_value="$5.00 Bonus Drop",
            wager_requirement="$2,500 Wager",
            source_url="https://t.me/degendotcom",
            source_name="@degendotcom",
            is_affiliate=False,
            image_url="https://i.imgur.com/8Q9Z5bF.png",
            description="Degen drop with media verification"
        ),
        BonusCodeItem(
            code="QZINOMAX",
            platform=Platform.QZINO,
            amount_value="100% Match + AI Rakeback",
            wager_requirement="10x Playthrough",
            source_url="https://qzino.ai",
            source_name="Qzino AI",
            is_affiliate=True,
            description="Exclusive Qzino promotion"
        ),
        BonusCodeItem(
            code="mjp6axxg",
            platform=Platform.DUAL_STAKE,
            amount_value="$3.00 (US & COM)",
            wager_requirement="$6,000 Played in last 7 days",
            source_url="https://t.me/codestats2/26044",
            source_name="@codestats2",
            is_affiliate=False,
            is_dual_stake=True,
            description="Dual Stake code valid on both Stake.us and Stake.com"
        )
    ]

    for item in sample_items:
        print(f"\n--- Sending {item.platform.value} Embed ({hex(item.platform.embed_color)}) ---")
        res = notifier.send_notification(item)
        print(f"{item.platform.value} notification sent: {res}")

def cmd_list_seen():
    tracker = CodeTracker(STATE_FILE_PATH)
    all_seen = tracker.get_all()
    print(f"\nTracked Bonus Codes in {STATE_FILE_PATH} ({len(all_seen)} total):\n")
    for item in all_seen:
        print(f"[{item.get('platform', 'Unknown')}] Code: {item.get('code')} | Value: {item.get('amount_value')} | Detected: {item.get('detected_at')}")
        print(f"  Redeem: {item.get('redeem_link')}")
        print(f"  Source: {item.get('source_url')}")
        print("-" * 60)

def cmd_health():
    logger.info("=== Running Enterprise Health Diagnostic Check ===")
    health_mon = HealthMonitor()
    report = health_mon.get_full_health_report()
    
    print("\n" + "=" * 80)
    print(f" 🩺 LEAKED.GG ENTERPRISE HEALTH DIAGNOSTIC REPORT")
    print(f" Status: {report['overall_status']} | Snapshot: {report['timestamp']}")
    print("=" * 80)
    
    sys_info = report["system"]
    print(f" • [System]  Uptime: {sys_info['uptime']} | Memory: {sys_info['memory_usage_mb']} MB | OS: {sys_info['os_platform']} | PID: {sys_info['pid']}")
    
    ss = report["scrapers"]["stakestats"]
    print(f" • [Scraper] StakeStats Live API: {ss['status']} (Latency: {ss['latency_ms']} ms) - {ss['message']}")
    
    tg = report["scrapers"]["telegram"]
    print(f" • [Scraper] Telegram Drops: {tg['status']} ({tg['monitored_channels_count']} channels active)")
    
    db = report["database"]
    print(f" • [StateDB] DB File: {db['file_path']} | Size: {db['size_kb']} KB | Total Tracked: {db['total_tracked_codes']} drops")
    
    routes = report["routes"]
    print(f" • [Routing] Platforms: {routes['configured_platforms_count']} configured | {routes['total_channels_mapped']} Channels | {routes['total_webhooks_mapped']} Webhooks")
    print("=" * 80 + "\n")

def cmd_test_degen_qzino():
    import asyncio
    from send_test_embeds import send_degen_and_qzino_live_test_embeds
    logger.info("=== Dispatching 3 Most Recent Degen & Qzino Events with Media to Channel 1460666123484794880 ===")
    asyncio.run(send_degen_and_qzino_live_test_embeds())

def cmd_fetch_proxies():
    from network_manager import get_resilient_session
    session = get_resilient_session()
    count = session.proxy_pool.fetch_free_proxies(max_proxies=25)
    print(f"Discovered and loaded {count} working free proxies into pool. Total proxies in pool: {len(session.proxy_pool.proxies)}")

def cmd_scan_all_latest():
    import asyncio
    from post_all_channels_latest import broadcast_latest_events_to_discord
    logger.info("=== Scanning All Channels & Sources and Broadcasting Most Recent Events ===")
    asyncio.run(broadcast_latest_events_to_discord())

def cmd_list_sources():
    manager = DashboardManager()
    summary = manager.get_all_monitored_sources_summary()
    print("\n" + "=" * 80)
    print(f" 📡 LEAKED.GG MONITORED EVENT SOURCES BREAKDOWN")
    print(f" Total Telegram: {summary['total_telegram_channels']} | Total Web: {summary['total_web_sources']} | Custom: {summary['total_custom_sources']}")
    print("=" * 80)
    
    print("\n--- 📲 Monitored Telegram Channels by Platform ---")
    custom_tg_flat = []
    for ch_list in summary["custom_sources"].get("telegram", {}).values():
        custom_tg_flat.extend(ch_list)

    for p_key, ch_list in summary["telegram_by_platform"].items():
        print(f" • [{p_key.upper()}]:")
        for ch in ch_list:
            cust = " 🌟 (Custom)" if ch in custom_tg_flat else ""
            print(f"    - @{ch}{cust}")

    print("\n--- 🌐 Monitored Web Review Sources ---")
    custom_web = summary["custom_sources"].get("web", [])
    for u in summary["web_sources"]:
        cust = " 🌟 (Custom)" if u in custom_web else ""
        print(f" • {u}{cust}")

    print("\n--- ⚡ Live Poller & Feed Endpoints ---")
    print(f" • StakeStats API: {summary['stakestats_api']}")
    print(f" • CodeStats Feed: {summary['codestats_feed']}")
    print("=" * 80 + "\n")

def cmd_add_source(source_type: str, source: str, platform: str = "custom"):
    manager = DashboardManager()
    stype = source_type.strip().lower()
    if "web" in stype or source.startswith("http://") or source.startswith("https://"):
        success, msg = manager.add_web_source(source)
    else:
        success, msg = manager.add_telegram_source(source, platform)
    print(f"\n{msg}\n")

def cmd_remove_source(source: str):
    manager = DashboardManager()
    if source.startswith("http://") or source.startswith("https://"):
        success, msg = manager.remove_web_source(source)
    else:
        success, msg = manager.remove_telegram_source(source)
    print(f"\n{msg}\n")

def cmd_clear_history():
    tracker = CodeTracker(STATE_FILE_PATH)
    tracker.clear()
    print(f"Cleared tracked codes history in {STATE_FILE_PATH}.")

def cmd_watch(interval: int = 60, once: bool = False, notify: bool = True):
    """Continuous multi-source watcher loop, like brokechubb's `watch` command."""
    logger.info(f"=== Starting {BOT_NAME} Watcher ===")
    manager = DashboardManager()
    tracker = CodeTracker(STATE_FILE_PATH)
    notifier = DiscordNotifier(dashboard_manager=manager)
    engine = ScraperEngine(tracker=tracker, notifier=notifier, code_validator=StakeCodeValidator())

    sweep = 0
    while running:
        sweep += 1
        logger.info(f"[Watch] Sweep #{sweep} starting...")
        try:
            new_codes = engine.run_check(notify=notify)
            if new_codes:
                logger.info(f"[Watch] Sweep #{sweep}: {len(new_codes)} new codes detected and broadcast.")
            else:
                logger.info(f"[Watch] Sweep #{sweep}: no new codes.")
        except Exception as e:
            logger.error(f"[Watch] Sweep #{sweep} error: {e}", exc_info=True)

        if once:
            break

        logger.info(f"[Watch] Next sweep in {interval} seconds...")
        slept = 0
        while running and slept < interval:
            time.sleep(1)
            slept += 1

    logger.info("Watcher stopped.")

def cmd_history(limit: int = 25):
    """Print recent drop history from the Supabase database."""
    import db_manager
    rows = db_manager.get_recent_history(limit=limit)
    if not rows:
        print("\nNo drops recorded in the database yet. Run `python main.py watch --once` to populate history.\n")
        return

    print("\n" + "=" * 80)
    print(f" 📜 RECENT DROP HISTORY ({len(rows)} most recent)")
    print("=" * 80)
    for r in rows:
        status = r.get("availability_status") or "—"
        print(f" • [{r.get('platform', '?')}] Code: {r.get('code', '?')}  | Value: {r.get('amount_value', '—')}")
        print(f"   Source: {r.get('source_name', '—')}  | Status: {status}  | Sightings: {r.get('sightings', 1)}")
        print(f"   Last Seen: {r.get('last_seen_at', '—')}")
        print("-" * 80)

def cmd_stats():
    """Print analytics: platform breakdown, source leaderboard, hourly heatmap."""
    import db_manager
    stats = db_manager.get_stats()
    if stats["total_drops"] == 0:
        print("\nNo drops recorded yet. Run `python main.py watch --once` to start collecting data.\n")
        return

    print("\n" + "=" * 80)
    print(f" 📊 LEAKED.GG DROP ANALYTICS — {stats['total_drops']} total drops recorded")
    print("=" * 80)

    print("\n--- 🎰 Drops by Platform ---")
    for platform, count in stats["platform_breakdown"]:
        bar = "█" * min(count, 40)
        print(f" • {platform:25s} {count:4d}  {bar}")

    print("\n--- 📡 Source Leaderboard (Top 10) ---")
    for source, count in stats["source_leaderboard"]:
        print(f" • {source:25s} {count:4d}")

    print("\n--- ⏰ Hourly Drop Heatmap ---")
    heatmap = stats["hourly_heatmap"]
    if heatmap:
        max_count = max(heatmap.values()) if heatmap else 1
        for hour in sorted(heatmap.keys()):
            count = heatmap[hour]
            bar = "▓" * int((count / max_count) * 30) if max_count > 0 else ""
            print(f" • {hour}  {count:3d}  {bar}")
    else:
        print(" (no timestamp data available)")
    print("=" * 80 + "\n")

def cmd_check_codes(codes: List[str]):
    """Validate one or more bonus codes against Stake's GraphQL API (like brokechubb's `check`)."""
    validator = StakeCodeValidator()
    print("\n" + "=" * 80)
    print(f" 🔎 CODE VALIDATION CHECK")
    print("=" * 80)
    any_active = False
    for raw_code in codes:
        code = raw_code.strip()
        if not code:
            continue
        print(f"\nChecking: {code}")
        for platform in (Platform.STAKE_US, Platform.STAKE_COM):
            result = validator.validate(code, platform)
            status = result.get("status", "UNKNOWN")
            bonus_val = result.get("bonusValue", "N/A")
            reason = result.get("reason", "")
            emoji = {"AVAILABLE": "🟢", "FULLY_CLAIMED": "🔴", "EXPIRED": "⏰"}.get(status, "🟡")
            print(f"  {platform.value:15s} {emoji} {status}  | Bonus: {bonus_val}" + (f" | {reason}" if reason and status == "UNKNOWN" else ""))
            if status == "AVAILABLE":
                any_active = True
    print("\n" + "=" * 80)
    if any_active:
        print(" ✅ At least one platform reports the code ACTIVE.")
    else:
        print(" ❌ No platform reports the code as active.")
    print("=" * 80 + "\n")

def cmd_test_channel():
    import asyncio
    from send_test_embeds import send_all_test_embeds
    logger.info("=== Dispatching 4 Recent Test Events for Each Platform & Source to Discord Channel 1460666123484794880 ===")
    asyncio.run(send_all_test_embeds())

def main():
    parser = argparse.ArgumentParser(description=f"{BOT_NAME} - Automated Affiliate & Drop Code Monitoring Engine")
    parser.add_argument(
        "action",
        nargs="?",
        default="run",
        choices=["run", "check-once", "poll-stakestats", "poll-telegram", "test-discord", "test-channel", "test-degen-qzino", "scan-all-latest", "fetch-proxies", "bot", "list-seen", "list-sources", "add-source", "remove-source", "clear-history", "health", "watch", "history", "stats", "check"],
        help="Action to perform (default: run)"
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Discord notifications even during single scan (check-once / poll commands)"
    )
    parser.add_argument(
        "--type",
        dest="source_type",
        default="telegram",
        choices=["telegram", "web"],
        help="Source type for add-source ('telegram' or 'web')"
    )
    parser.add_argument(
        "--source",
        dest="source_val",
        default="",
        help="Channel handle or Web URL for add-source / remove-source"
    )
    parser.add_argument(
        "--platform",
        dest="platform_val",
        default="custom",
        help="Target platform name for Telegram source"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds for 'watch' mode (default: 60)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single sweep then exit (watch mode)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Number of rows for 'history' (default: 25)"
    )
    parser.add_argument(
        "codes",
        nargs="*",
        help="Bonus code(s) to validate with 'check' action"
    )
    args = parser.parse_args()

    if args.action == "run":
        cmd_run()
    elif args.action == "check-once":
        cmd_check_once(notify=args.notify)
    elif args.action == "poll-stakestats":
        cmd_poll_stakestats(notify=args.notify)
    elif args.action == "poll-telegram":
        cmd_poll_telegram(notify=args.notify)
    elif args.action == "test-discord":
        cmd_test_discord()
    elif args.action == "test-channel":
        cmd_test_channel()
    elif args.action == "test-degen-qzino":
        cmd_test_degen_qzino()
    elif args.action == "scan-all-latest":
        cmd_scan_all_latest()
    elif args.action == "fetch-proxies":
        cmd_fetch_proxies()
    elif args.action == "bot":
        run_discord_bot()
    elif args.action == "list-seen":
        cmd_list_seen()
    elif args.action == "list-sources":
        cmd_list_sources()
    elif args.action == "add-source":
        if not args.source_val:
            print("❌ Please specify --source <handle_or_url>")
        else:
            cmd_add_source(args.source_type, args.source_val, args.platform_val)
    elif args.action == "remove-source":
        if not args.source_val:
            print("❌ Please specify --source <handle_or_url>")
        else:
            cmd_remove_source(args.source_val)
    elif args.action == "clear-history":
        cmd_clear_history()
    elif args.action == "health":
        cmd_health()
    elif args.action == "watch":
        cmd_watch(interval=args.interval, once=args.once, notify=True)
    elif args.action == "history":
        cmd_history(limit=args.limit)
    elif args.action == "stats":
        cmd_stats()
    elif args.action == "check":
        if not args.codes:
            print("Please specify code(s) to check, e.g.: python main.py check CODE1 CODE2")
        else:
            cmd_check_codes(args.codes)

if __name__ == "__main__":
    main()
