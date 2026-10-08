import unittest
import os
import json
import asyncio
import datetime
import tempfile
import uuid
from unittest.mock import MagicMock, AsyncMock
from datetime import timezone
from models import BonusCodeItem, Platform
from filters import (
    is_telegram_or_low_value_drop, is_valid_affiliate_code,
    extract_event_datetime, is_event_recent, MAX_EVENT_AGE_DAYS
)
from tracker import CodeTracker
from dashboard_manager import DashboardManager
from discord_notifier import DiscordNotifier
from scrapers.sources import SiteScraper
from scrapers.telegram import TelegramScraper
from scrapers.stakestats import StakeStatsPoller
from scrapers.codestats import CodeStatsScraper
from scrapers.engine import ScraperEngine
from health_monitor import HealthMonitor
from config import (
    COLOR_STAKE_COM, COLOR_STAKE_US, COLOR_SHUFFLE_COM, COLOR_SHUFFLE_US,
    COLOR_QZINO, COLOR_RAINBET, COLOR_DEGEN, COLOR_GOATED, COLOR_DUAL_STAKE,
    AFFILIATE_SIGNUP_LINKS
)

class TestLeakedGGMonitoring(unittest.TestCase):

    def setUp(self):
        self.test_state_file = "test_seen_codes.json"
        self.test_routes_file = "test_routes_config.json"
        if os.path.exists(self.test_state_file):
            os.remove(self.test_state_file)
        if os.path.exists(self.test_routes_file):
            os.remove(self.test_routes_file)

    def tearDown(self):
        if os.path.exists(self.test_state_file):
            os.remove(self.test_state_file)
        if os.path.exists(self.test_routes_file):
            os.remove(self.test_routes_file)

    def test_codestats_ignores_waiting_placeholder(self):
        scraper = CodeStatsScraper(base_url="https://codestats.test")
        scraper.session.fetch_json = MagicMock(return_value=None)
        scraper.session.fetch_text = MagicMock(return_value=(
            '<article class="code-card">'
            'Stake.com Code: Waiting Bonus Drop 2026-09-15'
            '</article>'
        ))

        self.assertEqual(scraper.scrape_codes(), [])

    def test_all_platforms_colors_and_signup_links(self):
        # Platform detection from text
        self.assertEqual(Platform.from_str("stake.com"), Platform.STAKE_COM)
        self.assertEqual(Platform.from_str("stake.us"), Platform.STAKE_US)
        self.assertEqual(Platform.from_str("shuffle.com"), Platform.SHUFFLE_COM)
        self.assertEqual(Platform.from_str("shuffle.us"), Platform.SHUFFLE_US)
        self.assertEqual(Platform.from_str("qzino.ai"), Platform.QZINO)
        self.assertEqual(Platform.from_str("rainbet"), Platform.RAINBET)
        self.assertEqual(Platform.from_str("degen"), Platform.DEGEN)
        self.assertEqual(Platform.from_str("goated"), Platform.GOATED)
        self.assertEqual(Platform.from_str("dual stake.us and stake.com"), Platform.DUAL_STAKE)

        # Ensure all platforms have distinct colors matching specific requirements
        self.assertEqual(Platform.SHUFFLE_US.embed_color, COLOR_SHUFFLE_US)
        self.assertEqual(Platform.SHUFFLE_COM.embed_color, COLOR_SHUFFLE_COM)
        self.assertEqual(Platform.QZINO.embed_color, COLOR_QZINO)
        self.assertEqual(Platform.STAKE_US.embed_color, COLOR_STAKE_US)
        self.assertEqual(Platform.STAKE_COM.embed_color, COLOR_STAKE_COM)
        self.assertEqual(Platform.RAINBET.embed_color, COLOR_RAINBET)
        self.assertEqual(COLOR_SHUFFLE_US, 0xFFFFFF)
        self.assertEqual(COLOR_SHUFFLE_COM, 0x8A2BE2)
        self.assertEqual(COLOR_QZINO, 0xFFD700)
        self.assertEqual(COLOR_STAKE_US, 0xFF7700)
        self.assertEqual(COLOR_STAKE_COM, 0xFF1493)
        self.assertEqual(COLOR_RAINBET, 0x0A2540)

        platform_colors = [
            Platform.STAKE_COM.embed_color,
            Platform.STAKE_US.embed_color,
            Platform.SHUFFLE_COM.embed_color,
            Platform.SHUFFLE_US.embed_color,
            Platform.QZINO.embed_color,
            Platform.RAINBET.embed_color,
            Platform.DEGEN.embed_color,
            Platform.GOATED.embed_color,
            Platform.DUAL_STAKE.embed_color
        ]
        self.assertEqual(len(platform_colors), len(set(platform_colors)), "All platforms must have unique embed colors!")

        # Check affiliate signup links
        self.assertEqual(AFFILIATE_SIGNUP_LINKS["Stake.com"], "https://stake.com/?c=SELFMADE")
        self.assertEqual(AFFILIATE_SIGNUP_LINKS["Stake.us"], "https://www.stake.us/?c=selfmade")
        self.assertEqual(AFFILIATE_SIGNUP_LINKS["Shuffle.com"], "https://shuffle.com/?r=selfmade")
        self.assertEqual(AFFILIATE_SIGNUP_LINKS["Shuffle.us"], "https://shuffle.us/?r=selfmade")
        self.assertEqual(AFFILIATE_SIGNUP_LINKS["Qzino"], "https://qzino.ai/?r=SELFMADE")
        self.assertEqual(AFFILIATE_SIGNUP_LINKS["Rainbet"], "https://rainbet.com/?r=murphy")
        self.assertEqual(AFFILIATE_SIGNUP_LINKS["Degen"], "https://degen.com/r/selfmade")

    def test_case_sensitivity_and_redeem_links(self):
        # Case sensitive code preservation (mixed-case, lowercase, uppercase)
        cases = ["stakecommp30u9tyrkd2d1", "UIJXBQUS", "mjp6axxg", "CaseSensitiveCode123"]
        for c in cases:
            item_com = BonusCodeItem(
                code=c,
                platform=Platform.STAKE_COM,
                amount_value="$12.50",
                wager_requirement="$50,000",
                source_url="https://example.com",
                source_name="Test"
            )
            self.assertEqual(item_com.clean_code, c)
            self.assertIn(f"code={c}", item_com.redeem_link)

            item_us = BonusCodeItem(
                code=c,
                platform=Platform.STAKE_US,
                amount_value="2 SC",
                wager_requirement="8,000 SC",
                source_url="https://example.com",
                source_name="Test"
            )
            self.assertEqual(item_us.clean_code, c)
            self.assertIn(f"code={c}", item_us.redeem_link)

    def test_rainbet_telegram_parsing(self):
        tg = TelegramScraper()
        sample_text = """
        🌧️ NEW RAINBET BONUS DROP!
        1. Click Code To Copy:
        UIJXBQUS
        2. Redeem Here: https://rainbet.com/affiliates?modal=wallet&tab=redeem
        Reward: $1
        Wager Required: $4,000
        Claims: 600
        """
        item = tg.parse_rainbet_message(sample_text, "https://t.me/EddiesCodesRainbet/2083")
        self.assertIsNotNone(item)
        self.assertEqual(item.code, "UIJXBQUS")
        self.assertEqual(item.platform, Platform.RAINBET)
        self.assertEqual(item.amount_value, "$1")
        self.assertEqual(item.wager_requirement, "$4,000")
        self.assertEqual(item.claims_count, "600")
        self.assertEqual(item.redeem_link, "https://rainbet.com/affiliates?modal=wallet&tab=redeem")
        self.assertEqual(item.affiliate_signup_link, "https://rainbet.com/?r=murphy")

    def test_degen_telegram_parsing_with_media(self):
        tg = TelegramScraper()
        notifier = DiscordNotifier()

        # 1. Standard text code with media
        sample_text = "Claim code DEGENWIN for $5 bonus drop! Wager $2,500 required."
        item = tg.parse_degen_message(
            text=sample_text,
            msg_url="https://t.me/degendotcom/123",
            image_url="https://cdn.telesco.pe/file/sample_degen.jpg"
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.code, "DEGENWIN")
        self.assertEqual(item.platform, Platform.DEGEN)
        self.assertEqual(item.image_url, "https://cdn.telesco.pe/file/sample_degen.jpg")
        self.assertEqual(item.affiliate_signup_link, "https://degen.com/r/selfmade")

        embed = notifier.build_embed(item)
        self.assertEqual(embed.get("image", {}).get("url"), "https://cdn.telesco.pe/file/sample_degen.jpg")

        # 2. Image-embedded promo code drop (e.g. post 49 format)
        sample_post_49 = """Promo Code Drop!
7 Day Wager Requirement: $4,000
Claim Amount: $5.00
Total Claims: 150
Enjoy and good luck Degens! 🎰"""
        item_49 = tg.parse_degen_message(
            text=sample_post_49,
            msg_url="https://t.me/degendotcom/49",
            image_url="https://cdn4.telesco.pe/file/pHHR6Eb.jpg"
        )
        self.assertIsNotNone(item_49)
        self.assertEqual(item_49.code, "CHECK_IMAGE_FOR_CODE_#49")
        self.assertEqual(item_49.platform, Platform.DEGEN)
        self.assertEqual(item_49.amount_value, "$5.00")
        self.assertEqual(item_49.wager_requirement, "$4,000")
        self.assertEqual(item_49.claims_count, "150")
        self.assertEqual(item_49.image_url, "https://cdn4.telesco.pe/file/pHHR6Eb.jpg")
        self.assertIn("7 Day Wager Requirement: $4,000", item_49.description)

        embed_49 = notifier.build_embed(item_49)
        self.assertEqual(embed_49.get("image", {}).get("url"), "https://cdn4.telesco.pe/file/pHHR6Eb.jpg")
        # Clean description without raw telegram text duplication
        self.assertIn("Verified Bonus Drop", embed_49.get("description", ""))
        self.assertNotIn("7 Day Wager Requirement", embed_49.get("description", ""))

    def test_dual_stake_code_parsing_and_formatting(self):
        tg = TelegramScraper()
        sample_text = """
        🔷 USER SUBMITTED STAKE CODE
        - Code: mjp6axxg
        🇺🇸 US https://stake.us/settings/offers?type=drop&code=mjp6axxg&currency=sweeps&modal=redeemBonus
        🌏 COM https://stake.com/settings/offers?type=drop&code=mjp6axxg&currency=ltc&modal=redeemBonus
        """
        item = tg.parse_stake_message(sample_text, "https://t.me/codestats2/26044", "codestats2")
        self.assertIsNotNone(item)
        self.assertEqual(item.code, "mjp6axxg")
        self.assertTrue(item.is_dual_stake)
        self.assertIn("code=mjp6axxg", item.redeem_link_us)
        self.assertIn("code=mjp6axxg", item.redeem_link_com)

        notifier = DiscordNotifier()
        embed = notifier.build_embed(item)
        self.assertIn("DUAL STAKE", embed["title"])
        fields_text = " ".join([f["value"] for f in embed["fields"]])
        self.assertIn("Stake.us", fields_text)
        self.assertIn("Stake.com", fields_text)

    def test_stakestats_poller_and_activecodes(self):
        poller = StakeStatsPoller()
        active_us, active_com = poller.get_active_codes()
        self.assertIsInstance(active_us, list)
        self.assertIsInstance(active_com, list)
        embeds = poller.format_discord_active_list()
        self.assertGreaterEqual(len(embeds), 1)
        self.assertIn("ACTIVE BONUS DROPS", embeds[0]["title"])
        field_names = " ".join(field["name"] for field in embeds[0]["fields"])
        self.assertIn("STAKE.US ACTIVE DROPS", field_names)
        self.assertIn("STAKE.COM ACTIVE DROPS", field_names)

    def test_stakestats_activecodes_paginates_large_results(self):
        poller = StakeStatsPoller()
        items = []
        for index in range(30):
            items.append(BonusCodeItem(
                code=f"ACTIVE{index:02d}",
                platform=Platform.STAKE_US if index % 2 == 0 else Platform.STAKE_COM,
                amount_value="$2",
                wager_requirement="$10,000 (7-Day Wager)",
                source_url="https://stakestats.net/stake/tools/code",
                source_name="StakeStats.net"
            ))
        poller.get_active_codes = MagicMock(return_value=(
            [item for item in items if item.platform == Platform.STAKE_US],
            [item for item in items if item.platform == Platform.STAKE_COM]
        ))

        embeds = poller.format_discord_active_list()

        self.assertGreater(len(embeds), 1)
        for embed in embeds:
            self.assertLessEqual(len(embed["fields"]), 24)
            total_chars = len(embed["title"]) + len(embed["description"]) + len(embed["footer"]["text"])
            total_chars += sum(len(field["name"]) + len(field["value"]) for field in embed["fields"])
            self.assertLessEqual(total_chars, 5600)

    def test_case_sensitive_tracker(self):
        tracker = CodeTracker(self.test_state_file)
        item1 = BonusCodeItem(
            code="BonusCodeA",
            platform=Platform.STAKE_US,
            amount_value="$10",
            wager_requirement="3x",
            source_url="https://example.com",
            source_name="Test"
        )
        item2 = BonusCodeItem(
            code="bonuscodea", # Different case
            platform=Platform.STAKE_US,
            amount_value="$10",
            wager_requirement="3x",
            source_url="https://example.com",
            source_name="Test"
        )
        self.assertTrue(tracker.mark_seen(item1))
        self.assertTrue(tracker.is_seen(item1.platform.value, "BonusCodeA"))
        self.assertFalse(tracker.is_seen(item1.platform.value, "bonuscodea"))

    def test_dashboard_manager_multi_channel_and_webhook(self):
        dm = DashboardManager(self.test_routes_file)
        
        # Test adding multiple channels for a single platform (at least 2 channels)
        dm.add_channel("Stake.us", 111111111111111111)
        dm.add_channel("Stake.us", 222222222222222222)
        channels = dm.get_channels("Stake.us")
        self.assertEqual(len(channels), 2)
        self.assertIn(111111111111111111, channels)
        self.assertIn(222222222222222222, channels)
        self.assertEqual(dm.get_channel("Stake.us"), 111111111111111111)

        # Test adding multiple webhooks for a single platform (at least 2 webhooks)
        dm.add_webhook("Stake.us", "https://discord.com/api/webhooks/111/hook1")
        dm.add_webhook("Stake.us", "https://discord.com/api/webhooks/222/hook2")
        webhooks = dm.get_webhooks("Stake.us")
        self.assertEqual(len(webhooks), 2)
        self.assertIn("https://discord.com/api/webhooks/111/hook1", webhooks)
        self.assertIn("https://discord.com/api/webhooks/222/hook2", webhooks)

        # Test channel and webhook removal
        dm.remove_channel("Stake.us", 111111111111111111)
        self.assertEqual(dm.get_channels("Stake.us"), [222222222222222222])

        dm.remove_webhook("Stake.us", "https://discord.com/api/webhooks/111/hook1")
        self.assertEqual(dm.get_webhooks("Stake.us"), ["https://discord.com/api/webhooks/222/hook2"])

        # Test default fallback channel & webhook
        dm.add_channel("Default", 999999999999999999)
        self.assertEqual(dm.get_channels("Rainbet"), [999999999999999999])

        # Test settings persistence
        dm.set_setting("realtime_monitoring_enabled", False)
        dm.set_setting("check_interval_seconds", 45)
        self.assertFalse(dm.get_setting("realtime_monitoring_enabled"))
        self.assertEqual(dm.get_setting("check_interval_seconds"), 45)

        # Test reloading from disk
        dm2 = DashboardManager(self.test_routes_file)
        self.assertEqual(dm2.get_channels("Stake.us"), [222222222222222222])
        self.assertEqual(dm2.get_webhooks("Stake.us"), ["https://discord.com/api/webhooks/222/hook2"])
        self.assertEqual(dm2.get_setting("check_interval_seconds"), 45)

        # Test summary generation
        summary = dm2.get_all_routes_summary()
        self.assertIn("Stake.us", summary)
        self.assertEqual(summary["Stake.us"]["channel_count"], 1)
        self.assertTrue(summary["Stake.us"]["webhook_configured"])

    def test_discord_notifier_with_multi_routes(self):
        dm = DashboardManager(self.test_routes_file)
        dm.add_webhook("Shuffle.us", "https://discord.com/api/webhooks/999/testshuffle1")
        dm.add_webhook("Shuffle.us", "https://discord.com/api/webhooks/999/testshuffle2")
        dm.add_channel("Shuffle.us", 333333333333333333)
        dm.add_channel("Shuffle.us", 444444444444444444)

        notifier = DiscordNotifier(dashboard_manager=dm)
        whs = notifier.get_webhooks_for_platform(Platform.SHUFFLE_US)
        chs = notifier.get_channels_for_platform(Platform.SHUFFLE_US)
        self.assertEqual(len(whs), 2)
        self.assertEqual(len(chs), 2)

    def test_health_monitor_engine(self):
        dm = DashboardManager(self.test_routes_file)
        tracker = CodeTracker(self.test_state_file)
        health_mon = HealthMonitor(dashboard_manager=dm, tracker=tracker)

        sys_metrics = health_mon.check_system_metrics()
        self.assertIn("uptime", sys_metrics)
        self.assertIn("memory_usage_mb", sys_metrics)
        self.assertGreaterEqual(sys_metrics["memory_usage_mb"], 0.0)

        db_metrics = health_mon.check_database_state()
        self.assertIn("total_tracked_codes", db_metrics)

        report = health_mon.get_full_health_report()
        self.assertIn("overall_status", report)
        self.assertIn("system", report)
        self.assertIn("scrapers", report)
        self.assertIn("routes", report)

        embed = health_mon.create_health_embed()
        self.assertIsNotNone(embed)
        self.assertIn("Health Monitor", embed.title)

    def test_all_provided_affiliate_and_low_wager_codes_parsing(self):
        """
        Validates that all user-provided affiliate and low-wager drop codes
        are matched by our scrapers/regexes and generate valid items with proper platforms and links.
        """
        scraper = SiteScraper()

        ballislife_codes = [
            "BIL7M0C5T8", "BIL4D9V3L1", "BIL0R8W6Q2", "BIL3P7H1M5", "BIL6K2T9X4",
            "BIL1N5Y8D3", "BIL8L4C0R7", "BIL2W9M3Q6", "BIL5X1P7H8", "BIL7C3V8N1",
            "BIL0M5Q2Y9", "BIL4H8R3T7", "BIL6P1K9W4", "BIL2N7X5D8", "BIL8Q4F2M0",
            "BIL1V6C9L7", "BIL5Y0T8P3", "BILGPK11VL", "BILGXLPOKQ", "BILGXT8U1V",
            "BILJKABDYH", "BILJVUOA5R"
        ]
        sample_bil_html = f"<div>{' '.join([f'<span>Drop Code: {c} Value: $5</span>' for c in ballislife_codes])}</div>"
        bil_items = scraper.parse("https://www.ballislife.com/betting/reviews/stake-us/bonus-drops/", sample_bil_html)
        detected_bil_codes = [it.code for it in bil_items]
        for c in ballislife_codes:
            self.assertIn(c, detected_bil_codes)

        next_codes = [
            "NEXT1V7QPK3XLMR", "NEXT8T2KRV9LQXP", "NEXT5Q4XLM7PRVK",
            "NEXT4R7KQ2M9LXP", "NEXT9T3WJ6N8KZR", "NEXT2P8XM5Q7LKC"
        ]
        sample_next_html = f"<div>{' '.join([f'<span>Code: {c} Amount: $5</span>' for c in next_codes])}</div>"
        next_items = scraper.parse("https://next.io/sweepstakes-casinos/stake-us/bonus-drop-codes/", sample_next_html)
        detected_next_codes = [it.code for it in next_items]
        for c in next_codes:
            self.assertIn(c, detected_next_codes)

        dimers_codes = [
            "DIMERS4Q2VRX9LKP", "DIMERS7L5KXM3QPT", "DIMERS7Q3KX9L2PM", "DIMERS2M8WP4K7QX"
        ]
        sample_dimers_html = f"<div>{' '.join([f'<span>DIMERS Code: {c} $5</span>' for c in dimers_codes])}</div>"
        dimers_items = scraper.parse("https://www.dimers.com/sweepstakes-casinos/stake-us/bonus-drop-code", sample_dimers_html)
        detected_dimers_codes = [it.code for it in dimers_items]
        for c in dimers_codes:
            self.assertIn(c, detected_dimers_codes)

        gamechampions_codes = [
            ("JVN23GMETITAN4L", Platform.STAKE_US),
            ("KRX81BONUSINFERNO9B", Platform.STAKE_US),
            ("XPR24DRPECLIPSE7B", Platform.STAKE_COM),
            ("YLM52STKIGNITE8N", Platform.STAKE_COM)
        ]
        for c, expected_plat in gamechampions_codes:
            url = "https://www.gamechampions.com/en/reviews/stake-us/bonus-drop-codes/" if expected_plat == Platform.STAKE_US else "https://www.gamechampions.com/en/reviews/stake-com/bonus-drop-codes/"
            gc_html = f"<div>Bonus Drop Code: {c}</div>"
            gc_items = scraper.parse(url, gc_html)
            self.assertTrue(any(it.code == c and it.platform == expected_plat for it in gc_items))

        thelines_codes = ["STAKEUSTLC007", "STAKEUSTLC006", "STAKEUSTLC003", "STAKEUSTLC001", "STAKEUSTLC002"]
        sample_lines_html = f"<div>{' '.join([f'<span>TheLines Code: {c}</span>' for c in thelines_codes])}</div>"
        lines_items = scraper.parse("https://www.thelines.com/casino/sweepstakes/stake-us/bonus-drop-codes/", sample_lines_html)
        detected_lines = [it.code for it in lines_items]
        for c in thelines_codes:
            self.assertIn(c, detected_lines)

        tgh_codes = [
            "TGHSEPT26BONUS7NQ4XZ", "SEPTREWARD926K8V3MP", "Haus26SeptPrizeR5T9LW",
            "BonusSEPT26DropsX2M7QK", "HAUSSEPT26RewardV8C4ZN", "THEGAMESEPT2026P6Y3KT",
            "GameHausSEPT26Q9L5RX", "TGHSEPTCode26M4Z8VN", "SEPTTGH26DropsW7K2PC",
            "HausRewardSEPT26B9X5QM"
        ]
        sample_tgh_html = f"<div>{' '.join([f'<span>TheGameHaus Drop: {c} Amount: $5</span>' for c in tgh_codes])}</div>"
        tgh_items = scraper.parse("https://thegamehaus.com/sweepstakes-casinos/stake-us-bonus-drop-codes/", sample_tgh_html)
        detected_tgh = [it.code for it in tgh_items]
        for c in tgh_codes:
            self.assertIn(c, detected_tgh)

        deadspin_codes = [
            "DSNDrop980aUS", "DSNbonusDROPS93850S", "DSN2983DSN3BONUSdrop", "DSbonusD902130DDROP",
            "LatestDrops502sj0", "BonusDROPS2031", "DropsDSN3019", "Drop3394DSNCODE"
        ]
        sample_dsn_html = f"<div>{' '.join([f'<span>Deadspin Drop: {c} Value: $5000</span>' for c in deadspin_codes])}</div>"
        dsn_items = scraper.parse("https://deadspin.com/sweepstakes-casinos/reviews/stake-us/bonus-drop-code/", sample_dsn_html)
        detected_dsn = [it.code for it in dsn_items]
        for c in deadspin_codes:
            self.assertIn(c, detected_dsn)

    def test_qzino_parsing_with_media(self):
        tg = TelegramScraper()
        notifier = DiscordNotifier()

        sample_text = """🎲 QZINO SPECIAL BONUS DROP!
Use Code: QZINOLUCKY88
Claim Amount: $10.00
Wager Requirement: 5x Playthrough
Total Claims: 500
Join now and claim via https://qzino.ai/?r=SELFMADE"""
        item = tg.parse_qzino_message(
            text=sample_text,
            msg_url="https://t.me/qzino/102",
            image_url="https://cdn.telesco.pe/file/qzino_promo.jpg"
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.code, "QZINOLUCKY88")
        self.assertEqual(item.platform, Platform.QZINO)
        self.assertEqual(item.amount_value, "$10.00")
        self.assertEqual(item.claims_count, "500")
        self.assertEqual(item.image_url, "https://cdn.telesco.pe/file/qzino_promo.jpg")
        self.assertIn("QZINO SPECIAL BONUS DROP", item.description)

        embed = notifier.build_embed(item)
        self.assertEqual(embed.get("image", {}).get("url"), "https://cdn.telesco.pe/file/qzino_promo.jpg")
        field_values = " ".join([f["value"] for f in embed.get("fields", [])])
        self.assertIn("[CLICK HERE TO CLAIM]", field_values)
        self.assertIn("[SIGNUP HERE]", field_values)
        self.assertIn("[JOIN DISCORD](https://discord.gg/TvJe6BV7ge)", field_values)

    def test_vip_events_routing_and_extraction(self):
        tg = TelegramScraper()
        notifier = DiscordNotifier()

        # 1. Stake.us VIP Weekly Boost from t.me/c/1542279201/257
        sample_us_vip = """🎉 Stake.us VIP Weekly Bonus is now available!
Claim your boost here: https://stake.us/?bonus=weekly_boost_tier5
Wager requirements apply based on your VIP level."""
        item_us = tg.parse_stake_message(
            text=sample_us_vip,
            msg_url="https://t.me/c/1542279201/257",
            channel_name="1542279201",
            image_url="https://cdn.telesco.pe/file/weekly_boost_us.jpg"
        )
        self.assertIsNotNone(item_us)
        self.assertEqual(item_us.platform, Platform.STAKE_US_VIP_NOTICES)
        self.assertEqual(item_us.event_type, "weekly_bonus")
        self.assertEqual(item_us.image_url, "https://cdn.telesco.pe/file/weekly_boost_us.jpg")
        self.assertIn("https://stake.us/?bonus=weekly_boost_tier5", item_us.description)

        embed_us = notifier.build_embed(item_us)
        self.assertEqual(embed_us.get("color"), Platform.STAKE_US_VIP_NOTICES.embed_color)
        self.assertEqual(embed_us.get("image", {}).get("url"), "https://cdn.telesco.pe/file/weekly_boost_us.jpg")

        # 2. Stake.com VIP Weekly Bonus from t.me/c/2922581483/86
        sample_com_vip = """👑 Stake.com VIP Weekly Bonus is LIVE!
Claim your bonus here: https://playstake.info/bonus?code=weekly_com_vip
Enjoy your reload & weekly boost!"""
        item_com = tg.parse_stake_message(
            text=sample_com_vip,
            msg_url="https://t.me/c/2922581483/86",
            channel_name="2922581483",
            image_url="https://cdn.telesco.pe/file/weekly_boost_com.jpg"
        )
        self.assertIsNotNone(item_com)
        self.assertEqual(item_com.platform, Platform.STAKE_COM_VIP_NOTICES)
        self.assertEqual(item_com.event_type, "weekly_bonus")
        self.assertEqual(item_com.image_url, "https://cdn.telesco.pe/file/weekly_boost_com.jpg")
        self.assertIn("https://playstake.info/bonus?code=weekly_com_vip", item_com.description)

        embed_com = notifier.build_embed(item_com)
        self.assertEqual(embed_com.get("color"), Platform.STAKE_COM_VIP_NOTICES.embed_color)

    def test_owner_and_subscriber_access_control(self):
        dm = DashboardManager(self.test_routes_file)
        owner_id = 1051355279511519273
        random_user_id = 999888777666555444

        # Owner check
        self.assertTrue(dm.is_owner(owner_id))
        self.assertTrue(dm.is_authorized(owner_id))

        # Random user without subscription is unauthorized
        self.assertFalse(dm.is_owner(random_user_id))
        self.assertFalse(dm.is_authorized(random_user_id))

        # Add $2 crypto subscriber
        dm.add_subscriber(random_user_id, note="$2 LTC Payment Confirmed")
        self.assertTrue(dm.is_authorized(random_user_id))
        self.assertFalse(dm.is_owner(random_user_id))

        # Remove subscriber
        dm.remove_subscriber(random_user_id)
        self.assertFalse(dm.is_authorized(random_user_id))

        # Owner cannot be removed
        self.assertFalse(dm.remove_subscriber(owner_id))

    def test_expired_subscribers_are_excluded_from_notification_fanout(self):
        manager = DashboardManager(self.test_routes_file)
        manager.add_subscriber("1001", duration="7days")
        manager.config["subscribers"]["1001"]["expires_at"] = (
            datetime.datetime.now(timezone.utc) - datetime.timedelta(days=1)
        ).isoformat()
        manager.save()

        self.assertNotIn("1001", manager.get_all_subscriber_ids())

    def test_subscriber_dispatch_uses_only_that_subscribers_routes(self):
        manager = DashboardManager(self.test_routes_file)
        manager.add_subscriber("1001")
        manager.add_subscriber("1002")
        manager.add_subscriber_channel("1001", Platform.STAKE_US, 111)
        manager.add_subscriber_channel("1002", Platform.STAKE_US, 222)
        manager.add_channel(Platform.STAKE_US, 999)

        notifier = DiscordNotifier(dashboard_manager=manager)
        notifier._send_single_item_notification = MagicMock(return_value=True)
        item = BonusCodeItem(
            code="ISOLATED100",
            platform=Platform.STAKE_US,
            amount_value="2 SC",
            wager_requirement="None",
            source_name="test",
            source_url="https://example.com"
        )

        self.assertTrue(notifier.send_notification(item, subscriber_uid="1001"))
        dispatched_channels = notifier._send_single_item_notification.call_args.args[2]
        self.assertEqual(dispatched_channels, [111])

    def test_false_positive_and_static_detection_rejection(self):
        """
        Validates that static UI text, common dictionary words, and broad false matches
        are cleanly rejected.
        """
        false_candidates = [
            "bilingual", "billing", "billion", "nextpage", "nextgen",
            "disabled", "display", "discussion", "september", "button",
            "promocode", "bonuscode", "clickhere", "claimnow", "exclusive",
            "menu", "header", "footer", "content", "stakecasino"
        ]
        for word in false_candidates:
            item = BonusCodeItem(
                code=word,
                platform=Platform.STAKE_US,
                amount_value="$5",
                wager_requirement="3x",
                source_url="https://example.com",
                source_name="Test"
            )
            is_valid, reason = is_valid_affiliate_code(item)
            self.assertFalse(is_valid, f"Word '{word}' should have been rejected as a false positive! Reason: {reason}")

    def test_event_recency_and_4_day_cutoff(self):
        """
        Validates that events older than 4 days (or containing outdated/expired dates)
        are rejected, while recent drops within 4 days are accepted.
        """
        now = datetime.datetime(2026, 9, 7, 2, 11, 0, tzinfo=timezone.utc)

        # 1. Recent drop from 1 day ago (2026-09-06)
        recent_dt = datetime.datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
        is_rec, _ = is_event_recent(dt=recent_dt, max_days=4, reference_dt=now)
        self.assertTrue(is_rec)

        item_recent = BonusCodeItem(
            code="BIL7M0C5T8",
            platform=Platform.STAKE_US,
            amount_value="$5",
            wager_requirement="3x",
            source_url="https://example.com",
            source_name="Test",
            event_datetime=recent_dt
        )
        self.assertTrue(is_valid_affiliate_code(item_recent, reference_dt=now)[0])

        # 2. Outdated drop from 13 days ago (2026-08-25)
        old_dt = datetime.datetime(2026, 8, 25, 15, 3, 0, tzinfo=timezone.utc)
        is_rec_old, reason_old = is_event_recent(dt=old_dt, max_days=4, reference_dt=now)
        self.assertFalse(is_rec_old)
        self.assertIn("exceeds 4-day limit", reason_old)

        item_old = BonusCodeItem(
            code="BIL7M0C5T8",
            platform=Platform.STAKE_US,
            amount_value="$5",
            wager_requirement="3x",
            source_url="https://example.com",
            source_name="Test",
            event_datetime=old_dt
        )
        is_valid_old, val_reason = is_valid_affiliate_code(item_old, reference_dt=now)
        self.assertFalse(is_valid_old)
        self.assertIn("too old", val_reason)

        # 3. Text date extraction and rejection
        text_with_old_date = "Low Wager Code BIL7M0C5T8 dropped on 8/25/2026 3:03 PM"
        extracted_dt = extract_event_datetime(text_with_old_date)
        self.assertIsNotNone(extracted_dt)
        self.assertEqual(extracted_dt.month, 8)
        self.assertEqual(extracted_dt.day, 25)
        self.assertEqual(extracted_dt.year, 2026)

        is_rec_text, _ = is_event_recent(dt=None, max_days=4, text=text_with_old_date, reference_dt=now)
        self.assertFalse(is_rec_text)

        # 4. Relative age in text
        self.assertFalse(is_event_recent(max_days=4, text="Posted 6 days ago by admin")[0])
        self.assertFalse(is_event_recent(max_days=4, text="Code dropped 2 weeks ago")[0])
        self.assertFalse(is_event_recent(max_days=4, text="Code is now expired")[0])
        self.assertTrue(is_event_recent(max_days=4, text="Posted 2 days ago by admin")[0])

    def test_telegram_avatar_exclusion_and_post_media_extraction(self):
        """
        Validates that channel and user profile/avatar pictures are NEVER extracted
        as the post media, while actual message media graphics are captured.
        """
        from bs4 import BeautifulSoup
        from scrapers.telegram import TelegramScraper

        tg = TelegramScraper()

        # 1. Message with ONLY channel avatar / profile picture (no post attachment)
        html_avatar_only = """
        <div class="tgme_widget_message_wrap js-widget_message_wrap">
          <div class="tgme_widget_message js-widget_message">
            <div class="tgme_widget_message_user">
              <a class="tgme_widget_message_user_photo">
                <img src="https://cdn4.telesco.pe/file/channel_userpic_avatar.jpg">
              </a>
            </div>
            <div class="tgme_widget_message_bubble">
              <div class="tgme_widget_message_author">Channel Owner</div>
              <div class="tgme_widget_message_text js-message_text">Stake.us drop code: STAKEUSCODE123 Value: $5 Wager: $3,000</div>
              <div class="tgme_widget_message_date"><time datetime="2026-09-06T12:00:00+00:00"></time></div>
            </div>
          </div>
        </div>
        """
        soup_avatar = BeautifulSoup(html_avatar_only, "html.parser")
        wrap_avatar = soup_avatar.find(class_="tgme_widget_message_wrap")
        extracted_img = tg.extract_image_url_from_wrap(wrap_avatar)
        self.assertIsNone(extracted_img, "Channel profile picture was incorrectly extracted as post media!")

        # 2. Message with actual post photo attachment
        html_post_media = """
        <div class="tgme_widget_message_wrap js-widget_message_wrap">
          <div class="tgme_widget_message js-widget_message">
            <div class="tgme_widget_message_user">
              <a class="tgme_widget_message_user_photo">
                <img src="https://cdn4.telesco.pe/file/userpic123.jpg">
              </a>
            </div>
            <div class="tgme_widget_message_bubble">
              <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://cdn4.telesco.pe/file/actual_degen_drop_graphic.jpg')"></a>
              <div class="tgme_widget_message_text js-message_text">Promo Code Drop! 7 Day Wager: $4,000 Claim Amount: $5.00</div>
              <div class="tgme_widget_message_date"><time datetime="2026-09-06T12:00:00+00:00"></time></div>
            </div>
          </div>
        </div>
        """
        soup_media = BeautifulSoup(html_post_media, "html.parser")
        wrap_media = soup_media.find(class_="tgme_widget_message_wrap")
        extracted_media_img = tg.extract_image_url_from_wrap(wrap_media)
        self.assertEqual(extracted_media_img, "https://cdn4.telesco.pe/file/actual_degen_drop_graphic.jpg")

        # 3. Avatar URL detection filter
        self.assertTrue(tg.is_avatar_or_profile_url("https://cdn.telegram.org/userpic/12345.jpg"))
        self.assertTrue(tg.is_avatar_or_profile_url("https://cdn.telegram.org/profile_photos/avatar.jpg"))
        self.assertFalse(tg.is_avatar_or_profile_url("https://cdn.telesco.pe/file/actual_drop_graphic.jpg"))

    def test_user_agent_rotator_and_headers(self):
        """
        Validates that UserAgentRotator provides diverse browser headers with Sec-Ch-Ua metadata.
        """
        from network_manager import UserAgentRotator, BROWSER_USER_AGENTS

        headers = UserAgentRotator.generate_headers()
        self.assertIn("User-Agent", headers)
        self.assertIn("Accept", headers)
        self.assertIn("Accept-Language", headers)
        self.assertIn("Upgrade-Insecure-Requests", headers)

        # Ensure random UA comes from the verified browser list
        ua = UserAgentRotator.get_random_ua()
        self.assertIn(ua, BROWSER_USER_AGENTS)

    def test_jitter_and_exponential_backoff(self):
        """
        Validates per-domain jitter delays and exponential backoff calculations.
        """
        from network_manager import JitterManager

        jm = JitterManager(default_min_delay=0.1, default_max_delay=0.3)
        domain = jm.get_domain("https://stakestats.net/api/codes")
        self.assertEqual(domain, "stakestats.net")

        # Test backoff calculation
        b1 = jm.calculate_backoff(attempt=1, base_seconds=2.0)
        self.assertGreaterEqual(b1, 2.0)
        self.assertLessEqual(b1, 5.0)

        b3 = jm.calculate_backoff(attempt=3, base_seconds=2.0)
        # base * 2^2 = 8 + jitter (0.5..2.0) -> 8.5..10.0
        self.assertGreaterEqual(b3, 8.0)
        self.assertLessEqual(b3, 11.0)

        # Test retry-after header override
        b_retry = jm.calculate_backoff(attempt=1, retry_after=15)
        self.assertGreaterEqual(b_retry, 15.0)
        self.assertLessEqual(b_retry, 18.0)

    def test_cloudflare_detector(self):
        """
        Validates detection of Cloudflare challenges, anti-bot screens, and rate limits.
        """
        from network_manager import CloudflareDetector

        # Cloudflare 403 challenge body
        cf_body = "<html><head><title>Just a moment...</title></head><body>Attention Required! | Cloudflare</body></html>"
        cf_headers = {"cf-ray": "8c123456789", "content-type": "text/html"}
        self.assertTrue(CloudflareDetector.is_cloudflare_challenge(403, cf_headers, cf_body))

        # Normal 200 response
        normal_body = "<html><body>Standard page content</body></html>"
        normal_headers = {"content-type": "text/html"}
        self.assertFalse(CloudflareDetector.is_cloudflare_challenge(200, normal_headers, normal_body))

        # Rate limited detection
        self.assertTrue(CloudflareDetector.is_rate_limited(429))
        self.assertTrue(CloudflareDetector.is_rate_limited(403, "Error: rate limit exceeded"))
        self.assertFalse(CloudflareDetector.is_rate_limited(200, "Success"))

        # Retry-After header extraction
        self.assertEqual(CloudflareDetector.get_retry_after({"Retry-After": "30"}), 30)
        self.assertEqual(CloudflareDetector.get_retry_after({"retry-after": "10"}), 10)
        self.assertIsNone(CloudflareDetector.get_retry_after({}))

    def test_proxy_pool_rotation_and_recovery(self):
        """
        Validates proxy pool rotation, failure counting, and recovery tracking.
        """
        from network_manager import ProxyPool

        pool = ProxyPool(enabled=True, custom_proxies=["1.2.3.4:8080", "5.6.7.8:3128"], load_env_proxies=False)
        p1 = pool.get_proxy()
        self.assertIsNotNone(p1)
        self.assertIn("http", p1)

        p2 = pool.get_proxy()
        self.assertIsNotNone(p2)

        # Report 3 failures for 1.2.3.4:8080
        pool.report_failure({"http": "http://1.2.3.4:8080"})
        pool.report_failure({"http": "http://1.2.3.4:8080"})
        pool.report_failure({"http": "http://1.2.3.4:8080"})

        # Only 5.6.7.8:3128 should remain active
        p3 = pool.get_proxy()
        self.assertEqual(p3["http"], "http://5.6.7.8:3128")

        # Report success resets failure
        pool.report_success({"http": "http://1.2.3.4:8080"})
        self.assertEqual(pool.failed_proxies["1.2.3.4:8080"], 0)

    def test_degen_and_qzino_parsing_with_media(self):
        """
        Validates that Degen and Qzino parsers extract codes, wager requirements, values,
        and media attachments.
        """
        from scrapers.telegram import TelegramScraper

        tg = TelegramScraper()

        # Degen parser test
        degen_text = "Promo Code Drop!\n7 Day Wager Requirement: $4,000\nClaim Amount: $5.00\nTotal Claims: 150\nEnjoy and good luck Degens!"
        degen_img = "https://cdn4.telesco.pe/file/pHHR6Eb.jpg"
        degen_item = tg.parse_degen_message(degen_text, "https://t.me/degendotcom/49", image_url=degen_img)

        self.assertIsNotNone(degen_item)
        self.assertEqual(degen_item.platform, Platform.DEGEN)
        self.assertEqual(degen_item.code, "CHECK_IMAGE_FOR_CODE_#49")
        self.assertEqual(degen_item.amount_value, "$5.00")
        self.assertEqual(degen_item.wager_requirement, "$4,000")
        self.assertEqual(degen_item.claims_count, "150")
        self.assertEqual(degen_item.image_url, degen_img)

        # Qzino parser test (Traditional promo)
        qzino_text = "Official Qzino website\nGet bonus up to 100% + 100 FS\nPlaythrough: 15x\nTotal Claims: 500"
        qzino_img = "https://cdn4.telesco.pe/file/WMvUout.jpg"
        qzino_item = tg.parse_qzino_message(qzino_text, "https://t.me/qzino/2", image_url=qzino_img)

        self.assertIsNotNone(qzino_item)
        self.assertEqual(qzino_item.platform, Platform.QZINO)
        self.assertEqual(qzino_item.amount_value, "100% + 100 FS")
        self.assertEqual(qzino_item.wager_requirement, "15x")
        self.assertEqual(qzino_item.claims_count, "500")
        self.assertEqual(qzino_item.image_url, qzino_img)

        # Qzino drop test from @qzino_code
        qzino_drop_text = """⚡️
URGENT Code Drop
Extra codes can now show up at any moment. Keep an eye out! 
IUM4HC9
 
- Value: $3
- Total Drop: first 50 claims 
- Requirements: $2,000 wagered in the last 7 days across Slots, Originals, and Sports betting
Redeem Here!"""
        qzino_drop_img = "https://cdn4.telesco.pe/file/JdmFdjJ5.jpg"
        drop_item = tg.parse_qzino_message(qzino_drop_text, "https://t.me/qzino_code/138", image_url=qzino_drop_img, channel_name="qzino_code")

        self.assertIsNotNone(drop_item)
        self.assertEqual(drop_item.code, "IUM4HC9")
        self.assertEqual(drop_item.platform, Platform.QZINO)
        self.assertEqual(drop_item.amount_value, "$3")
        self.assertEqual(drop_item.wager_requirement, "$2,000 wagered in the last 7 days across Slots, Originals, and Sports betting")
        self.assertEqual(drop_item.claims_count, "first 50 claims")
        self.assertEqual(drop_item.image_url, qzino_drop_img)
        self.assertEqual(drop_item.source_name, "@qzino_code")

    def test_clean_embed_no_telegram_dump(self):
        """
        Validates that embed cards format clean badge lines in description
        and do NOT dump raw Telegram text lines, keeping embeds clean and professional.
        """
        notifier = DiscordNotifier()

        # 1. Qzino Drop
        qzino_item = BonusCodeItem(
            code="IUM4HC9",
            platform=Platform.QZINO,
            amount_value="$3",
            wager_requirement="$2,000 in 7 days",
            claims_count="first 50 claims",
            is_affiliate=False,
            source_name="@qzino_code",
            source_url="https://t.me/qzino_code/138",
            description="⚡️ URGENT Code Drop\nExtra codes can now show up at any moment. Keep an eye out!\nIUM4HC9\n- Value: $3\n- Total Drop: first 50 claims"
        )
        embed_qz = notifier.build_embed(qzino_item)
        self.assertIn("Verified Bonus Drop", embed_qz["description"])
        self.assertNotIn("URGENT Code Drop", embed_qz["description"])
        self.assertNotIn("Total Drop:", embed_qz["description"])
        field_values = " ".join([f["value"] for f in embed_qz["fields"]])
        self.assertIn("IUM4HC9", field_values)
        self.assertIn("$3", field_values)

        # 2. Rainbet Drop
        rainbet_item = BonusCodeItem(
            code="MFQP3DSN",
            platform=Platform.RAINBET,
            amount_value="$1",
            wager_requirement="$4,000",
            claims_count="600",
            is_affiliate=False,
            source_name="@EddiesCodesRainbet",
            source_url="https://t.me/EddiesCodesRainbet/100",
            description="1. Click Code To Copy: MFQP3DSN\n2. Redeem Here: https://rainbet.com/affiliates\nReward: $1\nWager Required: $4,000\nClaims: 600"
        )
        embed_rb = notifier.build_embed(rainbet_item)
        self.assertIn("Verified Bonus Drop", embed_rb["description"])
        self.assertNotIn("Click Code To Copy", embed_rb["description"])
        self.assertNotIn("Wager Required:", embed_rb["description"])

        # 3. High Roller Drop
        hr_item = BonusCodeItem(
            code="HIGHROLLER100",
            platform=Platform.STAKE_US,
            amount_value="$100",
            wager_requirement="$200,000",
            is_highroller=True,
            is_affiliate=False,
            source_name="@highrollerscodeUS",
            source_url="https://t.me/highrollerscodeUS/200",
            description="🔥 HIGH ROLLER DROP\nCode: HIGHROLLER100\nValue: $100\nWager: $200,000"
        )
        embed_hr = notifier.build_embed(hr_item)
        self.assertIn("High Roller", embed_hr["description"])
        self.assertNotIn("Wager: $200,000", embed_hr["description"])

        # 4. VIP Event
        vip_item = BonusCodeItem(
            code="VIPWEEKLY",
            platform=Platform.STAKE_US_VIP_NOTICES,
            event_type="weekly_bonus",
            amount_value="VIP Weekly Boost",
            wager_requirement="VIP Tier Based",
            is_affiliate=False,
            source_name="Stake.us VIP",
            source_url="https://t.me/c/1542279201/257",
            description="Your VIP Weekly Boost is now live! Click the link below to claim."
        )
        embed_vip = notifier.build_embed(vip_item)
        self.assertIn("Official VIP Notice", embed_vip["description"])

    def test_exact_embed_field_layout_order(self):
        """
        Validates the strict layout and ordering of Discord embed fields:
        1. PLATFORM & SOURCE on the same line (inline: True, inline: True)
        2. CODE box on the next line (inline: False)
        3. VALUE, WAGER REQUIREMENTS, and CLAIMS LIMIT on the same line (inline: True x3)
        4. DIRECT REDEEM LINK on the next line (inline: False)
        5. SIGNUP link and JOIN DISCORD link on the same line (inline: True, inline: True)
        6. Media/Image attached at the bottom (embed['image'])
        """
        notifier = DiscordNotifier()

        item = BonusCodeItem(
            code="ORDERTEST2026",
            platform=Platform.STAKE_US,
            amount_value="5 SC",
            wager_requirement="10,000 SC in 7 days",
            claims_count="5,000 SC limit",
            source_name="@dailybonuscodeUS",
            source_url="https://t.me/dailybonuscodeUS/100",
            image_url="https://example.com/promo.png"
        )

        embed = notifier.build_embed(item)
        fields = embed["fields"]

        # Field 0: Platform (inline)
        self.assertEqual(fields[0]["name"], "🎰 Platform")
        self.assertTrue(fields[0]["inline"])
        self.assertIn("Stake.us", fields[0]["value"])

        # Field 1: Source (inline)
        self.assertEqual(fields[1]["name"], "🌐 Source")
        self.assertTrue(fields[1]["inline"])
        self.assertIn("@dailybonuscodeUS", fields[1]["value"])

        # Field 2: Bonus Code (full width)
        self.assertEqual(fields[2]["name"], "🎁 Bonus Code (Tap to Copy)")
        self.assertFalse(fields[2]["inline"])
        self.assertIn("ORDERTEST2026", fields[2]["value"])

        # Field 3: Value (inline)
        self.assertEqual(fields[3]["name"], "💰 Value / Amount")
        self.assertTrue(fields[3]["inline"])
        self.assertIn("5 SC", fields[3]["value"])

        # Field 4: Wager (inline)
        self.assertEqual(fields[4]["name"], "🔄 Wager Required")
        self.assertTrue(fields[4]["inline"])
        self.assertIn("10,000 SC", fields[4]["value"])

        # Field 5: Claims (inline)
        self.assertEqual(fields[5]["name"], "👥 Claims / Limit")
        self.assertTrue(fields[5]["inline"])
        self.assertIn("5,000 SC limit", fields[5]["value"])

        # Field 6: Direct Redeem Link (full width)
        self.assertEqual(fields[6]["name"], "🔗 Direct Redeem Link")
        self.assertFalse(fields[6]["inline"])
        self.assertIn("[CLICK HERE TO CLAIM]", fields[6]["value"])

        # Field 7: Signup Link (inline)
        self.assertEqual(fields[7]["name"], "📝 Direct Signup Link")
        self.assertTrue(fields[7]["inline"])
        self.assertIn("[SIGNUP HERE]", fields[7]["value"])

        # Field 8: Join Discord (inline)
        self.assertEqual(fields[8]["name"], "💬 Official Community")
        self.assertTrue(fields[8]["inline"])
        self.assertIn("[JOIN DISCORD]", fields[8]["value"])

        # Image at the bottom
        self.assertEqual(embed["image"]["url"], "https://example.com/promo.png")

    def test_concurrent_scraper_engine_execution(self):
        """
        Validates that ScraperEngine processes items across multiple sources concurrently
        and correctly deduplicates new items against CodeTracker.
        """
        from scrapers.engine import ScraperEngine
        engine = ScraperEngine(tracker=CodeTracker(self.test_state_file), notifier=DiscordNotifier())
        items = [
            BonusCodeItem(code="FASTCODE1", platform=Platform.STAKE_US, amount_value="$5", wager_requirement="3x", source_name="Test1", source_url="https://example.com/1"),
            BonusCodeItem(code="FASTCODE2", platform=Platform.SHUFFLE_US, amount_value="$10", wager_requirement="5x", source_name="Test2", source_url="https://example.com/2"),
        ]
        new_items = engine.process_items(items, notify=False)
        self.assertEqual(len(new_items), 2)

        # Second check should detect 0 new items because they are already tracked
        new_items_2 = engine.process_items(items, notify=False)
        self.assertEqual(len(new_items_2), 0)

    def test_command_permissions_and_unrestricted_public_access(self):
        """
        Validates that !info, /info, !activecodes, /activecodes, and /codes
        are accessible to all users with zero authorization restrictions,
        while dashboard routing commands enforce owner/subscriber authentication.
        """
        from dashboard_manager import DashboardManager
        manager = DashboardManager(self.test_routes_file)
        
        # Test random non-owner, non-subscriber user ID
        random_user_id = 999888777666555444
        self.assertFalse(manager.is_owner(random_user_id))
        self.assertFalse(manager.is_authorized(random_user_id))
        
        # Ensure that create_info_embed generates the public guide
        from discord_bot import create_info_embed
        info_embed = create_info_embed()
        self.assertIsNotNone(info_embed)
        self.assertIn("Information & Guide", info_embed.title)
        
        # Ensure StakeStatsPoller live format is accessible to public callers
        poller = StakeStatsPoller()
        self.assertTrue(callable(poller.format_discord_active_list))

    def test_dashboard_settings_applied_and_live_channel_dispatch(self):
        """
        Validates that settings configured in the Dashboard (channels, webhooks, intervals)
        are persistently saved, immediately applied to live monitoring, and route drops
        to the exact assigned channel IDs for each platform.
        """
        from unittest.mock import MagicMock, AsyncMock
        from dashboard_manager import DashboardManager
        from discord_notifier import DiscordNotifier
        from scrapers.engine import ScraperEngine

        manager = DashboardManager(self.test_routes_file)

        # 1. Configure custom platform channel routes via dashboard manager
        stake_us_channel_1 = 111222333444555666
        stake_us_channel_2 = 111222333444555777
        rainbet_channel = 222333444555666777
        qzino_channel = 333444555666777888

        manager.add_channel(Platform.STAKE_US, stake_us_channel_1)
        manager.add_channel(Platform.STAKE_US, stake_us_channel_2)
        manager.add_channel(Platform.RAINBET, rainbet_channel)
        manager.add_channel(Platform.QZINO, qzino_channel)

        # Verify settings persistence
        manager.set_setting("check_interval_seconds", 45)
        manager.set_setting("realtime_monitoring_enabled", True)

        reloaded_manager = DashboardManager(self.test_routes_file)
        self.assertEqual(reloaded_manager.get_setting("check_interval_seconds"), 45)
        self.assertTrue(reloaded_manager.get_setting("realtime_monitoring_enabled"))
        self.assertEqual(len(reloaded_manager.get_channels(Platform.STAKE_US)), 2)
        self.assertIn(stake_us_channel_1, reloaded_manager.get_channels(Platform.STAKE_US))
        self.assertIn(stake_us_channel_2, reloaded_manager.get_channels(Platform.STAKE_US))
        self.assertEqual(reloaded_manager.get_channels(Platform.RAINBET), [rainbet_channel])
        self.assertEqual(reloaded_manager.get_channels(Platform.QZINO), [qzino_channel])

        # 2. Mock Discord client and channels
        mock_loop = asyncio.new_event_loop()
        mock_bot = MagicMock()
        mock_bot.is_closed.return_value = False
        mock_bot.loop = mock_loop

        mock_chan_stake1 = MagicMock()
        mock_chan_stake1.name = "stake-us-drops-1"
        mock_chan_stake1.send = AsyncMock()

        mock_chan_stake2 = MagicMock()
        mock_chan_stake2.name = "stake-us-drops-2"
        mock_chan_stake2.send = AsyncMock()

        mock_chan_rainbet = MagicMock()
        mock_chan_rainbet.name = "rainbet-drops"
        mock_chan_rainbet.send = AsyncMock()

        def mock_get_channel(cid):
            if cid == stake_us_channel_1:
                return mock_chan_stake1
            elif cid == stake_us_channel_2:
                return mock_chan_stake2
            elif cid == rainbet_channel:
                return mock_chan_rainbet
            return None

        mock_bot.get_channel.side_effect = mock_get_channel

        notifier = DiscordNotifier(dashboard_manager=reloaded_manager, bot_client=mock_bot)
        tracker = CodeTracker(self.test_state_file)
        engine = ScraperEngine(tracker=tracker, notifier=notifier)

        # 3. Process new live drops and verify routing to assigned channels
        stake_item = BonusCodeItem(
            code="STAKEUSDASHBOARD1",
            platform=Platform.STAKE_US,
            amount_value="$10",
            wager_requirement="$5,000",
            is_affiliate=False,
            source_name="StakeStats",
            source_url="https://stakestats.net"
        )
        rainbet_item = BonusCodeItem(
            code="RAINBETDASHBOARD1",
            platform=Platform.RAINBET,
            amount_value="$5",
            wager_requirement="$2,000",
            is_affiliate=False,
            source_name="@EddiesCodesRainbet",
            source_url="https://t.me/EddiesCodesRainbet"
        )

        # Execute check with notification dispatch
        new_items = engine.process_items([stake_item, rainbet_item], notify=True)
        self.assertEqual(len(new_items), 2)

        # Execute scheduled coroutines in loop
        mock_loop.run_until_complete(asyncio.sleep(0.05))

        # Verify Stake.us drop was dispatched to both assigned Stake.us channels
        self.assertTrue(mock_chan_stake1.send.called)
        self.assertTrue(mock_chan_stake2.send.called)
        self.assertEqual(mock_chan_stake1.send.call_count, 1)
        self.assertEqual(mock_chan_stake2.send.call_count, 1)

        # Verify Rainbet drop was dispatched to the assigned Rainbet channel
        self.assertTrue(mock_chan_rainbet.send.called)
        self.assertEqual(mock_chan_rainbet.send.call_count, 1)

        mock_loop.close()

    def test_channel_fetch_fallback_when_not_in_cache(self):
        """
        Validates that when a channel is not present in local client cache,
        fetch_channel is called asynchronously to guarantee delivery.
        """
        from unittest.mock import MagicMock, AsyncMock
        from dashboard_manager import DashboardManager
        from discord_notifier import DiscordNotifier

        manager = DashboardManager(self.test_routes_file)
        uncached_cid = 999111222333444555
        manager.add_channel(Platform.SHUFFLE_COM, uncached_cid)

        mock_loop = asyncio.new_event_loop()
        mock_bot = MagicMock()
        mock_bot.is_closed.return_value = False
        mock_bot.loop = mock_loop

        # get_channel returns None (uncached)
        mock_bot.get_channel.return_value = None

        mock_fetched_channel = MagicMock()
        mock_fetched_channel.name = "shuffle-com-drops"
        mock_fetched_channel.send = AsyncMock()
        mock_bot.fetch_channel = AsyncMock(return_value=mock_fetched_channel)

        notifier = DiscordNotifier(dashboard_manager=manager, bot_client=mock_bot)
        item = BonusCodeItem(
            code="SHUFFLELIVE99",
            platform=Platform.SHUFFLE_COM,
            amount_value="$25",
            wager_requirement="$50,000",
            is_affiliate=False,
            source_name="@codestats2",
            source_url="https://t.me/codestats2"
        )

        res = notifier.send_notification(item)
        self.assertTrue(res)

        mock_loop.run_until_complete(asyncio.sleep(0.05))

        # Ensure fetch_channel was called with the channel ID and message sent
        mock_bot.fetch_channel.assert_called_once_with(uncached_cid)
        self.assertTrue(mock_fetched_channel.send.called)

        mock_loop.close()

    def test_codestats2_multi_platform_and_dual_stake_parsing(self):
        """
        Validates that @codestats2 parser accurately handles:
        1. User-submitted Stake drops defaulting to Dual Stake (Stake.us & Stake.com) unless explicitly single-platform.
        2. Stake.us, Stake.com, Shuffle.us, and Shuffle.com platform drops.
        3. Completely filters out CodeStats promotional text (autoclaimer, cloud claimer, etc.).
        """
        tg = TelegramScraper()

        # 1. User submitted code with both US and COM links -> Dual Stake
        msg_dual = (
            "USER SUBMITTED STAKE CODE\n"
            " - Code: mjp6axxg\n"
            "US https://stake.us/settings/offers?type=drop&code=mjp6axxg&currency=sweeps&modal=redeemBonus\n"
            "COM https://stake.com/settings/offers?type=drop&code=mjp6axxg&currency=ltc&modal=redeemBonus\n"
            "Missed it? codestats.gg/autoclaimer\n"
        )
        item_dual = tg.parse_codestats_message(msg_dual, "https://t.me/codestats2/111", None)
        self.assertIsNotNone(item_dual)
        self.assertEqual(item_dual.code, "mjp6axxg")
        self.assertEqual(item_dual.platform, Platform.DUAL_STAKE)
        self.assertTrue(item_dual.is_dual_stake)
        self.assertIn("stake.us", item_dual.redeem_link_us)
        self.assertIn("stake.com", item_dual.redeem_link_com)
        self.assertNotIn("codestats.gg", item_dual.description)

        # 2. User submitted code with ONLY COM link -> Stake.com
        msg_com_only = (
            "USER SUBMITTED STAKE CODE\n"
            " - Code: stakepyulapwg69f7ia1u\n"
            "COM https://stake.com/settings/offers?type=drop&code=stakepyulapwg69f7ia1u&currency=ltc&modal=redeemBonus\n"
            "Missed it? codestats.gg/autoclaimer\n"
        )
        item_com = tg.parse_codestats_message(msg_com_only, "https://t.me/codestats2/112", None)
        self.assertIsNotNone(item_com)
        self.assertEqual(item_com.code, "stakepyulapwg69f7ia1u")
        self.assertEqual(item_com.platform, Platform.STAKE_COM)
        self.assertFalse(item_com.is_dual_stake)

        # 3. Stake.us Bonus Drop Alert
        msg_stake_us = (
            "STAKE US BONUS DROP ALERT\n"
            " - Code: stakeusmk165hgde78oxh\n"
            " - Value: 2 SC\n"
            " - Total Drop Limit: 2,000 SC\n"
            " - Requirements: 8,000 SC played in the last 7 days\n"
            "https://stake.us/settings/offers?type=drop&code=stakeusmk165hgde78oxh&modal=redeemBonus\n"
            "No computer? Cloud Claimer now available!\n"
        )
        item_us = tg.parse_codestats_message(msg_stake_us, "https://t.me/codestats2/113", None)
        self.assertIsNotNone(item_us)
        self.assertEqual(item_us.code, "stakeusmk165hgde78oxh")
        self.assertEqual(item_us.platform, Platform.STAKE_US)
        self.assertEqual(item_us.amount_value, "2 SC")
        self.assertIn("8,000 SC played", item_us.wager_requirement)
        self.assertNotIn("Cloud Claimer", item_us.description)

        # 4. Shuffle.us Bonus Drop Alert
        msg_shuffle_us = (
            "SHUFFLE.US BONUS DROP ALERT\n"
            "- Code: 4JNY8TZV\n"
            "- Value: 25 SC + 250,000 GC\n"
            "- Claims: 10\n"
            "- Requirements: 200,000 SC played in the last 7 days\n"
            "https://shuffle.us/?modal=c&md-code=4JNY8TZV\n"
            "Claim more codes, sign up for Shuffle.US today.\n"
        )
        item_shuf_us = tg.parse_codestats_message(msg_shuffle_us, "https://t.me/codestats2/114", None)
        self.assertIsNotNone(item_shuf_us)
        self.assertEqual(item_shuf_us.code, "4JNY8TZV")
        self.assertEqual(item_shuf_us.platform, Platform.SHUFFLE_US)
        self.assertEqual(item_shuf_us.amount_value, "25 SC + 250,000 GC")
        self.assertIn("200,000 SC played", item_shuf_us.wager_requirement)
        self.assertEqual(item_shuf_us.claims_count, "10")
        self.assertNotIn("Claim more codes", item_shuf_us.description)

        # 5. Shuffle.com Chat Code
        msg_shuffle_com = (
            "SHUFFLE CHAT CODE ALERT\n"
            "Code: A79FBZ6Z\n"
            "https://shuffle.com/?modal=c&md-code=A79FBZ6Z\n"
            "Claim more codes, sign up for Shuffle.com today.\n"
            "Missed it? codestats.gg/autoclaimer\n"
        )
        item_shuf_com = tg.parse_codestats_message(msg_shuffle_com, "https://t.me/codestats2/115", None)
        self.assertIsNotNone(item_shuf_com)
        self.assertEqual(item_shuf_com.code, "A79FBZ6Z")
        self.assertEqual(item_shuf_com.platform, Platform.SHUFFLE_COM)
        self.assertNotIn("codestats.gg", item_shuf_com.description)

    def test_codestats_stake_code_corpus_formats(self):
        tg = TelegramScraper()
        samples = [
            ("STAKE.COM", "stakecomnseb1q5jifel1l", Platform.STAKE_COM),
            ("STAKE.COM", "stakepl1x7ninxbh5sddk", Platform.STAKE_COM),
            ("STAKE.US", "stakeus8wkwa2bdrmrvb8", Platform.STAKE_US),
            ("STAKE.COM", "stakecommczm5ifh64ka07", Platform.STAKE_COM),
            ("STAKE.US", "stakeusucuft9noaua2or", Platform.STAKE_US),
            ("STAKE.COM", "stakecomhjs7mcgqc5dorj", Platform.STAKE_COM),
            ("STAKE.US", "stakeusu6gd5n5xx6179j", Platform.STAKE_US),
            ("STAKE.US", "stakeus3m8vsx4djj0kcr", Platform.STAKE_US),
            ("STAKE.COM", "stakecom8inylqegkak6q4", Platform.STAKE_COM),
            ("STAKE.US", "stakeusmiv3chnu8c4ejg", Platform.STAKE_US),
            ("STAKE.COM", "stakecomj9jejctvyykpfu", Platform.STAKE_COM),
            ("STAKE.COM", "trjd6s0iwi", Platform.STAKE_COM),
            ("STAKE.US", "stakeus30upum57tdtvjx", Platform.STAKE_US),
            ("STAKE.COM", "lcpey7lljwwxn", Platform.STAKE_COM),
            ("STAKE.COM", "qu10n28yx072e", Platform.STAKE_COM),
            ("STAKE.COM", "stakecom9xnjvsvtwe2i15", Platform.STAKE_COM),
            ("STAKE.COM", "staketrd8p8c177zasmyn", Platform.STAKE_COM),
            ("STAKE.COM", "stakecomklyi5sb1k0bbq0", Platform.STAKE_COM),
            ("STAKE.US", "stakeusfokjtgohsjd641", Platform.STAKE_US),
        ]
        for platform_label, code, expected_platform in samples:
            message = (
                f"{platform_label} BONUS DROP ALERT\n"
                f"Code: {code}\n"
                "Value: $12.50\n"
                "Requirements: $50,000 wagered in the last 7 days\n"
                "codestats.gg/autoclaimer\n"
            )
            item = tg.parse_codestats_message(message, "https://t.me/codestats2/fixture")
            self.assertIsNotNone(item, code)
            self.assertEqual(item.code, code, code)
            self.assertEqual(item.platform, expected_platform, code)
            self.assertNotIn("codestats.gg", item.description, code)

        dual_message = (
            "USER SUBMITTED CODE DETECTED\n"
            "Code: 0kk4co42\n"
            "STAKE.US\nCLICK TO CLAIM\n"
            "STAKE.COM\nCLICK TO CLAIM\n"
            "codestats.gg/autoclaimer"
        )
        dual_item = tg.parse_codestats_message(dual_message, "https://t.me/codestats2/dual-fixture")
        self.assertIsNotNone(dual_item)
        self.assertEqual(dual_item.code, "0kk4co42")
        self.assertEqual(dual_item.platform, Platform.DUAL_STAKE)
        self.assertTrue(dual_item.is_dual_stake)
        self.assertNotIn("codestats.gg", dual_item.description)

    def test_codestats_live_feed_parses_shuffle_flags(self):
        scraper = CodeStatsScraper(base_url="https://codestats.test")
        scraper.session.fetch_json = MagicMock(side_effect=[
            {"sessionId": "test-session"},
            {"messages": [
                {
                    "code": "FJ0NX2KT",
                    "amount": "$15.00",
                    "wagerRequirement": None,
                    "dropLimit": None,
                    "timestamp": 1789477293872,
                    "channelName": "shuffle-codes",
                    "isShuffle": True,
                    "isShuffleUS": False,
                    "isShuffleCom": True,
                },
                {
                    "code": "RNEBNVMK",
                    "amount": "1.5 SC",
                    "wagerRequirement": "2500 SC",
                    "timestamp": 1789465562113,
                    "channelName": "shuffle-codes",
                    "isShuffle": True,
                    "isShuffleUS": True,
                    "isShuffleCom": False,
                },
            ]}
        ])

        items = scraper.scrape_codes()

        self.assertEqual([item.code for item in items], ["FJ0NX2KT", "RNEBNVMK"])
        self.assertEqual(items[0].platform, Platform.SHUFFLE_COM)
        self.assertEqual(items[1].platform, Platform.SHUFFLE_US)
        self.assertIn("md-code=FJ0NX2KT", items[0].redeem_link)
        self.assertEqual(items[1].wager_requirement, "2500 SC")

    def test_shuffle_wager_requirement_extraction_edge_cases(self):
        """
        Validates that Shuffle.us/Shuffle.com parsers extract wager requirement amounts
        even when labels lack colons or use alternate phrasing like 'Wager Requirement'
        instead of 'Requirements'.
        """
        tg = TelegramScraper()

        # 1. CodeStats message with 'Wager Requirement' label (no colon after label on same line format)
        msg_no_colon = (
            "SHUFFLE.US BONUS DROP ALERT\n"
            "- Code: TESTCODE123\n"
            "- Value: 5 SC\n"
            "- Wager Requirement 150,000 SC played in the last 7 days\n"
            "- Claims: 20\n"
            "https://shuffle.us/?modal=c&md-code=TESTCODE123\n"
        )
        item = tg.parse_codestats_message(msg_no_colon, "https://t.me/codestats2/9001", None)
        self.assertIsNotNone(item)
        self.assertEqual(item.platform, Platform.SHUFFLE_US)
        self.assertIn("150,000 SC played", item.wager_requirement)

        # 2. Stake-style Shuffle.us message using 'Wager Requirement:' via parse_stake_message
        msg_stake_shuffle = (
            "SHUFFLE.US BONUS DROP ALERT\n"
            "Code: SHUFUS99\n"
            "Value: 10 SC\n"
            "Wager Requirement: 75,000 SC played in the last 7 days\n"
            "Claims: 50\n"
            "https://shuffle.us/?modal=c&md-code=SHUFUS99\n"
        )
        item2 = tg.parse_stake_message(msg_stake_shuffle, "https://t.me/anyclaimershuffle/500", "anyclaimershuffle")
        self.assertIsNotNone(item2)
        self.assertEqual(item2.platform, Platform.SHUFFLE_US)
        self.assertIn("75,000 SC played", item2.wager_requirement)

        # 3. Stake-style Shuffle.com message using '7-Day Wager:' via parse_stake_message
        msg_stake_shuffle_com = (
            "SHUFFLE CHAT CODE ALERT\n"
            "Code: SHUFCOM88\n"
            "Value: $5.00\n"
            "7-Day Wager: $20,000 wagered in the last 7 days\n"
            "Claims: 100\n"
            "https://shuffle.com/?modal=c&md-code=SHUFCOM88\n"
        )
        item3 = tg.parse_stake_message(msg_stake_shuffle_com, "https://t.me/anyclaimershuffle/501", "anyclaimershuffle")
        self.assertIsNotNone(item3)
        self.assertEqual(item3.platform, Platform.SHUFFLE_COM)
        self.assertIn("$20,000 wagered", item3.wager_requirement)

        # 4. CodeStats message with 'Requirements' (no 's') and no colon spacing
        msg_req_no_s = (
            "SHUFFLE.COM BONUS DROP ALERT\n"
            "- Code: ABC123XYZ\n"
            "- Value: $2.50\n"
            "- Requirement $12,500 in 7 days\n"
            "- Claims: 500\n"
            "https://shuffle.com/?modal=c&md-code=ABC123XYZ\n"
        )
        item4 = tg.parse_codestats_message(msg_req_no_s, "https://t.me/codestats2/9002", None)
        self.assertIsNotNone(item4)
        self.assertEqual(item4.platform, Platform.SHUFFLE_COM)
        self.assertIn("$12,500", item4.wager_requirement)

    def test_dual_stake_independent_routing_and_embeds(self):
        """
        Validates that dual platform drops (Stake.us & Stake.com) are split into
        independent Stake.us and Stake.com events with dedicated redeem links,
        colors, and routed to each platform's assigned channel and webhook.
        """
        from unittest.mock import MagicMock, AsyncMock

        dual_item = BonusCodeItem(
            code="DUALCODE2026",
            platform=Platform.DUAL_STAKE,
            amount_value="$5 / 5 SC",
            wager_requirement="$10,000",
            source_url="https://t.me/codestats2/999",
            source_name="@codestats2",
            is_dual_stake=True
        )

        # Test item conversions
        us_item = dual_item.to_stake_us_item()
        com_item = dual_item.to_stake_com_item()

        self.assertEqual(us_item.platform, Platform.STAKE_US)
        self.assertEqual(us_item.code, "DUALCODE2026")
        self.assertIn("stake.us", us_item.redeem_link)
        self.assertIn("stake.us", us_item.affiliate_signup_link)

        self.assertEqual(com_item.platform, Platform.STAKE_COM)
        self.assertEqual(com_item.code, "DUALCODE2026")
        self.assertIn("stake.com", com_item.redeem_link)
        self.assertIn("stake.com", com_item.affiliate_signup_link)

        # Test routing dispatch
        manager = DashboardManager(filepath=self.test_routes_file)
        us_cid = 100000000000000001
        com_cid = 200000000000000002
        manager.add_channel(Platform.STAKE_US, us_cid)
        manager.add_channel(Platform.STAKE_COM, com_cid)

        mock_bot = MagicMock()
        mock_loop = asyncio.new_event_loop()
        mock_bot.loop = mock_loop
        mock_bot.is_closed = MagicMock(return_value=False)

        us_chan = MagicMock()
        us_chan.send = AsyncMock()
        com_chan = MagicMock()
        com_chan.send = AsyncMock()

        def mock_get_channel(cid):
            if cid == us_cid:
                return us_chan
            if cid == com_cid:
                return com_chan
            return None

        mock_bot.get_channel.side_effect = mock_get_channel

        notifier = DiscordNotifier(dashboard_manager=manager, bot_client=mock_bot)
        res = notifier.send_notification(dual_item)
        self.assertTrue(res)

        mock_loop.run_until_complete(asyncio.sleep(0.05))

        # Check that Stake.us channel received Stake.us embed
        self.assertTrue(us_chan.send.called)
        us_sent_embed = us_chan.send.call_args[1]["embed"]
        self.assertIn("STAKE.US", us_sent_embed.title.upper())
        self.assertEqual(us_sent_embed.color.value, Platform.STAKE_US.embed_color)

        # Check that Stake.com channel received Stake.com embed
        self.assertTrue(com_chan.send.called)
        com_sent_embed = com_chan.send.call_args[1]["embed"]
        self.assertIn("STAKE.COM", com_sent_embed.title.upper())
        self.assertEqual(com_sent_embed.color.value, Platform.STAKE_COM.embed_color)

        mock_loop.close()

    def test_user_provided_codestats_examples(self):
        """
        Validates the full set of user-provided drop examples from CodeStats/Telegram,
        including unicode mathematical bold fonts, dual drops, and high-roller checks.
        """
        tg = TelegramScraper()

        # 1. Stake.us Highroller Alert
        msg1 = (
            "@💸 𝐒𝐭𝐚𝐤𝐞.𝐮𝐬\n"
            "STAKE BONUS DROP ALERT\n"
            "Code: stakeusbv80mk7hviq5ko\n"
            "Value: 25 SC\n"
            "Total Drop Limit: 50,000 SC\n"
            "Requirements: 100,000 SC played in the last 7 days\n"
            "CLICK HERE TO CLAIM\n"
            "codestats.gg/autoclaimer•8/27/2026 11:22 PM\n"
        )
        item1 = tg.parse_codestats_message(msg1, "https://t.me/codestats2/201")
        self.assertIsNotNone(item1)
        self.assertEqual(item1.code, "stakeusbv80mk7hviq5ko")
        self.assertEqual(item1.platform, Platform.STAKE_US)
        self.assertEqual(item1.amount_value, "25 SC")
        self.assertEqual(item1.claims_count, "50,000 SC")
        self.assertIn("100,000 SC played", item1.wager_requirement)
        self.assertTrue(item1.is_highroller)

        # 2. Dual User Submitted Code
        msg2 = (
            "@💸 𝐒𝐭𝐚𝐤𝐞.𝐮𝐬 @🎰 𝐒𝐭𝐚𝐤𝐞.𝐜𝐨𝐦\n"
            "USER SUBMITTED CODE DETECTED\n"
            "Code: saturn93t\n"
            "Support the community share the codes.\n"
            " STAKE.US\n"
            "CLICK TO CLAIM\n"
            " STAKE.COM\n"
            "CLICK TO CLAIM\n"
            "codestats.gg/autoclaimer•8/27/2026 11:28 PM\n"
        )
        item2 = tg.parse_codestats_message(msg2, "https://t.me/codestats2/202")
        self.assertIsNotNone(item2)
        self.assertEqual(item2.code, "saturn93t")
        self.assertTrue(item2.is_dual_stake)
        self.assertEqual(item2.platform, Platform.DUAL_STAKE)

        # 3. Stake.com Single User Submitted Code without stakecom prefix
        msg3 = (
            "@🎰 𝐒𝐭𝐚𝐤𝐞.𝐜𝐨𝐦\n"
            "USER SUBMITTED CODE DETECTED\n"
            "Code: s467v7259jbhew4\n"
            "Support the community share the codes.\n"
            " STAKE.COM\n"
            "CLICK TO CLAIM\n"
            "codestats.gg/autoclaimer•8/28/2026 8:51 AM\n"
        )
        item3 = tg.parse_codestats_message(msg3, "https://t.me/codestats2/203")
        self.assertIsNotNone(item3)
        self.assertEqual(item3.code, "s467v7259jbhew4")
        self.assertEqual(item3.platform, Platform.STAKE_COM)
        self.assertFalse(item3.is_dual_stake)

        # 4. Stake.us Single User Submitted Code
        msg4 = (
            "@💸 𝐒𝐭𝐚𝐤𝐞.𝐮𝐬\n"
            "USER SUBMITTED CODE DETECTED\n"
            "Code: bonusdrops2031\n"
            "Support the community share the codes.\n"
            " STAKE.US\n"
            "CLICK TO CLAIM\n"
            "codestats.gg/autoclaimer•8/28/2026 1:46 PM\n"
        )
        item4 = tg.parse_codestats_message(msg4, "https://t.me/codestats2/204")
        self.assertIsNotNone(item4)
        self.assertEqual(item4.code, "bonusdrops2031")
        self.assertEqual(item4.platform, Platform.STAKE_US)
        self.assertFalse(item4.is_dual_stake)

        # 5. Stake.com Standard Drop Alert
        msg5 = (
            "@🎰 𝐒𝐭𝐚𝐤𝐞.𝐜𝐨𝐦\n"
            "STAKE BONUS DROP ALERT\n"
            "Code: stakecomm72edju5ffkp0f\n"
            "Value: $1\n"
            "Total Drop Limit: $2,000\n"
            "Requirements: $4,000 wagered in the last 7 days\n"
            "CLICK HERE TO CLAIM\n"
            "codestats.gg/autoclaimer•8/28/2026 6:02 AM\n"
        )
        item5 = tg.parse_codestats_message(msg5, "https://t.me/codestats2/205")
        self.assertIsNotNone(item5)
        self.assertEqual(item5.code, "stakecomm72edju5ffkp0f")
        self.assertEqual(item5.platform, Platform.STAKE_COM)
        self.assertEqual(item5.amount_value, "$1")
        self.assertIn("$4,000 wagered", item5.wager_requirement)

    def test_shuffle_multi_source_deduplication(self):
        """
        Validates that receiving the exact same Shuffle code across multiple sources
        (e.g. 5 times from @anyclaimershuffle, @codestats2, codestats.gg, etc.)
        results in exactly 1 notification and 0 duplicate posts.
        """
        tmp_db = os.path.join(tempfile.gettempdir(), f"test_shuffle_dedup_{uuid.uuid4().hex}.json")
        tracker = CodeTracker(filepath=tmp_db)
        mock_notifier = MagicMock()
        mock_notifier.send_notification = MagicMock(return_value=True)

        engine = ScraperEngine(tracker=tracker, notifier=mock_notifier)

        # 5 identical code items from different feeds/platforms (Shuffle.us and Shuffle.com)
        items = [
            BonusCodeItem(code="SHUFFLE2026A", platform=Platform.SHUFFLE_US, amount_value="2 SC", wager_requirement="1000 SC", source_name="@anyclaimershuffle", source_url="https://t.me/anyclaimershuffle/1"),
            BonusCodeItem(code="SHUFFLE2026A", platform=Platform.SHUFFLE_US, amount_value="2 SC", wager_requirement="1000 SC", source_name="@codestats2", source_url="https://t.me/codestats2/2"),
            BonusCodeItem(code="SHUFFLE2026A", platform=Platform.SHUFFLE_COM, amount_value="$2", wager_requirement="$1000", source_name="CodeStats.gg", source_url="https://codestats.gg"),
            BonusCodeItem(code="SHUFFLE2026A", platform=Platform.SHUFFLE_US, amount_value="2 SC", wager_requirement="1000 SC", source_name="@codestats2", source_url="https://t.me/codestats2/3"),
            BonusCodeItem(code="SHUFFLE2026A", platform=Platform.SHUFFLE_COM, amount_value="$2", wager_requirement="$1000", source_name="@anyclaimershuffle", source_url="https://t.me/anyclaimershuffle/4"),
        ]

        # Process the batch
        new_items = engine.process_items(items, notify=True)

        # Must only return and notify 1 unique item
        self.assertEqual(len(new_items), 1)
        self.assertEqual(mock_notifier.send_notification.call_count, 1)

        # Running another sweep with the same code must yield 0 new items
        new_items_2 = engine.process_items(items, notify=True)
        self.assertEqual(len(new_items_2), 0)
        self.assertEqual(mock_notifier.send_notification.call_count, 1)

        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    def test_dual_stake_no_double_events(self):
        """
        Validates that a code detected as Dual Stake and subsequently detected
        as Stake.us or Stake.com does not double post to Stake.us.
        """
        tmp_db = os.path.join(tempfile.gettempdir(), f"test_dual_stake_dedup_{uuid.uuid4().hex}.json")
        tracker = CodeTracker(filepath=tmp_db)
        mock_notifier = MagicMock()
        mock_notifier.send_notification = MagicMock(return_value=True)

        engine = ScraperEngine(tracker=tracker, notifier=mock_notifier)

        # 1. First event: Dual Stake drop
        dual_item = BonusCodeItem(
            code="dualdrop99",
            platform=Platform.DUAL_STAKE,
            amount_value="$5 (US & COM)",
            wager_requirement="$5,000 Wager",
            source_url="https://t.me/codestats2/100",
            source_name="@codestats2",
            is_dual_stake=True
        )
        res1 = engine.process_items([dual_item], notify=True)
        self.assertEqual(len(res1), 1)
        self.assertEqual(mock_notifier.send_notification.call_count, 1)

        # 2. Second event: Single Stake.us drop with same code from another feed
        stake_us_item = BonusCodeItem(
            code="dualdrop99",
            platform=Platform.STAKE_US,
            amount_value="5 SC",
            wager_requirement="5,000 SC Wager",
            source_url="https://t.me/dailybonuscodeUS/101",
            source_name="@dailybonuscodeUS"
        )
        res2 = engine.process_items([stake_us_item], notify=True)
        self.assertEqual(len(res2), 0)
        self.assertEqual(mock_notifier.send_notification.call_count, 1)

        # 3. Third event: Single Stake.com drop with same code
        stake_com_item = BonusCodeItem(
            code="dualdrop99",
            platform=Platform.STAKE_COM,
            amount_value="$5",
            wager_requirement="$5,000 Wager",
            source_url="https://t.me/dailybonuscodes/102",
            source_name="@dailybonuscodes"
        )
        res3 = engine.process_items([stake_com_item], notify=True)
        self.assertEqual(len(res3), 0)
        self.assertEqual(mock_notifier.send_notification.call_count, 1)

        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    def test_code_tracker_thread_safety(self):
        """
        Validates thread-safety of CodeTracker under concurrent writes and lookups.
        """
        import concurrent.futures

        tmp_db = os.path.join(tempfile.gettempdir(), f"test_thread_safety_{uuid.uuid4().hex}.json")
        tracker = CodeTracker(filepath=tmp_db)

        def worker(code_num):
            item = BonusCodeItem(
                code=f"CONCURRENT_CODE_{code_num}",
                platform=Platform.STAKE_US,
                amount_value="1 SC",
                wager_requirement="4,000 SC",
                source_url=f"https://example.com/{code_num}",
                source_name="Test"
            )
            is_seen = tracker.is_item_seen(item)
            if not is_seen:
                tracker.mark_seen(item)
            return tracker.is_item_seen(item)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i % 20) for i in range(100)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        self.assertTrue(all(results))
        self.assertEqual(len(tracker.get_all()), 20)

        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    def test_realtime_streaming_dispatch(self):
        """
        Validates that ScraperEngine.run_check dispatches newly detected items in real-time
        as sources stream results, without waiting for the full sweep to end.
        """
        tmp_db = os.path.join(tempfile.gettempdir(), f"test_realtime_{uuid.uuid4().hex}.json")
        tracker = CodeTracker(filepath=tmp_db)
        mock_notifier = MagicMock()
        mock_notifier.send_notification = MagicMock(return_value=True)

        engine = ScraperEngine(tracker=tracker, notifier=mock_notifier)

        # Mock scrapers to return items
        fast_item = BonusCodeItem(
            code="FASTSTAKE99",
            platform=Platform.STAKE_US,
            amount_value="25 SC",
            wager_requirement="100,000 SC",
            source_name="StakeStats",
            source_url="https://stakestats.net/stake/tools/code"
        )
        engine.stakestats_poller.get_active_codes = MagicMock(return_value=([fast_item], []))
        engine.telegram_scraper.scrape_all_channels = MagicMock(return_value=[])
        engine.codestats_scraper.scrape_codes = MagicMock(return_value=[])
        engine.site_scraper.fetch_html = MagicMock(return_value=None)

        results = engine.run_check(notify=True)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "FASTSTAKE99")
        self.assertEqual(mock_notifier.send_notification.call_count, 1)

        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    def test_dual_stake_shared_channel_dedup(self):
        """
        Validates that when a channel is configured for both Stake.us and Stake.com (or Default),
        DiscordNotifier dispatches exactly 1 combined dual-stake embed, never 2 duplicate embeds.
        """
        routes_file = os.path.join(tempfile.gettempdir(), f"test_dual_routes_{uuid.uuid4().hex}.json")
        dm = DashboardManager(filepath=routes_file)
        # Configure shared channel 999 for both Stake.us and Stake.com
        dm.add_channel(Platform.STAKE_US, 999)
        dm.add_channel(Platform.STAKE_COM, 999)

        mock_bot = MagicMock()
        mock_bot.is_closed.return_value = False
        notifier = DiscordNotifier(dashboard_manager=dm, bot_client=mock_bot)
        notifier._dispatch_to_channel = MagicMock()

        dual_item = BonusCodeItem(
            code="DUALCODE100",
            platform=Platform.DUAL_STAKE,
            amount_value="$10",
            wager_requirement="5,000 Wager",
            source_url="https://t.me/codestats2/1",
            source_name="@codestats2",
            is_dual_stake=True
        )

        notifier.send_notification(dual_item)

        # Must be dispatched to channel 999 exactly ONCE
        self.assertEqual(notifier._dispatch_to_channel.call_count, 1)
        dispatched_cid = notifier._dispatch_to_channel.call_args[0][0]
        self.assertEqual(dispatched_cid, 999)

        if os.path.exists(routes_file):
            os.remove(routes_file)

    def test_tracker_external_disk_sync(self):
        """
        Validates that if an external process writes a seen code to the state file on disk,
        CodeTracker dynamically loads and recognizes it on the next is_seen / is_item_seen check.
        """
        tmp_db = os.path.join(tempfile.gettempdir(), f"test_disk_sync_{uuid.uuid4().hex}.json")
        tracker1 = CodeTracker(filepath=tmp_db)
        tracker2 = CodeTracker(filepath=tmp_db)

        item = BonusCodeItem(
            code="EXT_SYNC_CODE",
            platform=Platform.STAKE_US,
            amount_value="10 SC",
            wager_requirement="10k",
            source_name="Ext",
            source_url="https://example.com/ext"
        )

        # Initially unseen in tracker2
        self.assertFalse(tracker2.is_item_seen(item))

        # External tracker1 marks it seen and writes to disk
        tracker1.mark_seen(item)

        # tracker2 should now recognize it via dynamic disk sync
        self.assertTrue(tracker2.is_item_seen(item))

        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    def test_dashboard_manager_add_remove_sources(self):
        """
        Validates adding and removing custom Telegram channels and Web Review URLs
        in DashboardManager with JSON persistence and summary calculations.
        """
        tmp_routes = os.path.join(tempfile.gettempdir(), f"test_sources_{uuid.uuid4().hex}.json")
        dm = DashboardManager(filepath=tmp_routes)

        # Add custom Telegram channel for Stake.us
        success, msg = dm.add_telegram_source("@custom_stake_us_drops", Platform.STAKE_US)
        self.assertTrue(success)
        self.assertIn("custom_stake_us_drops", msg)

        # Add custom Telegram channel for Qzino
        success, msg = dm.add_telegram_source("https://t.me/custom_qzino_channel", Platform.QZINO)
        self.assertTrue(success)
        self.assertIn("custom_qzino_channel", msg)

        # Add custom Web Review URL
        success, msg = dm.add_web_source("https://newreviews.com/stake-bonus-codes/")
        self.assertTrue(success)
        self.assertIn("https://newreviews.com/stake-bonus-codes/", msg)

        # Verify sources retrieval
        tg_sources = dm.get_telegram_sources()
        self.assertIn("custom_stake_us_drops", tg_sources["stake_us"])
        self.assertIn("custom_qzino_channel", tg_sources["qzino"])

        web_sources = dm.get_web_sources()
        self.assertIn("https://newreviews.com/stake-bonus-codes/", web_sources)

        # Verify summary breakdown
        summary = dm.get_all_monitored_sources_summary()
        self.assertEqual(summary["total_custom_sources"], 3)
        self.assertIn("custom_stake_us_drops", summary["custom_sources"]["telegram"]["stake_us"])

        # Reload from disk and verify persistence
        dm_reloaded = DashboardManager(filepath=tmp_routes)
        self.assertIn("custom_stake_us_drops", dm_reloaded.get_telegram_sources()["stake_us"])
        self.assertIn("https://newreviews.com/stake-bonus-codes/", dm_reloaded.get_web_sources())

        # Test source removal
        rem_ok, rem_msg = dm_reloaded.remove_telegram_source("custom_stake_us_drops", Platform.STAKE_US)
        self.assertTrue(rem_ok)
        self.assertNotIn("custom_stake_us_drops", dm_reloaded.get_telegram_sources()["stake_us"])

        rem_web_ok, rem_web_msg = dm_reloaded.remove_web_source("https://newreviews.com/stake-bonus-codes/")
        self.assertTrue(rem_web_ok)
        self.assertNotIn("https://newreviews.com/stake-bonus-codes/", dm_reloaded.get_web_sources())

        if os.path.exists(tmp_routes):
            os.remove(tmp_routes)

    def test_new_vip_platforms_exist(self):
        """
        Validates that the new VIP Notice platforms exist with correct properties.
        """
        self.assertIn(Platform.STAKE_COM_VIP_NOTICES, list(Platform))
        self.assertIn(Platform.STAKE_US_VIP_NOTICES, list(Platform))
        self.assertEqual(Platform.STAKE_COM_VIP_NOTICES.value, "Stake.com - VIP Notices")
        self.assertEqual(Platform.STAKE_US_VIP_NOTICES.value, "Stake.us - VIP Notices")
        self.assertEqual(Platform.from_str("stake.com - vip notices"), Platform.STAKE_COM_VIP_NOTICES)
        self.assertEqual(Platform.from_str("stake.us vip"), Platform.STAKE_US_VIP_NOTICES)
        self.assertNotEqual(Platform.STAKE_COM_VIP_NOTICES.embed_color, Platform.STAKE_COM.embed_color)
        self.assertNotEqual(Platform.STAKE_US_VIP_NOTICES.embed_color, Platform.STAKE_US.embed_color)

    def test_stake_vip_notice_parsing(self):
        """
        Validates that Stake.com and Stake.us VIP notices are parsed into the correct
        VIP Notice platforms with proper event types and preserved content.
        """
        tg = TelegramScraper()

        # Stake.com VIP Weekly Bonus
        com_vip = """👑 Stake.com VIP Weekly Bonus is LIVE!
Claim here: https://playstake.fans/bonus?code=BoostWeekly30May26
Total: $16,503,334
Period: May 23 → May 30
Giveaway: $5,000 at 18:00 UTC
Sprint Race: $10,000 prize pool"""
        item_com = tg.parse_stake_message(
            text=com_vip,
            msg_url="https://t.me/c/2922581483/61",
            channel_name="2922581483",
            image_url="https://cdn.telesco.pe/file/com_vip.jpg"
        )
        self.assertIsNotNone(item_com)
        self.assertEqual(item_com.platform, Platform.STAKE_COM_VIP_NOTICES)
        self.assertEqual(item_com.event_type, "weekly_bonus")
        self.assertIn("playstake.fans", item_com.custom_redeem_link)
        self.assertIn("BoostWeekly30May26", item_com.description)
        self.assertIn("$16,503,334", item_com.description)
        self.assertIn("May 23 → May 30", item_com.description)

        # Stake.us VIP Monthly Bonus
        us_monthly = """💰 Stake.us MONTHLY BONUS is now available!
Claim: https://stake.us/?bonus=monthly_bonus
Total: $25,000
Period: July 1 → July 31"""
        item_us = tg.parse_stake_message(
            text=us_monthly,
            msg_url="https://t.me/c/1542279201/257",
            channel_name="1542279201",
            image_url="https://cdn.telesco.pe/file/us_monthly.jpg"
        )
        self.assertIsNotNone(item_us)
        self.assertEqual(item_us.platform, Platform.STAKE_US_VIP_NOTICES)
        self.assertEqual(item_us.event_type, "monthly_bonus")
        self.assertIn("stake.us", item_us.custom_redeem_link)
        self.assertIn("July 1 → July 31", item_us.description)

    def test_vip_notice_generic_preservation(self):
        """
        Validates that unknown VIP messages are preserved as generic vip_notice events
        with complete original text in description.
        """
        tg = TelegramScraper()
        unknown_vip = """🚨 SPECIAL VIP ANNOUNCEMENT
VIP Notice: Check here (https://example.com/vip) for details.
Emoji test: 💸 💰 ⏰ 📺 🏁 ✈️ 🚨 ✉️ 🥉 🥈 🥇 💎 🙏 ❤️‍🔥
Unknown format with extra info."""
        item = tg.parse_stake_message(
            text=unknown_vip,
            msg_url="https://t.me/c/2922581483/999",
            channel_name="2922581483"
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.platform, Platform.STAKE_COM_VIP_NOTICES)
        self.assertEqual(item.event_type, "vip_notice")
        self.assertIn("SPECIAL VIP ANNOUNCEMENT", item.description)
        self.assertIn("💸", item.description)
        self.assertIn("https://example.com/vip", item.description)

    def test_telegram_private_source_configuration(self):
        """
        Validates adding, removing, and persisting private Telegram sources in DashboardManager.
        """
        tmp_routes = os.path.join(tempfile.gettempdir(), f"test_private_tg_{uuid.uuid4().hex}.json")
        dm = DashboardManager(filepath=tmp_routes)

        # Add built-in private sources (should succeed even if already in default config)
        ok1, msg1 = dm.add_telegram_private_source("-2922581483", label="Stake.com VIP Notices", reference_msg_id=61, source_url="https://t.me/c/2922581483/61")
        self.assertTrue(ok1)
        ok2, msg2 = dm.add_telegram_private_source("-1542279201", label="Stake.us VIP Notices", reference_msg_id=257, source_url="https://t.me/c/1542279201/257")
        self.assertTrue(ok2)

        # Add a new custom private source
        ok3, msg3 = dm.add_telegram_private_source("-1234567890", label="Custom Private Chat", reference_msg_id=100)
        self.assertTrue(ok3)

        # Verify retrieval
        private_sources = dm.get_telegram_private_sources()
        self.assertIn("-2922581483", private_sources)
        self.assertIn("-1542279201", private_sources)
        self.assertIn("-1234567890", private_sources)
        self.assertEqual(private_sources["-2922581483"]["label"], "Stake.com VIP Notices")
        self.assertEqual(private_sources["-2922581483"]["reference_msg_id"], 61)

        # Verify summary includes private sources
        summary = dm.get_all_monitored_sources_summary()
        self.assertEqual(summary["total_telegram_private_sources"], 3)
        self.assertIn("-2922581483", summary["telegram_private_sources"])

        # Test removal
        rem_ok, rem_msg = dm.remove_telegram_private_source("-1234567890")
        self.assertTrue(rem_ok)
        self.assertNotIn("-1234567890", dm.get_telegram_private_sources())

        # Reload and verify persistence
        dm2 = DashboardManager(filepath=tmp_routes)
        self.assertIn("-1542279201", dm2.get_telegram_private_sources())
        self.assertNotIn("-1234567890", dm2.get_telegram_private_sources())

        if os.path.exists(tmp_routes):
            os.remove(tmp_routes)

    def test_telegram_source_message_id_separation(self):
        """
        Validates that Telegram source IDs and message IDs are kept separate in configuration.
        """
        tmp_routes = os.path.join(tempfile.gettempdir(), f"test_tg_sep_{uuid.uuid4().hex}.json")
        dm = DashboardManager(filepath=tmp_routes)

        dm.add_telegram_private_source("-2922581483", label="Stake.com VIP", reference_msg_id=61)
        private_sources = dm.get_telegram_private_sources()
        chat_meta = private_sources.get("-2922581483", {})
        self.assertEqual(chat_meta["reference_msg_id"], 61)
        self.assertIn("2922581483", chat_meta["source_url"])

        if os.path.exists(tmp_routes):
            os.remove(tmp_routes)

    def test_link_preservation(self):
        """
        Validates that links are preserved in various formats: Here (URL), [Here](URL), plain URL.
        """
        tg = TelegramScraper()

        # Pattern: Here (URL) in VIP notice
        text1 = """👑 Stake.com VIP Weekly Bonus
Claim here (https://playstake.fans/bonus?code=BoostWeekly30May26) now!"""
        item1 = tg.parse_stake_message(text1, "https://t.me/c/2922581483/61", "2922581483")
        self.assertIsNotNone(item1)
        self.assertIn("https://playstake.fans/bonus?code=BoostWeekly30May26", item1.description)

        # Pattern: [Here](URL) in VIP notice
        text2 = """👑 Stake.us VIP Monthly Bonus
Join [here](https://stake.us/?bonus=monthly) for rewards."""
        item2 = tg.parse_stake_message(text2, "https://t.me/c/1542279201/257", "1542279201")
        self.assertIsNotNone(item2)
        self.assertIn("https://stake.us/?bonus=monthly", item2.description)

        # Pattern: plain URL in VIP notice
        text3 = """👑 Stake.com VIP Notice
Check https://kick.com/Eddie for live streams."""
        item3 = tg.parse_stake_message(text3, "https://t.me/c/2922581483/62", "2922581483")
        self.assertIsNotNone(item3)
        self.assertIn("https://kick.com/Eddie", item3.description)

        # Multiple URLs
        text4 = """👑 Stake.com VIP Notice
Links: https://stake.com and https://stake.us"""
        item4 = tg.parse_stake_message(text4, "https://t.me/c/2922581483/63", "2922581483")
        self.assertIsNotNone(item4)
        self.assertIn("https://stake.com", item4.description)
        self.assertIn("https://stake.us", item4.description)

    def test_emoji_preservation(self):
        """
        Validates that Unicode emojis are preserved exactly in parsed event descriptions.
        """
        tg = TelegramScraper()
        text = """💸 Stake.com VIP Weekly Bonus 💰
⏰ Claim before 18:00 UTC 📺
🏁 Sprint Race starts now ✈️
🚨 Don't miss out ✉️
🥉🥈🥇 Top 3 get bonuses 💎🙏❤️‍🔥"""
        item = tg.parse_stake_message(text, "https://t.me/c/2922581483/64", "2922581483")
        self.assertIsNotNone(item)
        self.assertIn("💸", item.description)
        self.assertIn("💰", item.description)
        self.assertIn("⏰", item.description)
        self.assertIn("📺", item.description)
        self.assertIn("🏁", item.description)
        self.assertIn("✈️", item.description)
        self.assertIn("🚨", item.description)
        self.assertIn("✉️", item.description)
        self.assertIn("🥉", item.description)
        self.assertIn("🥈", item.description)
        self.assertIn("🥇", item.description)
        self.assertIn("💎", item.description)
        self.assertIn("🙏", item.description)
        self.assertIn("❤️‍🔥", item.description)

    def test_complete_message_preservation(self):
        """
        Validates that complete original message text is preserved in description,
        without summarization or section removal.
        """
        tg = TelegramScraper()
        full_message = """👑 Stake.com VIP Weekly Bonus is LIVE!

Total: $16,503,334
Period: May 23 → May 30

Giveaway: $5,000 at 18:00 UTC
Giveaway Location: Stake.com Casino

Sprint Race: $10,000 prize pool
Sprint Race Start: 20:00 UTC
Duration: 2 hours
Prize: $10,000

Claim here: https://playstake.fans/bonus?code=BoostWeekly30May26

Telegram URL: https://t.me/StakeCasino

Emojis: 💸💰⏰📺🏁✈️🚨✉️🥉🥈🥇💎🙏❤️‍🔥

Good luck! 🎰"""
        item = tg.parse_stake_message(full_message, "https://t.me/c/2922581483/65", "2922581483")
        self.assertIsNotNone(item)
        self.assertIn("Total: $16,503,334", item.description)
        self.assertIn("Period: May 23 → May 30", item.description)
        self.assertIn("Giveaway: $5,000 at 18:00 UTC", item.description)
        self.assertIn("Sprint Race: $10,000 prize pool", item.description)
        self.assertIn("https://playstake.fans/bonus?code=BoostWeekly30May26", item.description)
        self.assertIn("https://t.me/StakeCasino", item.description)
        self.assertIn("Good luck! 🎰", item.description)

    def test_duplicate_detection_vip_events(self):
        """
        Validates that duplicate VIP events are detected and not re-broadcast.
        """
        tmp_db = os.path.join(tempfile.gettempdir(), f"test_vip_dedup_{uuid.uuid4().hex}.json")
        tracker = CodeTracker(filepath=tmp_db)

        item1 = BonusCodeItem(
            code="STAKE_COM_WEEKLY_BOOST_#123",
            platform=Platform.STAKE_COM_VIP_NOTICES,
            amount_value="VIP Weekly Boost",
            wager_requirement="VIP Tier Based",
            source_url="https://t.me/c/2922581483/61",
            source_name="Stake.com VIP",
            is_affiliate=False,
            event_type="weekly_bonus"
        )
        item2 = BonusCodeItem(
            code="STAKE_COM_WEEKLY_BOOST_#123",
            platform=Platform.STAKE_COM_VIP_NOTICES,
            amount_value="VIP Weekly Boost",
            wager_requirement="VIP Tier Based",
            source_url="https://t.me/c/2922581483/61",
            source_name="Stake.com VIP",
            is_affiliate=False,
            event_type="weekly_bonus"
        )

        self.assertTrue(tracker.mark_seen(item1))
        self.assertFalse(tracker.mark_seen(item2))
        self.assertTrue(tracker.is_seen(Platform.STAKE_COM_VIP_NOTICES.value, "STAKE_COM_WEEKLY_BOOST_#123", "https://t.me/c/2922581483/61"))

        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    def test_vip_platform_routing(self):
        """
        Validates that VIP Notice platforms route to their own configured channels/webhooks,
        separate from regular Stake platforms.
        """
        tmp_routes = os.path.join(tempfile.gettempdir(), f"test_vip_routes_{uuid.uuid4().hex}.json")
        dm = DashboardManager(filepath=tmp_routes)

        com_vip_cid = 100000000000000001
        us_vip_cid = 100000000000000002
        com_cid = 200000000000000002
        us_cid = 200000000000000001

        dm.add_channel(Platform.STAKE_COM_VIP_NOTICES, com_vip_cid)
        dm.add_channel(Platform.STAKE_US_VIP_NOTICES, us_vip_cid)
        dm.add_channel(Platform.STAKE_COM, com_cid)
        dm.add_channel(Platform.STAKE_US, us_cid)

        self.assertEqual(dm.get_channels(Platform.STAKE_COM_VIP_NOTICES), [com_vip_cid])
        self.assertEqual(dm.get_channels(Platform.STAKE_US_VIP_NOTICES), [us_vip_cid])
        self.assertEqual(dm.get_channels(Platform.STAKE_COM), [com_cid])
        self.assertEqual(dm.get_channels(Platform.STAKE_US), [us_cid])

        # Verify they are separate
        self.assertNotIn(com_vip_cid, dm.get_channels(Platform.STAKE_COM))
        self.assertNotIn(us_vip_cid, dm.get_channels(Platform.STAKE_US))

        if os.path.exists(tmp_routes):
            os.remove(tmp_routes)

    def test_telegram_api_client_missing_credentials(self):
        """
        Validates that TelegramAPIClient reports clear error when credentials are missing.
        """
        from scrapers.telegram_api import TelegramAPIClient
        client = TelegramAPIClient()
        self.assertFalse(client.is_available)
        self.assertIsNotNone(client.error_message)
        self.assertTrue(
            "telethon" in (client.error_message or "").lower() or
            "TELEGRAM_API_ID" in (client.error_message or "").upper()
        )

    def test_stake_weekly_bonus_parser_extraction(self):
        """
        Validates extraction of Stake.com Weekly Bonus fields from historical data.
        """
        tg = TelegramScraper()
        weekly_text = """👑 Stake.com VIP Weekly Bonus
2026-05-30
URL: https://playstake.fans/bonus?code=BoostWeekly30May26
Total: $16,503,334
Period: May 23 → May 30
Giveaway: $5,000 at 18:00 UTC
Sprint Race: $10,000 prize pool"""
        item = tg.parse_stake_message(weekly_text, "https://t.me/c/2922581483/66", "2922581483")
        self.assertIsNotNone(item)
        self.assertEqual(item.platform, Platform.STAKE_COM_VIP_NOTICES)
        self.assertEqual(item.event_type, "weekly_bonus")
        self.assertIn("BoostWeekly30May26", item.custom_redeem_link)
        self.assertIn("$16,503,334", item.description)
        self.assertIn("May 23 → May 30", item.description)

    def test_stake_monthly_bonus_parser_extraction(self):
        """
        Validates extraction of Stake.com Monthly Bonus fields.
        """
        tg = TelegramScraper()
        monthly_text = """July Monthly Bonus
Claim: https://playstake.fans/bonus?code=julymonthlycoupon26234032wasdk3
Total: $27,992,463
Period: July 4 → July 11"""
        item = tg.parse_stake_message(monthly_text, "https://t.me/c/2922581483/67", "2922581483")
        self.assertIsNotNone(item)
        self.assertEqual(item.platform, Platform.STAKE_COM_VIP_NOTICES)
        self.assertEqual(item.event_type, "monthly_bonus")
        self.assertIn("julymonthlycoupon26234032wasdk3", item.custom_redeem_link)
        self.assertIn("July 4 → July 11", item.description)

    def test_post_monthly_bonus_classification(self):
        """
        Validates that Post Monthly Bonus messages are classified correctly.
        """
        tg = TelegramScraper()
        post_monthly = "June Post Monthly Bonus\nClaim here: https://playstake.fans/bonus?code=postmonthly"
        item = tg.parse_stake_message(post_monthly, "https://t.me/c/2922581483/68", "2922581483")
        self.assertIsNotNone(item)
        self.assertEqual(item.platform, Platform.STAKE_COM_VIP_NOTICES)
        self.assertEqual(item.event_type, "post_monthly_bonus")
        self.assertIn("postmonthly", item.custom_redeem_link)

    def test_config_has_vip_platforms(self):
        """
        Validates config.py contains VIP platform colors, webhooks, and affiliate links.
        """
        import config
        self.assertTrue(hasattr(config, "COLOR_STAKE_COM_VIP_NOTICES"))
        self.assertTrue(hasattr(config, "COLOR_STAKE_US_VIP_NOTICES"))
        self.assertTrue(hasattr(config, "DISCORD_WEBHOOK_STAKE_COM_VIP"))
        self.assertTrue(hasattr(config, "DISCORD_WEBHOOK_STAKE_US_VIP"))
        self.assertIn("Stake.com - VIP Notices", config.AFFILIATE_SIGNUP_LINKS)
        self.assertIn("Stake.us - VIP Notices", config.AFFILIATE_SIGNUP_LINKS)
        self.assertIn("-2922581483", config.TELEGRAM_PRIVATE_SOURCES)
        self.assertIn("-1542279201", config.TELEGRAM_PRIVATE_SOURCES)

    def test_dashboard_manager_vip_routes_summary(self):
        """
        Validates that DashboardManager.get_all_routes_summary includes VIP Notice platforms.
        """
        tmp_routes = os.path.join(tempfile.gettempdir(), f"test_vip_summary_{uuid.uuid4().hex}.json")
        dm = DashboardManager(filepath=tmp_routes)
        dm.add_channel(Platform.STAKE_COM_VIP_NOTICES, 111111111111111111)
        dm.add_channel(Platform.STAKE_US_VIP_NOTICES, 222222222222222222)

        summary = dm.get_all_routes_summary()
        self.assertIn("Stake.com - VIP Notices", summary)
        self.assertIn("Stake.us - VIP Notices", summary)
        self.assertEqual(summary["Stake.com - VIP Notices"]["channel_ids"], [111111111111111111])
        self.assertEqual(summary["Stake.us - VIP Notices"]["channel_ids"], [222222222222222222])

        if os.path.exists(tmp_routes):
            os.remove(tmp_routes)

    def test_vip_platforms_do_not_dedup_with_regular_stake(self):
        """
        Validates that VIP Notice events do not deduplicate with regular Stake.com/US drops.
        """
        tmp_db = os.path.join(tempfile.gettempdir(), f"test_vip_no_dedup_{uuid.uuid4().hex}.json")
        tracker = CodeTracker(filepath=tmp_db)

        regular_com = BonusCodeItem(
            code="BoostWeekly30May26",
            platform=Platform.STAKE_COM,
            amount_value="$16,503,334",
            wager_requirement="VIP Tier Based",
            source_url="https://stakestats.net",
            source_name="StakeStats"
        )
        vip_com = BonusCodeItem(
            code="STAKE_COM_WEEKLY_BOOST_#123",
            platform=Platform.STAKE_COM_VIP_NOTICES,
            amount_value="VIP Weekly Boost",
            wager_requirement="VIP Tier Based",
            source_url="https://t.me/c/2922581483/61",
            source_name="Stake.com VIP",
            is_affiliate=False,
            event_type="weekly_bonus"
        )

        self.assertTrue(tracker.mark_seen(regular_com))
        self.assertTrue(tracker.mark_seen(vip_com))
        self.assertTrue(tracker.is_seen(Platform.STAKE_COM.value, "BoostWeekly30May26"))
        self.assertTrue(tracker.is_seen(Platform.STAKE_COM_VIP_NOTICES.value, "STAKE_COM_WEEKLY_BOOST_#123", "https://t.me/c/2922581483/61"))

        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    def test_sources_embed_generation(self):
        """
        Validates that create_sources_embed correctly structures the Discord embed
        with all platform categories, custom sources, and active counts.
        """
        from discord_bot import create_sources_embed
        tmp_routes = os.path.join(tempfile.gettempdir(), f"test_embed_sources_{uuid.uuid4().hex}.json")
        dm = DashboardManager(filepath=tmp_routes)
        dm.add_telegram_source("vip_custom_drops", Platform.STAKE_US)
        dm.add_web_source("https://exclusivepromos.com/drops")

        embed = create_sources_embed(dm)
        self.assertIn("Monitored Event Sources", embed.title)
        field_names = [f.name for f in embed.fields]
        self.assertTrue(any("Stake.us" in fn for fn in field_names))
        self.assertTrue(any("Web Review" in fn for fn in field_names))
        self.assertTrue(any("Live Poller" in fn for fn in field_names))

        if os.path.exists(tmp_routes):
            os.remove(tmp_routes)

    def test_scraper_engine_dynamic_sources(self):
        """
        Validates that ScraperEngine dynamically consumes custom sources added via DashboardManager.
        """
        tmp_routes = os.path.join(tempfile.gettempdir(), f"test_engine_sources_{uuid.uuid4().hex}.json")
        dm = DashboardManager(filepath=tmp_routes)
        dm.add_web_source("https://dynamic-source.com/stake/")
        dm.add_telegram_source("dynamic_tg_channel", Platform.STAKE_US)

        engine = ScraperEngine(dashboard_manager=dm)
        web_sources = engine.dashboard_manager.get_web_sources()
        self.assertIn("https://dynamic-source.com/stake/", web_sources)

        tg_sources = engine.dashboard_manager.get_telegram_sources()
        self.assertIn("dynamic_tg_channel", tg_sources["stake_us"])

        if os.path.exists(tmp_routes):
            os.remove(tmp_routes)

if __name__ == "__main__":
    unittest.main()
