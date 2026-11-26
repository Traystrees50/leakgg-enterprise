import json
import logging
import asyncio
import concurrent.futures
import os
from datetime import datetime, timezone
import requests
from typing import Optional, Dict, Any, List
from models import BonusCodeItem, Platform
from config import BOT_NAME, KICK_STREAM_LINKS, DEFAULT_KICK_LINK, KICK_STREAM_LABELS, DEFAULT_KICK_LABEL, PLATFORM_SOURCE_OVERRIDES, DISCORD_INVITE_URL
from dashboard_manager import DashboardManager

logger = logging.getLogger(__name__)

# Backup tracking file
BACKUP_FILE = "posts_backup.json"

# Official platform logo thumbnails for Discord embeds
# Using publicly hosted CDN images for each platform
PLATFORM_LOGOS: Dict[str, str] = {
    "Stake.com":               "https://stake.com/favicon.ico",
    "Stake.us":                "https://stake.us/favicon.ico",
    "Stake.com - VIP Notices": "https://stake.com/favicon.ico",
    "Stake.us - VIP Notices":  "https://stake.us/favicon.ico",
    "Shuffle.com":             "https://shuffle.com/favicon.ico",
    "Shuffle.us":              "https://shuffle.us/favicon.ico",
    "Stake.us & Stake.com":    "https://stake.com/favicon.ico",
    "Rainbet":                 "https://rainbet.com/favicon.ico",
    "Rainbet.us":              "https://rainbet.com/favicon.ico",
    "Qzino":                   "https://qzino.ai/favicon.ico",
    "Degen":                   "https://degen.com/favicon.ico",
    "Goated":                  "https://goated.com/favicon.ico",
    "THRILL":                  "https://thrill.com/favicon.ico",
    "WINNA":                   "https://winna.com/favicon.ico",
    "GAMBA":                   "https://gamba.com/favicon.ico",
    "Razed":                   "https://razed.com/favicon.ico",
}


def save_backup(action: str, platform: str, code: str, details: str = "") -> bool:
    """
    Saves a timestamped backup record of posts and code checks to a local JSON file.
    Uses ISO 8601 timestamps for tracking.
    Returns True on success, False on failure.
    """
    try:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "platform": platform,
            "code": code,
            "details": details,
        }
        existing = []
        if os.path.exists(BACKUP_FILE):
            try:
                with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = []
        existing.append(record)
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        logger.debug(f"Backup saved: {action} {platform} {code}")
        return True
    except Exception as e:
        logger.error(f"Failed to save backup: {e}")
        return False


def get_kick_url_for_platform(platform_value: str) -> str:
    """
    Conditional Kick link logic:
    - Rainbet -> https://www.kick.com/moonbootmurphy
    - All other platforms -> https://www.kick.com/traystrees50
    """
    if platform_value == "Rainbet":
        return "https://www.kick.com/moonbootmurphy"
    return DEFAULT_KICK_LINK


def get_kick_label_for_platform(platform_value: str) -> str:
    """Returns the Kick stream label for the platform, with Rainbet override."""
    if platform_value == "Rainbet":
        return KICK_STREAM_LABELS.get("Rainbet", DEFAULT_KICK_LABEL)
    return DEFAULT_KICK_LABEL


