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
        No title. Platform field with details. Bold text for labels.
        Footer: "LEAKED.GG • {detected_at}"
        Image attached when present (required for DEGEN/QZINO).
        """
        platform_name = item.platform.value.upper()
        source_name = item.source_name or "Unknown Source"
        color = item.platform.embed_color

        bullet_lines = (
            f"**Code:** `{item.clean_code}`\n"
            f"**Value:** {item.amount_value or 'Exclusive Offer'}\n"
            f"**Total Drop Limit:** {item.claims_count or 'Unlimited'}\n"
            f"**Requirements:** {item.wager_requirement or 'None'}"
        )

        if item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
            claim_line = (
                f"[**CLICK HERE TO CLAIM (US)**]({item.redeem_link_us})  "
                f"[**CLICK HERE TO CLAIM (COM)**]({item.redeem_link_com})"
            )
        else:
            claim_line = f"[**CLICK HERE TO CLAIM**]({item.redeem_link})"

        fields = [
            {
                "name": "**Platform**",
                "value": f"{platform_name} — {source_name}",
                "inline": False,
            },
            {
                "name": "**Details**",
                "value": f"{bullet_lines}\n\n{claim_line}",
                "inline": False,
            }
        ]

        embed: Dict[str, Any] = {
            "color": color,
            "fields": fields,
            "footer": {"text": f"LEAKED.GG • {item.detected_at}"},
        }

        if item.image_url:
            embed["image"] = {"url": item.image_url}

        return embed

    @staticmethod
    def _link_button_definitions(item: BonusCodeItem) -> List[tuple[str, str]]:
        return [
            ("CLAIM", item.redeem_link),
            ("SIGNUP", item.affiliate_signup_link),
            ("DISCORD", DISCORD_INVITE_URL),
            ("KICK", get_kick_url_for_platform(item.platform.value)),
        ]

    def _link_button_components(self, item: BonusCodeItem) -> List[Dict[str, Any]]:
        return [{
            "type": 1,
            "components": [
                {"type": 2, "style": 5, "label": label, "url": url}
                for label, url in self._link_button_definitions(item)
            ],
        }]

    def _send_single_item_notification(self, item: BonusCodeItem, target_webhooks: List[str], target_channels: List[int]) -> bool:
        embed_dict = self.build_embed(item)
        role_tag = item.platform.role_tag
        # Webhook payload: exclude role tags for Rainbet (clean posts without @ mentions)
        webhook_payload = {
            "embeds": [embed_dict],
            "components": self._link_button_components(item),
        }
        if role_tag and item.platform != Platform.RAINBET:
            webhook_payload["content"] = role_tag

        success = False
        # 1. Dispatch via Webhook(s)
        for wh in list(dict.fromkeys([w for w in target_webhooks if w])):
            try:
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
        if self.bot_client is not None:
            try:
                unique_channels = list(dict.fromkeys([int(c) for c in target_channels if c]))
                for cid in unique_channels:
                    self._dispatch_to_channel(cid, embed_dict, item)
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

        if subscriber_uid:
            if item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
                sent = False
                sent = self._send_subscriber_notification(item.to_stake_us_item(), subscriber_uid) or sent
                sent = self._send_subscriber_notification(item.to_stake_com_item(), subscriber_uid) or sent
                return sent
            return self._send_subscriber_notification(item, subscriber_uid)

        if item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
            us_item = item.to_stake_us_item()
            com_item = item.to_stake_com_item()

            us_webhooks = set(self.dashboard_manager.get_webhooks(Platform.STAKE_US))
            us_channels = set(self.dashboard_manager.get_channels(Platform.STAKE_US))

            com_webhooks = set(self.dashboard_manager.get_webhooks(Platform.STAKE_COM))
            com_channels = set(self.dashboard_manager.get_channels(Platform.STAKE_COM))

            # Destinations configured for BOTH platforms (or fallback to Default if neither configured)
            shared_webhooks = list(us_webhooks.intersection(com_webhooks))
            shared_channels = list(us_channels.intersection(com_channels))

            exclusive_us_webhooks = list(us_webhooks - set(shared_webhooks))
            exclusive_us_channels = list(us_channels - set(shared_channels))

            exclusive_com_webhooks = list(com_webhooks - set(shared_webhooks))
            exclusive_com_channels = list(com_channels - set(shared_channels))

            # Check if neither platform is configured -> fallback to Default routes ONCE (combined card)
            if not us_webhooks and not us_channels and not com_webhooks and not com_channels:
                def_webhooks = self.dashboard_manager.get_webhooks("Default")
                if self.default_webhook_url and self.default_webhook_url not in def_webhooks:
                    def_webhooks.append(self.default_webhook_url)
                def_channels = self.dashboard_manager.get_channels("Default")
                success = self._send_single_item_notification(item, def_webhooks, def_channels)
                save_backup("post", "Dual Stake", item.code, f"value={item.amount_value} wager={item.wager_requirement}")
                for sub_uid in self.dashboard_manager.get_all_subscriber_ids():
                    success = self._send_subscriber_notification(us_item, sub_uid) or success
                    success = self._send_subscriber_notification(com_item, sub_uid) or success
                return success

            success = False
            # 1. Send single combined dual card to shared destinations (never duplicate post to same channel)
            if shared_webhooks or shared_channels:
                s_shared = self._send_single_item_notification(item, shared_webhooks, shared_channels)
                success = success or s_shared

            # 2. Send Stake.us card only to exclusive Stake.us destinations
            if exclusive_us_webhooks or exclusive_us_channels:
                s_us = self._send_single_item_notification(us_item, exclusive_us_webhooks, exclusive_us_channels)
                success = success or s_us

            # 3. Send Stake.com card only to exclusive Stake.com destinations
            if exclusive_com_webhooks or exclusive_com_channels:
                s_com = self._send_single_item_notification(com_item, exclusive_com_webhooks, exclusive_com_channels)
                success = success or s_com

            for sub_uid in self.dashboard_manager.get_all_subscriber_ids():
                success = self._send_subscriber_notification(us_item, sub_uid) or success
                success = self._send_subscriber_notification(com_item, sub_uid) or success
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

    def _dispatch_to_channel(self, channel_id: int, embed_dict: Dict[str, Any], item: BonusCodeItem):
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
                    logger.info(f"✅ Dispatched {item.platform.value} drop '{item.code}' to direct channel #{getattr(channel, 'name', channel_id)} ({channel_id})")
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
