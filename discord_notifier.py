import json
import logging
import asyncio
import concurrent.futures
import os
from datetime import datetime, timezone
import requests
from typing import Optional, Dict, Any, List
from models import BonusCodeItem, Platform
from config import BOT_NAME, KICK_STREAM_LINKS, DEFAULT_KICK_LINK, KICK_STREAM_LABELS, DEFAULT_KICK_LABEL, PLATFORM_SOURCE_OVERRIDES
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

    @staticmethod
    def _record_delivery(item: BonusCodeItem, guild_id: Optional[int], delivered: bool) -> None:
        if guild_id is None:
            return
        try:
            from drop_analytics import get_store
            get_store().record_delivery(item, guild_id, delivered)
        except Exception as exc:
            logger.warning(f"Could not record delivery analytics for guild {guild_id}: {exc}")

    @staticmethod
    def _already_delivered_to_guild(item: BonusCodeItem, guild_id: int) -> bool:
        try:
            from drop_analytics import get_store
            return get_store().has_successful_delivery(item, guild_id)
        except Exception as exc:
            logger.warning(f"Could not check delivery history for guild {guild_id}: {exc}")
            return False

    @staticmethod
    def build_message_components(item: BonusCodeItem) -> List[Dict[str, Any]]:
        return [{
            "type": 1,
            "components": [
                {"type": 2, "style": 5, "label": "CLAIM", "url": item.redeem_link},
                {"type": 2, "style": 5, "label": "SIGNUP", "url": item.affiliate_signup_link},
            ],
        }]

    @staticmethod
    def build_link_view(item: BonusCodeItem):
        import discord

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            label="CLAIM",
            style=discord.ButtonStyle.link,
            url=item.redeem_link,
        ))
        view.add_item(discord.ui.Button(
            label="SIGNUP",
            style=discord.ButtonStyle.link,
            url=item.affiliate_signup_link,
        ))
        return view

    def build_embed(self, item: BonusCodeItem) -> Dict[str, Any]:
        """
        Builds a readable, platform-colored drop embed. Claim and signup actions
        are attached as the only message buttons by the delivery methods.
        """
        emoji = item.platform.emoji
        color = item.platform.embed_color
        title = item.notification_title

        source_display = f"[{item.source_name}]({item.source_url})" if item.source_url else f"`{item.source_name}`"
        if item.platform.value in PLATFORM_SOURCE_OVERRIDES:
            override_name, override_url = PLATFORM_SOURCE_OVERRIDES[item.platform.value]
            source_display = f"[{override_name}]({override_url})"
        fields = [
            {
                "name": "Event",
                "value": f"{emoji} **{item.platform.value}** • 🌐 {source_display}",
                "inline": False
            },
            {
                "name": "🎁 Bonus code",
                "value": f"```{item.clean_code}```",
                "inline": False
            },
            {
                "name": "💰 Value",
                "value": f"**{item.amount_value or 'Exclusive Offer'}**",
                "inline": True
            },
            {
                "name": "🔄 Wager",
                "value": f"**{item.wager_requirement or 'None / 0x'}**",
                "inline": True
            },
            {
                "name": "👥 Claims",
                "value": f"**{item.claims_count or 'Unlimited / Open'}**",
                "inline": True
            }
        ]

        # A combined Stake alert has two redeem destinations; keep both visible
        # while the single Claim button targets the default Stake.us redeem URL.
        if item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
            fields.append({
                "name": "🔗 Claim on either Stake site",
                "value": (
                    f"🇺🇸 **Stake.us:** [Open redeem page]({item.redeem_link_us})\n"
                    f"🌍 **Stake.com:** [Open redeem page]({item.redeem_link_com})"
                ),
                "inline": False
            })

        # Clean, modern embed description without raw telegram text duplication
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

        embed: Dict[str, Any] = {
            "title": title,
            "description": embed_desc,
            "color": color,
            "fields": fields,
            "footer": {
                "text": f"{BOT_NAME} • Detected at {item.detected_at}"
            }
        }

        if item.platform.logo_url:
            embed["thumbnail"] = {"url": item.platform.logo_url}

        # 6. Media / image goes last
        if item.image_url:
            embed["image"] = {"url": item.image_url}

        return embed

    def _send_single_item_notification(self, item: BonusCodeItem, target_webhooks: List[str], target_channels: List[int]) -> bool:
        embed_dict = self.build_embed(item)
        role_tag = item.platform.role_tag
        # Webhook payload: exclude role tags for Rainbet (clean posts without @ mentions)
        webhook_payload = {
            "embeds": [embed_dict],
            "components": self.build_message_components(item),
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
                    logger.info(f"Successfully dispatched Discord embed for {item.platform.value} code '{item.code}' to a configured webhook.")
                    success = True
                else:
                    logger.error(f"Failed to send Discord webhook for {item.platform.value}. HTTP {resp.status_code}.")
            except Exception as e:
                logger.error(f"Exception while sending Discord webhook for {item.platform.value}: {type(e).__name__}")

        # 2. If bot client is connected and channels are configured, post to all direct channels
        if self.bot_client is not None:
            try:
                unique_channels = list(dict.fromkeys([int(c) for c in target_channels if c]))
                for cid in unique_channels:
                    if self._dispatch_to_channel(cid, embed_dict, item):
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

    def send_notification(
        self,
        item: BonusCodeItem,
        custom_webhook: Optional[str] = None,
        subscriber_uid: Optional[str] = None,
        guild_id: Optional[int] = None,
    ) -> bool:
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

        if guild_id is None:
            configured_guild_ids = self.dashboard_manager.get_configured_guild_ids()
            if configured_guild_ids:
                outcomes = []
                for configured_guild_id in configured_guild_ids:
                    configured_guild_id = int(configured_guild_id)
                    if self._already_delivered_to_guild(item, configured_guild_id):
                        outcomes.append(True)
                    else:
                        outcomes.append(
                            self.send_notification(item, guild_id=configured_guild_id)
                        )
                return bool(outcomes) and all(outcomes)

        get_webhooks = (
            lambda platform: self.dashboard_manager.get_guild_webhooks(guild_id, platform)
            if guild_id is not None
            else self.dashboard_manager.get_webhooks(platform)
        )
        get_channels = (
            lambda platform: self.dashboard_manager.get_guild_channels(guild_id, platform)
            if guild_id is not None
            else self.dashboard_manager.get_channels(platform)
        )

        if item.is_dual_stake or item.platform == Platform.DUAL_STAKE:
            us_item = item.to_stake_us_item()
            com_item = item.to_stake_com_item()

            us_webhooks = set(get_webhooks(Platform.STAKE_US))
            us_channels = set(get_channels(Platform.STAKE_US))

            com_webhooks = set(get_webhooks(Platform.STAKE_COM))
            com_channels = set(get_channels(Platform.STAKE_COM))

            # Destinations configured for BOTH platforms (or fallback to Default if neither configured)
            shared_webhooks = list(us_webhooks.intersection(com_webhooks))
            shared_channels = list(us_channels.intersection(com_channels))

            exclusive_us_webhooks = list(us_webhooks - set(shared_webhooks))
            exclusive_us_channels = list(us_channels - set(shared_channels))

            exclusive_com_webhooks = list(com_webhooks - set(shared_webhooks))
            exclusive_com_channels = list(com_channels - set(shared_channels))

            # Check if neither platform is configured -> fallback to Default routes ONCE (combined card)
            if not us_webhooks and not us_channels and not com_webhooks and not com_channels:
                def_webhooks = get_webhooks("Default")
                if guild_id is None and self.default_webhook_url and self.default_webhook_url not in def_webhooks:
                    def_webhooks.append(self.default_webhook_url)
                def_channels = get_channels("Default")
                success = self._send_single_item_notification(item, def_webhooks, def_channels)
                save_backup("post", "Dual Stake", item.code, f"value={item.amount_value} wager={item.wager_requirement}")
                if guild_id is None:
                    for sub_uid in self.dashboard_manager.get_all_subscriber_ids():
                        success = self._send_subscriber_notification(us_item, sub_uid) or success
                        success = self._send_subscriber_notification(com_item, sub_uid) or success
                self._record_delivery(item, guild_id, success)
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

            if guild_id is None:
                for sub_uid in self.dashboard_manager.get_all_subscriber_ids():
                    success = self._send_subscriber_notification(us_item, sub_uid) or success
                    success = self._send_subscriber_notification(com_item, sub_uid) or success
            self._record_delivery(item, guild_id, success)
            return success

        # Standard single platform dispatch
        target_webhooks = get_webhooks(item.platform)
        if guild_id is None and not target_webhooks and self.default_webhook_url:
            target_webhooks.append(self.default_webhook_url)
        target_channels = get_channels(item.platform)
        if not target_channels and not target_webhooks:
            target_channels = get_channels("Default")
            target_webhooks = get_webhooks("Default")
            if guild_id is None and self.default_webhook_url and self.default_webhook_url not in target_webhooks:
                target_webhooks.append(self.default_webhook_url)

        success = self._send_single_item_notification(item, target_webhooks, target_channels)

        # Save backup record
        save_backup("post", item.platform.value, item.code, f"value={item.amount_value} wager={item.wager_requirement}")

        # Dispatch to all active subscribers' personal channel/webhook routes (non-owner only)
        if guild_id is None:
            for sub_uid in self.dashboard_manager.get_all_subscriber_ids():
                success = self._send_subscriber_notification(item, sub_uid) or success

        self._record_delivery(item, guild_id, success)
        return success

    def _dispatch_to_channel(self, channel_id: int, embed_dict: Dict[str, Any], item: BonusCodeItem):
        """
        Safely dispatches an embed to a Discord text channel using client cache or API fetch.
        Waits for completion from worker threads and schedules safely when called
        from the bot's own event loop.
        """
        if not self.bot_client or self.bot_client.is_closed():
            return False

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
                        return False
                    except Exception as fe:
                        logger.warning(f"Could not fetch Discord channel ID {channel_id}: {fe}")
                        return False
                if channel is not None:
                    role_tag = item.platform.role_tag
                    embed = discord.Embed.from_dict(embed_dict)

                    await asyncio.wait_for(
                        channel.send(
                            content=role_tag or None,
                            embed=embed,
                            view=self.build_link_view(item),
                        ),
                        timeout=5.0
                    )
                    logger.info(f"✅ Dispatched {item.platform.value} drop '{item.code}' to direct channel #{getattr(channel, 'name', channel_id)} ({channel_id})")
                    return True
            except asyncio.TimeoutError:
                logger.warning(f"Timeout sending to channel {channel_id}, skipping")
            except Exception as exc:
                logger.error(f"Failed to deliver message to channel {channel_id}: {exc}")
            return False

        try:
            loop = getattr(self.bot_client, "loop", None)
            if loop and loop.is_running():
                try:
                    curr_loop = asyncio.get_running_loop()
                    if curr_loop is loop:
                        loop.create_task(_async_send())
                        return True
                    else:
                        future = asyncio.run_coroutine_threadsafe(_async_send(), loop)
                        try:
                            return bool(future.result(timeout=8.0))
                        except concurrent.futures.TimeoutError:
                            future.cancel()
                            logger.warning(f"Channel dispatch to {channel_id} timed out")
                            return False
                except RuntimeError:
                    # Called from worker thread with no active asyncio loop in that thread
                    future = asyncio.run_coroutine_threadsafe(_async_send(), loop)
                    try:
                        return bool(future.result(timeout=8.0))
                    except concurrent.futures.TimeoutError:
                        future.cancel()
                        logger.warning(f"Channel dispatch to {channel_id} timed out")
                        return False
                    except Exception:
                        raise
            elif loop:
                loop.create_task(_async_send())
                return True
        except Exception as e:
            logger.error(f"Error scheduling channel dispatch for {channel_id}: {e}")
        return False

    def send_raw_message(
        self,
        platform: Platform,
        content: str,
        subscriber_uid: Optional[str] = None,
        guild_id: Optional[int] = None,
    ) -> bool:
        """
        Sends a raw text message to all configured webhooks and direct channels for the platform.
        """
        if subscriber_uid:
            target_webhooks = self.dashboard_manager.get_subscriber_webhooks(subscriber_uid, platform)
            target_channels = self.dashboard_manager.get_subscriber_channels(subscriber_uid, platform)
            if not target_webhooks and not target_channels:
                target_webhooks = self.dashboard_manager.get_subscriber_webhooks(subscriber_uid, "Default")
                target_channels = self.dashboard_manager.get_subscriber_channels(subscriber_uid, "Default")
        elif guild_id is not None:
            target_webhooks = self.dashboard_manager.get_guild_webhooks(guild_id, platform)
            target_channels = self.dashboard_manager.get_guild_channels(guild_id, platform)
            if not target_webhooks and not target_channels:
                target_webhooks = self.dashboard_manager.get_guild_webhooks(guild_id, "Default")
                target_channels = self.dashboard_manager.get_guild_channels(guild_id, "Default")
        else:
            target_webhooks = self.get_webhooks_for_platform(platform)
            target_channels = self.get_channels_for_platform(platform)
        if not subscriber_uid and guild_id is None and not target_webhooks and self.default_webhook_url:
            target_webhooks = [self.default_webhook_url]
        if not subscriber_uid and guild_id is None and not target_channels and not target_webhooks:
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
                    logger.info(f"Successfully dispatched raw message for {platform.value} to a configured webhook.")
                    success = True
                else:
                    logger.error(f"Failed to send raw message webhook for {platform.value}. HTTP {resp.status_code}.")
            except Exception as e:
                logger.error(f"Exception while sending raw message webhook for {platform.value}: {type(e).__name__}")

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