class DiscordNotifier:
    def __init__(self, webhook_url: Optional[str] = None, dashboard_manager: Optional[DashboardManager] = None, bot_client: Optional[Any] = None):
        self.dashboard_manager = dashboard_manager or DashboardManager()
        self.default_webhook_url = webhook_url
        self.bot_client = bot_client

    def get_webhook_url_for_platform(self, platform: Platform) -> Optional[str]:
        if self.default_webhook_url:
            return self.default_webhook_url
        return self.dashboard_manager.get_webhook(platform)

    def get_channel_id_for_platform(self, platform: Platform) -> Optional[int]:
        return self.dashboard_manager.get_channel(platform)

    def get_webhooks_for_platform(self, platform: Platform) -> List[str]:
        if self.default_webhook_url:
            return [self.default_webhook_url]
        return self.dashboard_manager.get_webhooks(platform)

    def get_channels_for_platform(self, platform: Platform) -> List[int]:
        return self.dashboard_manager.get_channels(platform)

    def build_embed(self, item: BonusCodeItem) -> Dict[str, Any]:
        """
        Builds a clean LEAKED.GG branded Discord embed.
        Platform field shows platform name + code. Details only shown if meaningful values exist.
        Footer: "We Value Responsible Gaming - Leaked.gg"
        Image attached when present (required for DEGEN/QZINO).
        """
        platform_name = item.platform.value.upper()
        color = item.platform.embed_color

        # Check for user submitted dual stake
        is_user_submitted_dual = (
            item.is_dual_stake or item.platform == Platform.DUAL_STAKE
        ) and item.amount_value and "User Submitted" in item.amount_value

        # Only include meaningful details (skip defaults/placeholders)
        detail_lines = []

        # Always show the code prominently (easy to copy)
        detail_lines.append(f"**Code:** `{item.clean_code}`")

        # For user submitted dual stake: skip Value line entirely, show special platform title
        # For others: only show value if it's a real value, not a placeholder
        placeholder_values = {"Exclusive Offer", "Amount not specified", "User Submitted (US & COM)", "User Submitted Stake.com Drop", "User Submitted Stake.us Drop"}
        if item.amount_value and item.amount_value not in placeholder_values:
            detail_lines.append(f"**Value:** {item.amount_value}")

        # Only show claims if it's a real limit
        if item.claims_count and item.claims_count not in {"Unlimited", "Unknown"}:
            detail_lines.append(f"**Total Drop Limit:** {item.claims_count}")

        # Only show wager if it's a real requirement
        if item.wager_requirement and item.wager_requirement not in {"Not specified", "None", "N/A"}:
            detail_lines.append(f"**Requirements:** {item.wager_requirement}")

        # Claim link(s) - always show
        _is_ambiguous = getattr(item, "is_ambiguous_stake", False) or item.platform == Platform.AMBIGUOUS_STAKE
        if _is_ambiguous:
            # Ambiguous Stake: both links are CANDIDATES only, neither
            # platform is verified. Never present them as a verified dual.
            claim_line = (
                f"[**CANDIDATE CLAIM (US)**]({item.redeem_link_us})  "
                f"[**CANDIDATE CLAIM (COM)**]({item.redeem_link_com})"
            )
        elif item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
            claim_line = (
                f"[**CLICK HERE TO CLAIM (US)**]({item.redeem_link_us})  "
                f"[**CLICK HERE TO CLAIM (COM)**]({item.redeem_link_com})"
            )
        else:
            claim_line = f"[**CLICK HERE TO CLAIM**]({item.redeem_link})"

        detail_lines.append("")  # blank line before claim link
        detail_lines.append(claim_line)

        # Platform field: special handling for user submitted dual stake
        if _is_ambiguous:
            platform_display = "AMBIGUOUS STAKE (US & COM) - CANDIDATE LINKS ONLY, NOT VERIFIED"
        elif is_user_submitted_dual:
            platform_display = "NEW USER SUBMITTED (US & COM) CODE DETECTED"
        else:
            platform_display = f"{platform_name}  NEW DROP DETECTED"

        fields = [
            {
                "name": "**Platform**",
                "value": platform_display,
                "inline": False,
            },
            {
                "name": "**Details**",
                "value": "\n".join(detail_lines),
                "inline": False,
            }
        ]

        embed: Dict[str, Any] = {
            "color": color,
            "fields": fields,
            "footer": {"text": "We Value Responsible Gaming - Leaked.gg"},
        }

        # Attach event media/image (always shown when present — required for Degen, Qzino, etc.)
        if item.image_url:
            embed["image"] = {"url": item.image_url}

        # Platform logo thumbnail (shown in top-right corner of every embed)
        logo_url = PLATFORM_LOGOS.get(item.platform.value)
        if logo_url:
            embed["thumbnail"] = {"url": logo_url}

        return embed

    # Moonbootmurphy's Rainbet webhook - only this webhook gets KICK button
    MOONBOOTMURPHY_WEBHOOK = "https://discord.com/api/webhooks/1565129798492364850/ccOjrNLeAnMZt1whgm-pO9GWmrk7a3dWIKfETCB76IqpAhnEFZ9p5-y6bFoEPugd4X2u"

    def _link_button_definitions(self, item: BonusCodeItem, target_webhook: Optional[str] = None) -> List[tuple[str, str]]:
        buttons = [
            ("CLAIM", item.redeem_link),
            ("SIGNUP", item.affiliate_signup_link),
            ("DISCORD", DISCORD_INVITE_URL),
        ]
        # Only include KICK button for Rainbet sent to moonbootmurphy's webhook
        if item.platform == Platform.RAINBET and target_webhook and target_webhook == self.MOONBOOTMURPHY_WEBHOOK:
            buttons.append(("KICK", "https://www.kick.com/moonbootmurphy"))
        return buttons

    def _link_button_components(self, item: BonusCodeItem, target_webhook: Optional[str] = None) -> List[Dict[str, Any]]:
        return [{
            "type": 1,
            "components": [
                {"type": 2, "style": 5, "label": label, "url": url}
                for label, url in self._link_button_definitions(item, target_webhook)
            ],
        }]

    def _send_single_item_notification(self, item: BonusCodeItem, target_webhooks: List[str], target_channels: List[int]) -> bool:
        embed_dict = self.build_embed(item)
        role_tag = item.platform.role_tag
        
        success = False
        # 1. Dispatch via Webhook(s)
        for wh in list(dict.fromkeys([w for w in target_webhooks if w])):
            webhook_payload = {
                "embeds": [embed_dict],
                "components": self._link_button_components(item, wh),
            }
            if role_tag and item.platform != Platform.RAINBET:
                webhook_payload["content"] = role_tag
            try:
                # If we have raw image bytes (private Telegram media), send as multipart
                if item.image_bytes and not item.image_url:
                    import io
                    payload_json = json.dumps({
                        "payload_json": json.dumps(webhook_payload)
                    })
                    resp = requests.post(
                        wh,
                        data={"payload_json": json.dumps(webhook_payload)},
                        files={"file": ("media.jpg", io.BytesIO(item.image_bytes), "image/jpeg")},
                        timeout=15
                    )
                else:
                    resp = requests.post(
                        wh,
                        data=json.dumps(webhook_payload),
                        headers={"Content-Type": "application/json"},
                        timeout=10
                    )
                if resp.status_code in [200, 204]:
                    logger.info(f"Successfully dispatched Discord embed for {item.platform.value} code '{item.code}' to webhook: {wh[:35]}...")
                    success = True
                else:
                    logger.error(f"Failed to send Discord webhook. HTTP {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Exception while sending Discord webhook: {e}")

        # 2. If bot client is connected and channels are configured, post to all direct channels
        # For channel posts, no KICK button (only moonbootmurphy's webhook gets it)
        channel_components = self._link_button_components(item, None)
        if self.bot_client is not None:
            try:
                unique_channels = list(dict.fromkeys([int(c) for c in target_channels if c]))
                for cid in unique_channels:
                    self._dispatch_to_channel(cid, embed_dict, item, channel_components)
                    success = True
            except Exception as e:
                logger.warning(f"Direct channel dispatch error: {e}")

        return success

    def _send_subscriber_notification(self, item: BonusCodeItem, subscriber_uid: str) -> bool:
        sub_channels = self.dashboard_manager.get_subscriber_channels(subscriber_uid, item.platform)
        sub_webhooks = self.dashboard_manager.get_subscriber_webhooks(subscriber_uid, item.platform)
        if not sub_channels and not sub_webhooks:
            sub_channels = self.dashboard_manager.get_subscriber_channels(subscriber_uid, "Default")
            sub_webhooks = self.dashboard_manager.get_subscriber_webhooks(subscriber_uid, "Default")
        if not sub_channels and not sub_webhooks:
            # Subscriber has no custom routes configured; they receive posts via admin channels
            return False
        return self._send_single_item_notification(item, sub_webhooks, sub_channels)

    _BLOCKED_PHRASES = ("A_ToolsX", "t.me/A_ToolsX", "must join our channel")

    def send_notification(self, item: BonusCodeItem, custom_webhook: Optional[str] = None, subscriber_uid: Optional[str] = None) -> bool:
        try:
            _blob = str(item.__dict__)
        except Exception:
            _blob = str(item)
        if any(p.lower() in _blob.lower() for p in self._BLOCKED_PHRASES):
            return False
        """
        Sends the bonus code embed to Discord across all configured webhooks
        and direct bot text channels for the platform(s).
        Supports multi-channel and multi-webhook distribution simultaneously.

        For Dual-Platform drops (Stake.us & Stake.com):
        - Dispatches Stake.us-tailored embed with Stake.us redeem link & info to Stake.us channels and webhooks.
        - Dispatches Stake.com-tailored embed with Stake.com redeem link & info to Stake.com channels and webhooks.
        """
        if custom_webhook:
            return self._send_single_item_notification(item, [custom_webhook], [])

        _is_ambiguous = getattr(item, "is_ambiguous_stake", False) or item.platform == Platform.AMBIGUOUS_STAKE
        if subscriber_uid:
            if _is_ambiguous:
                # Ambiguous: send ONCE, do not split into US + COM items.
                return self._send_subscriber_notification(item, subscriber_uid)
            if item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
                sent = False
                sent = self._send_subscriber_notification(item.to_stake_us_item(), subscriber_uid) or sent
                sent = self._send_subscriber_notification(item.to_stake_com_item(), subscriber_uid) or sent
                return sent
            return self._send_subscriber_notification(item, subscriber_uid)

        if not _is_ambiguous and (item.is_dual_stake or item.platform == Platform.DUAL_STAKE):
            # For dual stake items: post to BOTH Stake.us AND Stake.com channels/webhooks
            # Each embed contains BOTH claim links (US and COM)
            us_webhooks = set(self.dashboard_manager.get_webhooks(Platform.STAKE_US))
            us_channels = set(self.dashboard_manager.get_channels(Platform.STAKE_US))

            com_webhooks = set(self.dashboard_manager.get_webhooks(Platform.STAKE_COM))
            com_channels = set(self.dashboard_manager.get_channels(Platform.STAKE_COM))

            success = False

            # Send to all Stake.us destinations
            if us_webhooks or us_channels:
                s_us = self._send_single_item_notification(item, list(us_webhooks), list(us_channels))
                success = success or s_us

            # Send to all Stake.com destinations
            if com_webhooks or com_channels:
                s_com = self._send_single_item_notification(item, list(com_webhooks), list(com_channels))
                success = success or s_com

            # Fallback to Default if neither platform has routes configured
            if not us_webhooks and not us_channels and not com_webhooks and not com_channels:
                def_webhooks = self.dashboard_manager.get_webhooks("Default")
                if self.default_webhook_url and self.default_webhook_url not in def_webhooks:
                    def_webhooks.append(self.default_webhook_url)
                def_channels = self.dashboard_manager.get_channels("Default")
                s_def = self._send_single_item_notification(item, def_webhooks, def_channels)
                success = success or s_def

            save_backup("post", "Dual Stake", item.code, f"value={item.amount_value} wager={item.wager_requirement}")
            for sub_uid in self.dashboard_manager.get_all_subscriber_ids():
                success = self._send_subscriber_notification(item, sub_uid) or success
            return success

        # Standard single platform dispatch
        target_webhooks = self.dashboard_manager.get_webhooks(item.platform)
        if not target_webhooks and self.default_webhook_url:
            target_webhooks.append(self.default_webhook_url)
        target_channels = self.dashboard_manager.get_channels(item.platform)
        if not target_channels and not target_webhooks:
            target_channels = self.dashboard_manager.get_channels("Default")
            target_webhooks = self.dashboard_manager.get_webhooks("Default")
            if self.default_webhook_url and self.default_webhook_url not in target_webhooks:
                target_webhooks.append(self.default_webhook_url)

        success = self._send_single_item_notification(item, target_webhooks, target_channels)

        # Save backup record
        save_backup("post", item.platform.value, item.code, f"value={item.amount_value} wager={item.wager_requirement}")

        # Dispatch to all active subscribers' personal channel/webhook routes (non-owner only)
        for sub_uid in self.dashboard_manager.get_all_subscriber_ids():
            success = self._send_subscriber_notification(item, sub_uid) or success

        return success

    def _dispatch_to_channel(self, channel_id: int, embed_dict: Dict[str, Any], item: BonusCodeItem, components: Optional[List[Dict[str, Any]]] = None):
        """
        Safely dispatches an embed to a Discord text channel using client cache or API fetch.
        Handles both thread-pool execution and event loop coroutine scheduling.
        Includes clickable claim, signup, community, and Kick URL buttons.
        """
        if not self.bot_client or self.bot_client.is_closed():
            return

        import asyncio
        import discord

        async def _async_send():
            try:
                channel = self.bot_client.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await asyncio.wait_for(
                            self.bot_client.fetch_channel(channel_id),
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout fetching Discord channel ID {channel_id}")
                        return
                    except Exception as fe:
                        logger.warning(f"Could not fetch Discord channel ID {channel_id}: {fe}")
                        return
                if channel is not None:
                    role_tag = item.platform.role_tag
                    embed = discord.Embed.from_dict(embed_dict)

                    # These URL-only buttons need no interaction callbacks.
                    view = None
                    try:
                        view = discord.ui.View(timeout=None)
                        if components:
                            for component in components:
                                if component.get("type") == 1:
                                    for btn_comp in component.get("components", []):
                                        if btn_comp.get("type") == 2:
                                            view.add_item(discord.ui.Button(
                                                label=btn_comp.get("label"),
                                                style=discord.ButtonStyle.link,
                                                url=btn_comp.get("url"),
                                            ))
                        else:
                            # Fallback to old method
                            for label, url in self._link_button_definitions(item):
                                view.add_item(discord.ui.Button(
                                    label=label,
                                    style=discord.ButtonStyle.link,
                                    url=url,
                                ))
                    except Exception as ve:
                        logger.warning(f"Failed to build interactive view: {ve}")

                    await asyncio.wait_for(
                        channel.send(content=role_tag or None, embed=embed, view=view),
                        timeout=5.0
                    )
                    logger.info(f"Dispatched {item.platform.value} drop '{item.code}' to direct channel #{getattr(channel, 'name', channel_id)} ({channel_id})")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout sending to channel {channel_id}, skipping")
            except Exception as exc:
                logger.error(f"Failed to deliver message to channel {channel_id}: {exc}")

        try:
            loop = getattr(self.bot_client, "loop", None)
            if loop and loop.is_running():
                try:
                    curr_loop = asyncio.get_running_loop()
                    if curr_loop is loop:
                        loop.create_task(_async_send())
                    else:
                        future = asyncio.run_coroutine_threadsafe(_async_send(), loop)
                        try:
                            future.result(timeout=8.0)
                        except concurrent.futures.TimeoutError:
                            logger.warning(f"Channel dispatch to {channel_id} timed out, task may still complete")
                except RuntimeError:
                    # Called from worker thread with no active asyncio loop in that thread
                    future = asyncio.run_coroutine_threadsafe(_async_send(), loop)
                    try:
                        future.result(timeout=8.0)
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"Channel dispatch to {channel_id} timed out, task may still complete")
                    except Exception:
                        raise
            elif loop:
                loop.create_task(_async_send())
        except Exception as e:
            logger.error(f"Error scheduling channel dispatch for {channel_id}: {e}")

    def send_raw_message(self, platform: Platform, content: str, subscriber_uid: Optional[str] = None) -> bool:
        """
        Sends a raw text message to all configured webhooks and direct channels for the platform.
        """
        if any(p.lower() in (content or "").lower() for p in self._BLOCKED_PHRASES):
            return False
        if subscriber_uid:
            target_webhooks = self.dashboard_manager.get_subscriber_webhooks(subscriber_uid, platform)
            target_channels = self.dashboard_manager.get_subscriber_channels(subscriber_uid, platform)
            if not target_webhooks and not target_channels:
                target_webhooks = self.dashboard_manager.get_subscriber_webhooks(subscriber_uid, "Default")
                target_channels = self.dashboard_manager.get_subscriber_channels(subscriber_uid, "Default")
        else:
            target_webhooks = self.get_webhooks_for_platform(platform)
            target_channels = self.get_channels_for_platform(platform)
        if not subscriber_uid and not target_webhooks and self.default_webhook_url:
            target_webhooks = [self.default_webhook_url]
        if not subscriber_uid and not target_channels and not target_webhooks:
            target_channels = self.get_channels_for_platform("Default")
            target_webhooks = self.get_webhooks_for_platform("Default")
            if self.default_webhook_url and self.default_webhook_url not in target_webhooks:
                target_webhooks.append(self.default_webhook_url)

        if not target_webhooks and not target_channels:
            return False

        success = False
        payload = {"content": content}

        for wh in list(dict.fromkeys([w for w in target_webhooks if w])):
            try:
                resp = requests.post(
                    wh,
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                if resp.status_code in [200, 204]:
                    logger.info(f"Successfully dispatched raw message for {platform.value} to webhook: {wh[:35]}...")
                    success = True
                else:
                    logger.error(f"Failed to send raw message webhook. HTTP {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Exception while sending raw message webhook: {e}")

        if self.bot_client is not None:
            try:
                unique_channels = list(dict.fromkeys([int(c) for c in target_channels if c]))
                for cid in unique_channels:
                    self._dispatch_raw_to_channel(cid, content)
                    success = True
            except Exception as e:
                logger.warning(f"Direct channel raw dispatch error: {e}")

        return success

    def _dispatch_raw_to_channel(self, channel_id: int, content: str):
        """
        Safely dispatches a raw text message to a Discord text channel.
        """
        if not self.bot_client or self.bot_client.is_closed():
            return

        import asyncio
        import discord

        async def _async_send():
            try:
                channel = self.bot_client.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await asyncio.wait_for(
                            self.bot_client.fetch_channel(channel_id),
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout fetching Discord channel ID {channel_id}")
                        return
                    except Exception as fe:
                        logger.warning(f"Could not fetch Discord channel ID {channel_id}: {fe}")
                        return
                if channel is not None:
                    await asyncio.wait_for(
                        channel.send(content=content),
                        timeout=5.0
                    )
                    logger.info(f"✅ Dispatched raw message to direct channel #{getattr(channel, 'name', channel_id)} ({channel_id})")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout sending raw message to channel {channel_id}, skipping")
            except Exception as exc:
                logger.error(f"Failed to deliver raw message to channel {channel_id}: {exc}")

        try:
            loop = getattr(self.bot_client, "loop", None)
            if loop and loop.is_running():
                try:
                    curr_loop = asyncio.get_running_loop()
                    if curr_loop is loop:
                        loop.create_task(_async_send())
                    else:
                        future = asyncio.run_coroutine_threadsafe(_async_send(), loop)
                        try:
                            future.result(timeout=8.0)
                        except concurrent.futures.TimeoutError:
                            logger.warning(f"Raw channel dispatch to {channel_id} timed out, task may still complete")
                except RuntimeError:
                    future = asyncio.run_coroutine_threadsafe(_async_send(), loop)
                    try:
                        future.result(timeout=8.0)
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"Raw channel dispatch to {channel_id} timed out, task may still complete")
                    except Exception:
                        raise
            elif loop:
                loop.create_task(_async_send())
        except Exception as e:
            logger.error(f"Error scheduling raw channel dispatch for {channel_id}: {e}")
