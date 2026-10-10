import os
import json
import logging
from typing import Dict, Any, Optional, List, Union, Tuple
from models import Platform
from config import (
    DISCORD_WEBHOOK_URL, DISCORD_WEBHOOK_STAKE_COM, DISCORD_WEBHOOK_STAKE_US,
    DISCORD_WEBHOOK_STAKE_COM_VIP, DISCORD_WEBHOOK_STAKE_US_VIP,
    DISCORD_WEBHOOK_SHUFFLE_COM, DISCORD_WEBHOOK_SHUFFLE_US,
    DISCORD_WEBHOOK_QZINO, DISCORD_WEBHOOK_RAINBET,
    DISCORD_WEBHOOK_DEGEN, DISCORD_WEBHOOK_GOATED, DISCORD_WEBHOOK_WINNA,
    DISCORD_WEBHOOK_THRILL,
    CHECK_INTERVAL_SECONDS, OWNER_USER_ID,
    TELEGRAM_CHANNELS, TARGET_SOURCES, TELEGRAM_PRIVATE_SOURCES
)

logger = logging.getLogger(__name__)

DASHBOARD_CONFIG_FILE = "routes_config.json"

class DashboardManager:
    """
    Enterprise-ready dashboard & routing manager.
    Supports multi-channel (multiple channel IDs) and multi-webhook (multiple webhook URLs)
    mappings per platform, with dynamic persistence, environment fallbacks,
    and granular owner / crypto subscriber access control.
    """
    def __init__(self, filepath: str = DASHBOARD_CONFIG_FILE):
        self.filepath = filepath
        self.config: Dict[str, Any] = {
            "channels": {},
            "webhooks": {},
            "sources": {
                "telegram": {},
                "web": [],
                "telegram_private": dict(TELEGRAM_PRIVATE_SOURCES),
            },
            "subscribers": {
                str(OWNER_USER_ID): {
                    "role": "owner",
                    "active": True,
                    "note": "Project Creator & Owner"
                }
            },
            "settings": {
                "realtime_monitoring_enabled": True,
                "check_interval_seconds": CHECK_INTERVAL_SECONDS
            },
            "subscriber_routes": {}
        }
        self.load()

    def _normalize_platform_key(self, platform_input: Any) -> str:
        if isinstance(platform_input, Platform):
            return platform_input.value
        plat_str = str(platform_input).strip()
        matched = Platform.from_str(plat_str)
        if matched != Platform.UNKNOWN:
            return matched.value
        if plat_str.lower() in ["default", "all", "global"]:
            return "Default"
        return plat_str

    def _ensure_channel_list(self, raw_val: Any) -> List[int]:
        """
        Normalizes single int/string or list of ints into a clean List[int].
        """
        if raw_val is None:
            return []
        if isinstance(raw_val, list):
            res = []
            for item in raw_val:
                try:
                    res.append(int(item))
                except (ValueError, TypeError):
                    pass
            return list(dict.fromkeys(res))
        try:
            return [int(raw_val)]
        except (ValueError, TypeError):
            return []

    def _ensure_webhook_list(self, raw_val: Any) -> List[str]:
        """
        Normalizes single string or list of strings into a clean List[str].
        """
        if raw_val is None:
            return []
        if isinstance(raw_val, list):
            res = [str(item).strip() for item in raw_val if str(item).strip()]
            return list(dict.fromkeys(res))
        s = str(raw_val).strip()
        return [s] if s else []

    def load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.config["channels"] = data.get("channels", {})
                        self.config["webhooks"] = data.get("webhooks", {})
                        self.config["sources"] = data.get("sources", {
                            "telegram": {},
                            "web": [],
                            "telegram_private": dict(TELEGRAM_PRIVATE_SOURCES),
                        })
                        self.config["subscribers"] = data.get("subscribers", {
                            str(OWNER_USER_ID): {
                                "role": "owner",
                                "active": True,
                                "note": "Project Creator & Owner"
                            }
                        })
                        # Ensure owner is always active
                        self.config["subscribers"][str(OWNER_USER_ID)] = {
                            "role": "owner",
                            "active": True,
                            "note": "Project Creator & Owner"
                        }
                        self.config["settings"] = {
                            **self.config["settings"],
                            **data.get("settings", {})
                        }
                        self.config["subscriber_routes"] = data.get("subscriber_routes", {})
                    logger.info(f"Loaded dashboard configuration from {self.filepath}")
            except Exception as e:
                logger.error(f"Error loading dashboard config from {self.filepath}: {e}")
        else:
            self.save()

    def is_owner(self, user_id: Union[int, str]) -> bool:
        """
        Returns True if the given user ID matches the project owner / creator.
        """
        return str(user_id).strip() == str(OWNER_USER_ID)

    def is_authorized(self, user_id: Union[int, str]) -> bool:
        """
        Returns True if the user is the project owner OR an active authorized subscriber ($2 crypto).
        Checks expiration date for time-limited subscriptions.
        """
        uid = str(user_id).strip()
        if self.is_owner(uid):
            return True
        sub_entry = self.config.get("subscribers", {}).get(uid)
        if sub_entry and sub_entry.get("active", False):
            # Check expiration for time-limited subscriptions
            expires_at = sub_entry.get("expires_at")
            if expires_at:
                try:
                    from datetime import datetime
                    exp_date = datetime.fromisoformat(expires_at)
                    if datetime.now(exp_date.tzinfo) > exp_date:
                        logger.info(f"Subscriber {uid} access expired on {expires_at}")
                        return False
                except Exception:
                    pass
            return True
        return False

    def add_subscriber(self, user_id: Union[int, str], note: str = "Active Subscriber", role: str = "subscriber", duration: str = "lifetime") -> None:
        """
        Grants full bot dashboard configuration access to a user.
        Supports duration: 'lifetime', '1month' (30 days), or '7days' (7 days).
        """
        from datetime import datetime, timedelta, timezone
        uid = str(user_id).strip()
        if "subscribers" not in self.config:
            self.config["subscribers"] = {}
        
        expires_at = None
        if duration == "1month":
            expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        elif duration == "7days":
            expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        
        self.config["subscribers"][uid] = {
            "role": role,
            "active": True,
            "note": note,
            "duration": duration,
            "expires_at": expires_at,
            "granted_at": datetime.now(timezone.utc).isoformat()
        }
        self.save()
        exp_str = expires_at or "never (lifetime)"
        logger.info(f"Added subscriber {uid} ({note}) - expires: {exp_str}")

    def remove_subscriber(self, user_id: Union[int, str]) -> bool:
        """
        Revokes subscriber dashboard access. Owner cannot be removed.
        """
        uid = str(user_id).strip()
        if self.is_owner(uid):
            return False
        if uid in self.config.get("subscribers", {}):
            del self.config["subscribers"][uid]
            self.save()
            logger.info(f"Removed subscriber {uid}")
            return True
        return False

    def get_subscribers(self) -> Dict[str, Any]:
        """
        Returns dictionary of all active subscribers.
        """
        return self.config.get("subscribers", {})

    def save(self) -> None:
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved dashboard config to {self.filepath}")
        except Exception as e:
            logger.error(f"Failed to save dashboard config to {self.filepath}: {e}")

    # ----------------------------------------------------
    # Multi-Channel Routing Operations
    # ----------------------------------------------------
    def get_channels(self, platform_input: Any) -> List[int]:
        """
        Returns all configured Discord channel IDs for the specified platform.
        Falls back to 'Default' platform channels if none are configured.
        """
        key = self._normalize_platform_key(platform_input)
        if key in self.config["channels"]:
            channels = self._ensure_channel_list(self.config["channels"][key])
            if channels:
                return channels
        # Fallback to default
        if key != "Default" and "Default" in self.config["channels"]:
            return self._ensure_channel_list(self.config["channels"]["Default"])
        return []

    def get_channel(self, platform_input: Any) -> Optional[int]:
        """
        Returns the primary (first) channel ID for backward compatibility.
        """
        channels = self.get_channels(platform_input)
        return channels[0] if channels else None

    def add_channel(self, platform_input: Any, channel_id: int) -> str:
        """
        Adds a channel ID to the platform's multi-channel routing list.
        """
        key = self._normalize_platform_key(platform_input)
        existing = self._ensure_channel_list(self.config["channels"].get(key))
        cid = int(channel_id)
        if cid not in existing:
            existing.append(cid)
            self.config["channels"][key] = existing
            self.save()
        return key

    def remove_channel(self, platform_input: Any, channel_id: int) -> str:
        """
        Removes a specific channel ID from the platform's routing list.
        """
        key = self._normalize_platform_key(platform_input)
        existing = self._ensure_channel_list(self.config["channels"].get(key))
        cid = int(channel_id)
        if cid in existing:
            existing.remove(cid)
            if existing:
                self.config["channels"][key] = existing
            else:
                self.config["channels"].pop(key, None)
            self.save()
        return key

    def clear_channels(self, platform_input: Any) -> str:
        """
        Clears all channel IDs for a platform.
        """
        key = self._normalize_platform_key(platform_input)
        self.config["channels"].pop(key, None)
        self.save()
        return key

    def set_channel(self, platform_input: Any, channel_id: Optional[int]) -> str:
        """
        Replaces or sets a single primary channel ID.
        """
        key = self._normalize_platform_key(platform_input)
        if channel_id is None:
            self.config["channels"].pop(key, None)
        else:
            self.config["channels"][key] = [int(channel_id)]
        self.save()
        return key

    def set_channels(self, platform_input: Any, channel_ids: List[int]) -> str:
        """
        Replaces the complete list of channel IDs for a platform.
        """
        key = self._normalize_platform_key(platform_input)
        cleaned = self._ensure_channel_list(channel_ids)
        if cleaned:
            self.config["channels"][key] = cleaned
        else:
            self.config["channels"].pop(key, None)
        self.save()
        return key

    # ----------------------------------------------------
    # Per-Subscriber / Per-Guild Routing Operations
    # ----------------------------------------------------
    def _get_subscriber_routes(self, user_id: Union[int, str]) -> Dict[str, Any]:
        uid = str(user_id).strip()
        if uid not in self.config["subscriber_routes"]:
            self.config["subscriber_routes"][uid] = {"channels": {}, "webhooks": {}, "guild_id": None}
        return self.config["subscriber_routes"][uid]

    def get_subscriber_channels(self, user_id: Union[int, str], platform_input: Any) -> List[int]:
        """Returns channel IDs configured by a specific subscriber for a platform."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        key = self._normalize_platform_key(platform_input)
        return self._ensure_channel_list(sub_routes.get("channels", {}).get(key))

    def get_subscriber_webhooks(self, user_id: Union[int, str], platform_input: Any) -> List[str]:
        """Returns webhook URLs configured by a specific subscriber for a platform."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        key = self._normalize_platform_key(platform_input)
        return self._ensure_webhook_list(sub_routes.get("webhooks", {}).get(key))

    def add_subscriber_channel(self, user_id: Union[int, str], platform_input: Any, channel_id: int) -> str:
        """Adds a channel ID to a subscriber's personal routing list for a platform."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        key = self._normalize_platform_key(platform_input)
        if "channels" not in sub_routes:
            sub_routes["channels"] = {}
        existing = self._ensure_channel_list(sub_routes["channels"].get(key))
        cid = int(channel_id)
        if cid not in existing:
            existing.append(cid)
            sub_routes["channels"][key] = existing
            self.save()
        return key

    def remove_subscriber_channel(self, user_id: Union[int, str], platform_input: Any, channel_id: int) -> str:
        """Removes a specific channel ID from a subscriber's routing list."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        key = self._normalize_platform_key(platform_input)
        existing = self._ensure_channel_list(sub_routes.get("channels", {}).get(key))
        cid = int(channel_id)
        if cid in existing:
            existing.remove(cid)
            if existing:
                sub_routes["channels"][key] = existing
            else:
                sub_routes["channels"].pop(key, None)
            self.save()
        return key

    def clear_subscriber_channels(self, user_id: Union[int, str], platform_input: Optional[Any] = None) -> str:
        """Clears subscriber-specific channel routing for one platform or all platforms."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        if platform_input is None:
            sub_routes["channels"] = {}
        else:
            key = self._normalize_platform_key(platform_input)
            sub_routes.setdefault("channels", {}).pop(key, None)
        self.save()
        return uid

    def set_subscriber_webhook(self, user_id: Union[int, str], platform_input: Any, webhook_url: str) -> str:
        """Sets a webhook URL for a subscriber's platform routing."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        key = self._normalize_platform_key(platform_input)
        if "webhooks" not in sub_routes:
            sub_routes["webhooks"] = {}
        sub_routes["webhooks"][key] = self._ensure_webhook_list(webhook_url)
        self.save()
        return key

    def add_subscriber_webhook(self, user_id: Union[int, str], platform_input: Any, webhook_url: str) -> str:
        """Adds a webhook URL to a subscriber's routing list for a platform."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        key = self._normalize_platform_key(platform_input)
        if "webhooks" not in sub_routes:
            sub_routes["webhooks"] = {}
        existing = self._ensure_webhook_list(sub_routes["webhooks"].get(key))
        url = str(webhook_url).strip()
        if url and url not in existing:
            existing.append(url)
            sub_routes["webhooks"][key] = existing
            self.save()
        return key

    def clear_subscriber_webhooks(self, user_id: Union[int, str], platform_input: Optional[Any] = None) -> str:
        """Clears subscriber-specific webhook routing for one platform or all platforms."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        if platform_input is None:
            sub_routes["webhooks"] = {}
        else:
            key = self._normalize_platform_key(platform_input)
            sub_routes.setdefault("webhooks", {}).pop(key, None)
        self.save()
        return uid

    def set_subscriber_guild(self, user_id: Union[int, str], guild_id: Union[int, str]) -> None:
        """Associates a subscriber with a specific Discord guild (server)."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        sub_routes["guild_id"] = str(guild_id)
        self.save()

    def get_subscriber_guild(self, user_id: Union[int, str]) -> Optional[str]:
        """Returns the Discord guild ID associated with a subscriber, if set."""
        uid = str(user_id).strip()
        sub_routes = self._get_subscriber_routes(uid)
        return sub_routes.get("guild_id")

    def get_all_subscriber_ids(self) -> List[str]:
        """Returns list of all subscriber user IDs (excluding owner)."""
        subs = self.config.get("subscribers", {})
        return [
            uid for uid in subs.keys()
            if uid != str(OWNER_USER_ID) and self.is_authorized(uid)
        ]

    # ----------------------------------------------------
    def get_webhooks(self, platform_input: Any) -> List[str]:
        """
        Returns all configured Discord Webhook URLs for the specified platform.
        Merges dynamic dashboard webhooks, environment variable routes, and fallbacks.
        """
        key = self._normalize_platform_key(platform_input)
        webhooks: List[str] = []

        # 1. Dynamic dashboard configured webhooks
        if key in self.config["webhooks"]:
            webhooks.extend(self._ensure_webhook_list(self.config["webhooks"][key]))

        # 2. Environment variable routes from config.py
        env_routes = {
            Platform.STAKE_COM.value: DISCORD_WEBHOOK_STAKE_COM,
            Platform.STAKE_US.value: DISCORD_WEBHOOK_STAKE_US,
            Platform.STAKE_COM_VIP_NOTICES.value: DISCORD_WEBHOOK_STAKE_COM_VIP,
            Platform.STAKE_US_VIP_NOTICES.value: DISCORD_WEBHOOK_STAKE_US_VIP,
            Platform.SHUFFLE_COM.value: DISCORD_WEBHOOK_SHUFFLE_COM,
            Platform.SHUFFLE_US.value: DISCORD_WEBHOOK_SHUFFLE_US,
            Platform.QZINO.value: DISCORD_WEBHOOK_QZINO,
            Platform.RAINBET.value: DISCORD_WEBHOOK_RAINBET,
            Platform.DEGEN.value: DISCORD_WEBHOOK_DEGEN,
            Platform.GOATED.value: DISCORD_WEBHOOK_GOATED,
            Platform.WINNA.value: DISCORD_WEBHOOK_WINNA,
            Platform.THRILL.value: DISCORD_WEBHOOK_THRILL,
        }
        if key in env_routes and env_routes[key]:
            webhooks.append(env_routes[key].strip())

        # 3. Fallback to default webhook if empty
        if not webhooks:
            def_wh_list = self._ensure_webhook_list(self.config["webhooks"].get("Default"))
            webhooks.extend(def_wh_list)
            if DISCORD_WEBHOOK_URL and DISCORD_WEBHOOK_URL.strip():
                webhooks.append(DISCORD_WEBHOOK_URL.strip())

        # Deduplicate while preserving order
        return list(dict.fromkeys(webhooks))

    def get_webhook(self, platform_input: Any) -> Optional[str]:
        """
        Returns the primary (first) webhook URL for backward compatibility.
        """
        webhooks = self.get_webhooks(platform_input)
        return webhooks[0] if webhooks else None

    def add_webhook(self, platform_input: Any, webhook_url: str) -> str:
        """
        Adds a webhook URL to the platform's multi-webhook routing list.
        """
        key = self._normalize_platform_key(platform_input)
        url = str(webhook_url).strip()
        if not url:
            return key
        existing = self._ensure_webhook_list(self.config["webhooks"].get(key))
        if url not in existing:
            existing.append(url)
            self.config["webhooks"][key] = existing
            self.save()
        return key

    def remove_webhook(self, platform_input: Any, webhook_url: str) -> str:
        """
        Removes a specific webhook URL from the platform's routing list.
        """
        key = self._normalize_platform_key(platform_input)
        url = str(webhook_url).strip()
        existing = self._ensure_webhook_list(self.config["webhooks"].get(key))
        if url in existing:
            existing.remove(url)
            if existing:
                self.config["webhooks"][key] = existing
            else:
                self.config["webhooks"].pop(key, None)
            self.save()
        return key

    def clear_webhooks(self, platform_input: Any) -> str:
        """
        Clears all webhooks for a platform.
        """
        key = self._normalize_platform_key(platform_input)
        self.config["webhooks"].pop(key, None)
        self.save()
        return key

    def set_webhook(self, platform_input: Any, webhook_url: Optional[str]) -> str:
        """
        Replaces or sets a single primary webhook URL.
        """
        key = self._normalize_platform_key(platform_input)
        if not webhook_url:
            self.config["webhooks"].pop(key, None)
        else:
            self.config["webhooks"][key] = [str(webhook_url).strip()]
        self.save()
        return key

    def set_webhooks(self, platform_input: Any, webhook_urls: List[str]) -> str:
        """
        Replaces the complete list of webhook URLs for a platform.
        """
        key = self._normalize_platform_key(platform_input)
        cleaned = self._ensure_webhook_list(webhook_urls)
        if cleaned:
            self.config["webhooks"][key] = cleaned
        else:
            self.config["webhooks"].pop(key, None)
        self.save()
        return key

    def clear_routes(self, platform_input: Any) -> str:
        """
        Clears both channels and webhooks for a platform.
        """
        key = self._normalize_platform_key(platform_input)
        self.config["channels"].pop(key, None)
        self.config["webhooks"].pop(key, None)
        self.save()
        return key

    # ----------------------------------------------------
    # General Settings
    # ----------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.config["settings"].get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.config["settings"][key] = value
        self.save()

    def get_all_routes_summary(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns a complete routing map across all platforms for display in the Discord dashboard.
        Includes multi-channel IDs, multi-webhook URLs, and formatted display fields.
        """
        platforms = [
            Platform.STAKE_US,
            Platform.STAKE_COM,
            Platform.STAKE_US_VIP_NOTICES,
            Platform.STAKE_COM_VIP_NOTICES,
            Platform.SHUFFLE_US,
            Platform.SHUFFLE_COM,
            Platform.RAINBET,
            Platform.DEGEN,
            Platform.QZINO,
            Platform.GOATED,
            Platform.THRILL,
            Platform.WINNA,
            Platform.DUAL_STAKE,
        ]

        summary = {}
        for p in platforms:
            channels = self.get_channels(p)
            webhooks = self.get_webhooks(p)
            primary_ch = channels[0] if channels else None
            primary_wh = webhooks[0] if webhooks else None

            # Format channel display
            if not channels:
                ch_display = "❌ *Not Assigned*"
            elif len(channels) == 1:
                ch_display = f"<#{channels[0]}> (`{channels[0]}`)"
            else:
                ch_display = ", ".join(f"<#{c}>" for c in channels) + f" (`{len(channels)} Channels`)"

            # Format webhook display
            if not webhooks:
                wh_display = "❌ *Not Set*"
            elif len(webhooks) == 1:
                wh_display = "✅ *1 Webhook Active*"
            else:
                wh_display = f"✅ *{len(webhooks)} Webhooks Active*"

            summary[p.value] = {
                "emoji": p.emoji,
                "color": p.embed_color,
                "channel_id": primary_ch,
                "channel_ids": channels,
                "channel_count": len(channels),
                "channels_display": ch_display,
                "webhook_configured": bool(webhooks),
                "webhook_urls": webhooks,
                "webhook_count": len(webhooks),
                "webhooks_display": wh_display,
                "webhook_masked": f"{primary_wh[:35]}...{primary_wh[-6:]}" if primary_wh and len(primary_wh) > 45 else (primary_wh or "Not Set")
            }

        # Also add Default fallback
        def_channels = self._ensure_channel_list(self.config["channels"].get("Default"))
        def_webhooks = self.get_webhooks("Default")
        def_prim_ch = def_channels[0] if def_channels else None
        def_prim_wh = def_webhooks[0] if def_webhooks else None

        if not def_channels:
            def_ch_disp = "❌ *Not Assigned*"
        elif len(def_channels) == 1:
            def_ch_disp = f"<#{def_channels[0]}> (`{def_channels[0]}`)"
        else:
            def_ch_disp = ", ".join(f"<#{c}>" for c in def_channels) + f" (`{len(def_channels)} Channels`)"

        if not def_webhooks:
            def_wh_disp = "❌ *Not Set*"
        elif len(def_webhooks) == 1:
            def_wh_disp = "✅ *1 Webhook Active*"
        else:
            def_wh_disp = f"✅ *{len(def_webhooks)} Webhooks Active*"

        summary["Default"] = {
            "emoji": "🌐",
            "color": 0x5865F2,
            "channel_id": def_prim_ch,
            "channel_ids": def_channels,
            "channel_count": len(def_channels),
            "channels_display": def_ch_disp,
            "webhook_configured": bool(def_webhooks),
            "webhook_urls": def_webhooks,
            "webhook_count": len(def_webhooks),
            "webhooks_display": def_wh_disp,
            "webhook_masked": f"{def_prim_wh[:35]}...{def_prim_wh[-6:]}" if def_prim_wh and len(def_prim_wh) > 45 else (def_prim_wh or "Not Set")
        }

        return summary

    # ----------------------------------------------------
    # Monitored Sources Operations (Telegram & Web Review URLs)
    # ----------------------------------------------------
    def _normalize_telegram_platform(self, platform_input: Optional[Any]) -> str:
        if not platform_input:
            return "custom"
        if isinstance(platform_input, Platform):
            if platform_input == Platform.STAKE_US:
                return "stake_us"
            if platform_input == Platform.STAKE_COM:
                return "stake_com"
            if platform_input == Platform.STAKE_US_VIP_NOTICES:
                return "stake_us_vip"
            if platform_input == Platform.STAKE_COM_VIP_NOTICES:
                return "stake_com_vip"
            if platform_input in [Platform.SHUFFLE_US, Platform.SHUFFLE_COM]:
                return "shuffle"
            if platform_input == Platform.QZINO:
                return "qzino"
            if platform_input == Platform.RAINBET:
                return "rainbet"
            if platform_input == Platform.DEGEN:
                return "degen"
            if platform_input == Platform.GOATED:
                return "goated"
            if platform_input == Platform.WINNA:
                return "winna"
            if platform_input == Platform.MYPRIZE_US:
                return "myprize_us"
            if platform_input == Platform.CROWNSCOINS:
                return "crowncoins"
            if platform_input == Platform.REALPRIZE:
                return "realprize"
            if platform_input == Platform.ACEBET:
                return "acebet"
            if platform_input == Platform.LONESTAR:
                return "lonestar"
            if platform_input == Platform.CHANCED:
                return "chanced"
            if platform_input == Platform.PULSZ:
                return "pulsz"
            if platform_input == Platform.THRILL:
                return "thrill"
            if platform_input == Platform.MODO:
                return "modo"
            if platform_input == Platform.BABA:
                return "baba"
            if platform_input == Platform.COOKED_US:
                return "cooked_us"
            if platform_input == Platform.COOKED_COM:
                return "cooked_com"
            if platform_input == Platform.WOWVEGAS:
                return "wowvegas"
            if platform_input == Platform.YAYCASINO:
                return "yaycasino"
            return "custom"

        p_str = str(platform_input).strip().lower().replace(".", "_").replace(" ", "_").replace("-", "_")
        if p_str in ["stake_us", "stakeus", "us"]:
            return "stake_us"
        if p_str in ["stake_com", "stakecom", "com"]:
            return "stake_com"
        if "stake_us_vip" in p_str or "stakeus vip" in p_str or "us_vip" in p_str:
            return "stake_us_vip"
        if "stake_com_vip" in p_str or "stakecom vip" in p_str or "com_vip" in p_str:
            return "stake_com_vip"
        if "shuffle" in p_str:
            return "shuffle"
        if "qzino" in p_str:
            return "qzino"
        if "rainbet" in p_str:
            return "rainbet"
        if "degen" in p_str:
            return "degen"
        if "goated" in p_str:
            return "goated"
        if "winna" in p_str:
            return "winna"
        if "myprize" in p_str:
            return "myprize_us"
        if "crowncoins" in p_str:
            return "crowncoins"
        if "realprize" in p_str:
            return "realprize"
        if "acebet" in p_str:
            return "acebet"
        if "lonestar" in p_str:
            return "lonestar"
        if "chanced" in p_str:
            return "chanced"
        if "pulsz" in p_str:
            return "pulsz"
        if "thrill" in p_str:
            return "thrill"
        if "modo" in p_str:
            return "modo"
        if "baba" in p_str:
            return "baba"
        if "cooked_us" in p_str or "cookedus" in p_str:
            return "cooked_us"
        if "cooked_com" in p_str or "cookedcom" in p_str:
            return "cooked_com"
        if "wowvegas" in p_str:
            return "wowvegas"
        if "yaycasino" in p_str:
            return "yaycasino"
        if p_str in ["codestats", "codestats2"]:
            return "codestats"
        return "custom"

    def get_telegram_sources(self) -> Dict[str, List[str]]:
        """
        Returns combined dictionary of all Telegram channels monitored (built-in + custom additions + private sources).
        """
        combined: Dict[str, List[str]] = {}
        for p_key, ch_list in TELEGRAM_CHANNELS.items():
            combined[p_key] = list(ch_list)

        custom_tg = self.config.get("sources", {}).get("telegram", {})
        for p_key, ch_list in custom_tg.items():
            if p_key not in combined:
                combined[p_key] = []
            for ch in ch_list:
                clean_ch = str(ch).strip()
                if clean_ch and clean_ch not in combined[p_key]:
                    combined[p_key].append(clean_ch)

        private_tg = self.config.get("sources", {}).get("telegram_private", {})
        for chat_id, meta in private_tg.items():
            label = meta.get("label", chat_id)
            source_key = f"private_{chat_id}"
            combined[source_key] = [label]
        return combined

    def get_web_sources(self) -> List[str]:
        """
        Returns combined list of all Web Review Sources monitored (built-in + custom additions).
        """
        combined = list(TARGET_SOURCES)
        custom_web = self.config.get("sources", {}).get("web", [])
        for url in custom_web:
            u = str(url).strip()
            if u and u not in combined:
                combined.append(u)
        return combined

    def add_telegram_source(self, channel_input: str, platform_input: Optional[Any] = "custom") -> Tuple[bool, str]:
        """
        Adds a new custom Telegram channel handle to monitor for events.
        """
        clean_ch = str(channel_input).strip()
        clean_ch = clean_ch.replace("https://t.me/s/", "").replace("https://t.me/", "").replace("@", "").strip()
        clean_ch = clean_ch.split("/")[0].strip()
        if not clean_ch:
            return False, "❌ Invalid Telegram channel handle."

        plat_key = self._normalize_telegram_platform(platform_input)
        if "sources" not in self.config:
            self.config["sources"] = {"telegram": {}, "web": []}
        if "telegram" not in self.config["sources"]:
            self.config["sources"]["telegram"] = {}
        if plat_key not in self.config["sources"]["telegram"]:
            self.config["sources"]["telegram"][plat_key] = []

        existing_custom = self.config["sources"]["telegram"][plat_key]
        if clean_ch in existing_custom:
            return False, f"⚠️ Telegram channel `@{clean_ch}` is already registered in custom **{plat_key}** sources."

        existing_default = TELEGRAM_CHANNELS.get(plat_key, [])
        if clean_ch in existing_default:
            return False, f"ℹ️ Telegram channel `@{clean_ch}` is already an active built-in **{plat_key}** source."

        existing_custom.append(clean_ch)
        self.config["sources"]["telegram"][plat_key] = existing_custom
        self.save()
        logger.info(f"Added custom Telegram source @{clean_ch} to {plat_key}")
        return True, f"✅ Successfully added Telegram channel `@{clean_ch}` to **{plat_key}** monitoring."

    def remove_telegram_source(self, channel_input: str, platform_input: Optional[Any] = None) -> Tuple[bool, str]:
        """
        Removes a custom Telegram channel handle from monitoring.
        """
        clean_ch = str(channel_input).strip()
        clean_ch = clean_ch.replace("https://t.me/s/", "").replace("https://t.me/", "").replace("@", "").strip()
        clean_ch = clean_ch.split("/")[0].strip()
        if not clean_ch:
            return False, "❌ Invalid Telegram channel handle."

        custom_tg = self.config.get("sources", {}).get("telegram", {})
        removed = False
        if platform_input:
            plat_key = self._normalize_telegram_platform(platform_input)
            if plat_key in custom_tg and clean_ch in custom_tg[plat_key]:
                custom_tg[plat_key].remove(clean_ch)
                if not custom_tg[plat_key]:
                    del custom_tg[plat_key]
                removed = True
        else:
            for p_key, ch_list in list(custom_tg.items()):
                if clean_ch in ch_list:
                    ch_list.remove(clean_ch)
                    if not ch_list:
                        del custom_tg[p_key]
                    removed = True

        if removed:
            self.save()
            logger.info(f"Removed custom Telegram source @{clean_ch}")
            return True, f"✅ Removed custom Telegram channel `@{clean_ch}` from monitoring."

        # Check if it was a built-in channel
        for p_key, ch_list in TELEGRAM_CHANNELS.items():
            if clean_ch in ch_list:
                return False, f"⚠️ `@{clean_ch}` is a core built-in source and cannot be removed."

        return False, f"❌ Custom Telegram channel `@{clean_ch}` was not found in custom monitoring list."

    def add_web_source(self, url_input: str) -> Tuple[bool, str]:
        """
        Adds a new custom Web Review URL to monitor for bonus codes.
        """
        u = str(url_input).strip()
        if not (u.startswith("http://") or u.startswith("https://")):
            return False, "❌ Invalid URL format (must start with `http://` or `https://`)."

        if "sources" not in self.config:
            self.config["sources"] = {"telegram": {}, "web": []}
        if "web" not in self.config["sources"]:
            self.config["sources"]["web"] = []

        if u in self.config["sources"]["web"]:
            return False, f"⚠️ Web source `{u}` is already registered in custom sources."

        if u in TARGET_SOURCES:
            return False, f"ℹ️ Web source `{u}` is already an active built-in target source."

        self.config["sources"]["web"].append(u)
        self.save()
        logger.info(f"Added custom Web review source {u}")
        return True, f"✅ Successfully added web review source `{u}` to monitoring."

    def remove_web_source(self, url_input: str) -> Tuple[bool, str]:
        """
        Removes a custom Web Review URL from monitoring.
        """
        u = str(url_input).strip()
        custom_web = self.config.get("sources", {}).get("web", [])
        if u in custom_web:
            custom_web.remove(u)
            self.save()
            logger.info(f"Removed custom Web review source {u}")
            return True, f"✅ Removed custom web review source `{u}` from monitoring."

        if u in TARGET_SOURCES:
            return False, f"⚠️ `{u}` is a core built-in source and cannot be removed."

        return False, f"❌ Custom web source `{u}` was not found in custom monitoring list."

    # ----------------------------------------------------
    # Telegram Private Source Operations
    # ----------------------------------------------------
    def get_telegram_private_sources(self) -> Dict[str, Any]:
        """
        Returns all configured Telegram private group/channel sources.
        """
        return self.config.get("sources", {}).get("telegram_private", {})

    def add_telegram_private_source(self, chat_id: str, label: str = "", reference_msg_id: Optional[int] = None, source_url: str = "") -> Tuple[bool, str]:
        """
        Adds a private Telegram chat/channel source by chat ID.
        Built-in sources from config.TELEGRAM_PRIVATE_SOURCES are always allowed.
        """
        chat_id_str = str(chat_id).strip()
        if not chat_id_str:
            return False, "❌ Invalid Telegram chat ID."

        if "sources" not in self.config:
            self.config["sources"] = {"telegram": {}, "web": [], "telegram_private": {}}
        if "telegram_private" not in self.config["sources"]:
            self.config["sources"]["telegram_private"] = {}

        source_url = source_url or f"https://t.me/c/{chat_id_str.lstrip('-')}/{reference_msg_id or ''}".rstrip("/")
        self.config["sources"]["telegram_private"][chat_id_str] = {
            "label": label or f"Private Telegram {chat_id_str}",
            "reference_msg_id": reference_msg_id,
            "source_url": source_url,
        }
        self.save()
        logger.info(f"Added/updated private Telegram source {chat_id_str}")
        return True, f"✅ Added/updated private Telegram source `{chat_id_str}` with label `{label or chat_id_str}`."

    def remove_telegram_private_source(self, chat_id: str) -> Tuple[bool, str]:
        """
        Removes a private Telegram chat/channel source by chat ID.
        """
        chat_id_str = str(chat_id).strip()
        private_tg = self.config.get("sources", {}).get("telegram_private", {})
        if chat_id_str in private_tg:
            del private_tg[chat_id_str]
            self.save()
            logger.info(f"Removed private Telegram source {chat_id_str}")
            return True, f"✅ Removed private Telegram source `{chat_id_str}`."

        return False, f"❌ Private Telegram source `{chat_id_str}` was not found."

    def get_all_custom_sources(self) -> Dict[str, Any]:
        """
        Returns all user-configured custom sources.
        """
        return {
            "telegram": self.config.get("sources", {}).get("telegram", {}),
            "web": self.config.get("sources", {}).get("web", [])
        }

    def get_all_monitored_sources_summary(self) -> Dict[str, Any]:
        """
        Returns a complete breakdown of all active sources across Telegram, Web, and Live APIs.
        """
        tg = self.get_telegram_sources()
        web = self.get_web_sources()
        custom = self.get_all_custom_sources()
        private_tg = self.get_telegram_private_sources()

        total_tg_channels = sum(len(ch_list) for ch_list in tg.values())
        total_custom_tg = sum(len(ch_list) for ch_list in custom.get("telegram", {}).values())
        total_custom_web = len(custom.get("web", []))
        total_private_tg = len(private_tg)

        web_by_platform = self._group_web_sources_by_platform(web)

        return {
            "telegram_by_platform": tg,
            "total_telegram_channels": total_tg_channels,
            "web_sources": web,
            "total_web_sources": len(web),
            "web_sources_by_platform": web_by_platform,
            "stakestats_api": "https://stakestats.net/stake/tools/code",
            "codestats_feed": "https://codestats.gg",
            "custom_sources": custom,
            "total_custom_sources": total_custom_tg + total_custom_web,
            "telegram_private_sources": private_tg,
            "total_telegram_private_sources": total_private_tg,
        }

    def _group_web_sources_by_platform(self, web_sources: List[str]) -> Dict[str, List[str]]:
        """
        Groups web review sources by inferred platform using URL heuristics.
        """
        grouped: Dict[str, List[str]] = {}
        for url in web_sources:
            plat = self._infer_platform_from_web_url(url)
            key = plat.value if isinstance(plat, Platform) else str(plat)
            if key not in grouped:
                grouped[key] = []
            if url not in grouped[key]:
                grouped[key].append(url)
        return grouped

    def _infer_platform_from_web_url(self, url: str) -> Any:
        """
        Infers the primary platform a web review source covers using URL/path heuristics.
        """
        lower = url.lower()
        if "stake.com" in lower or "stake-com" in lower:
            return Platform.STAKE_COM
        if "stake.us" in lower or "stake-us" in lower:
            return Platform.STAKE_US
        if "shuffle.com" in lower:
            return Platform.SHUFFLE_COM
        if "shuffle.us" in lower:
            return Platform.SHUFFLE_US
        if "rainbet" in lower:
            return Platform.RAINBET
        if "qzino" in lower:
            return Platform.QZINO
        if "degen" in lower:
            return Platform.DEGEN
        if "goated" in lower:
            return Platform.GOATED
        return "General"
