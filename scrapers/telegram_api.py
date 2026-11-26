import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class TelegramAPIClient:
    """
    Optional Telegram API client for private group/channel monitoring.
    Uses Telethon if available and credentials are configured.

    Supports joining private channels via invite hash (t.me/+HASH) so the
    bot can monitor channels it was invited to without knowing the numeric
    chat ID in advance.
    """

    def __init__(self):
        self._client = None
        self._error: Optional[str] = None
        self._try_initialize()

    def _try_initialize(self) -> None:
        try:
            from telethon.sync import TelegramClient  # noqa: F401
        except ImportError:
            self._error = (
                "telethon library is not installed. "
                "Install it with: pip install telethon>=1.36.0"
            )
            logger.warning(self._error)
            return

        try:
            from config import (
                TELEGRAM_API_ID,
                TELEGRAM_API_HASH,
                TELEGRAM_SESSION,
                TELEGRAM_BOT_TOKEN,
            )
        except ImportError:
            self._error = "Telegram configuration not found in config.py"
            logger.warning(self._error)
            return

        if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
            self._error = (
                "TELEGRAM_API_ID and TELEGRAM_API_HASH are required for private "
                "Telegram monitoring. Get them from https://my.telegram.org/apps"
            )
            logger.warning(self._error)
            return

        try:
            from telethon import TelegramClient

            session_name = TELEGRAM_SESSION or "leaked_gg_bot"
            self._client = TelegramClient(
                session_name,
                api_id=int(TELEGRAM_API_ID),
                api_hash=TELEGRAM_API_HASH,
            )
            if TELEGRAM_BOT_TOKEN:
                import asyncio
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self._client.start(bot_token=TELEGRAM_BOT_TOKEN)
                )
                loop.close()
            else:
                self._client.connect()
                if not self._client.is_user_authorized():
                    self._error = (
                        "Telegram session is not authorized. "
                        "Set TELEGRAM_SESSION to a valid session string or run "
                        "the auth flow once."
                    )
                    logger.warning(self._error)
                    self._client = None
                    return
            logger.info("Telegram API client initialized successfully")
        except Exception as e:
            self._error = f"Failed to initialize Telegram API client: {e}"
            logger.error(self._error)
            self._client = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        return self._client is not None and self._error is None

    @property
    def error_message(self) -> Optional[str]:
        return self._error

    # ------------------------------------------------------------------
    # Invite-hash joining
    # ------------------------------------------------------------------

    async def join_by_invite_hash(self, invite_hash: str) -> Optional[int]:
        """
        Joins a private Telegram channel/group using the hash portion of a
        t.me/+HASH invite link and returns the resolved numeric chat ID.

        If the account is already a member the existing entity is returned
        without raising an error.

        Returns the integer chat ID on success, None on failure.
        """
        if not self.is_available:
            return None
        try:
            from telethon.tl.functions.messages import ImportChatInviteRequest
            from telethon.errors import UserAlreadyParticipantError

            try:
                result = await self._client(ImportChatInviteRequest(invite_hash))
                chat = result.chats[0] if result.chats else None
            except UserAlreadyParticipantError:
                # Already a member — resolve the entity directly
                chat = await self._client.get_entity(f"t.me/+{invite_hash}")

            if chat is None:
                logger.warning(f"join_by_invite_hash: no chat returned for hash {invite_hash!r}")
                return None

            chat_id = getattr(chat, "id", None)
            if chat_id is not None:
                # Telegram supergroups/channels use negative IDs in the API
                if chat_id > 0:
                    chat_id = -chat_id
                logger.info(
                    f"Joined/resolved private channel via invite hash "
                    f"{invite_hash!r} → chat_id={chat_id}"
                )
            return chat_id
        except Exception as e:
            logger.error(f"Failed to join channel via invite hash {invite_hash!r}: {e}")
            return None

    async def ensure_joined(self, chat_id: int, invite_hash: Optional[str]) -> bool:
        """
        Ensures the Telethon session is a member of the channel.
        Tries to resolve by chat_id first; falls back to joining via invite_hash.
        Returns True if the channel is accessible.
        """
        if not self.is_available:
            return False
        try:
            await self._client.get_entity(chat_id)
            return True
        except Exception:
            pass
        if invite_hash:
            resolved = await self.join_by_invite_hash(invite_hash)
            return resolved is not None
        return False

    # ------------------------------------------------------------------
    # Chat metadata
    # ------------------------------------------------------------------

    async def get_chat_metadata(self, chat_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_available:
            return None
        try:
            entity = await self._client.get_entity(chat_id)
            return {
                "id": getattr(entity, "id", chat_id),
                "title": getattr(entity, "title", None),
                "username": getattr(entity, "username", None),
                "type": type(entity).__name__,
            }
        except Exception as e:
            logger.error(f"Failed to resolve Telegram chat {chat_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # Message fetching
    # ------------------------------------------------------------------

    async def fetch_messages(
        self,
        chat_id: int,
        limit: int = 50,
        offset_id: Optional[int] = None,
        invite_hash: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetches recent messages from a private Telegram chat/channel.

        If the channel is not yet accessible and an invite_hash is provided,
        the client will attempt to join first.

        Returns a list of message dicts with id, text, date, media flags,
        photo_url, and any embedded hyperlinks.
        """
        if not self.is_available:
            return []

        # Ensure we are a member before fetching
        accessible = await self.ensure_joined(chat_id, invite_hash)
        if not accessible:
            logger.warning(
                f"fetch_messages: channel {chat_id} is not accessible "
                f"(invite_hash={invite_hash!r})"
            )
            return []

        try:
            messages: List[Dict[str, Any]] = []
            async for msg in self._client.iter_messages(
                chat_id, limit=limit, offset_id=offset_id or 0
            ):
                if msg is None:
                    continue

                message_data: Dict[str, Any] = {
                    "id": msg.id,
                    "text": msg.text or "",
                    "date": msg.date.isoformat() if msg.date else None,
                    "media": bool(msg.media),
                    "has_photo": bool(getattr(msg, "photo", None)),
                    "has_video": bool(getattr(msg, "video", None)),
                    "has_document": bool(getattr(msg, "document", None)),
                }

                # Attempt to get a direct photo URL (works for user accounts,
                # not always available for bot tokens)
                try:
                    photo_url = getattr(msg.file, "url", None) if msg.file else None
                    if photo_url:
                        message_data["photo_url"] = photo_url
                except Exception:
                    pass

                # Extract hyperlinks from message entities
                if msg.entities:
                    links = [
                        entity.url
                        for entity in msg.entities
                        if hasattr(entity, "url") and entity.url
                    ]
                    if links:
                        message_data["links"] = links

                messages.append(message_data)

            return messages
        except Exception as e:
            logger.error(f"Failed to fetch messages from Telegram chat {chat_id}: {e}")
            return []

    # ------------------------------------------------------------------
    # Media download
    # ------------------------------------------------------------------

    async def download_message_media(
        self, chat_id: int, message_id: int
    ) -> Optional[bytes]:
        """
        Downloads media (photo/video) for a specific message as raw bytes.
        Used as an OCR source for codes embedded in private Telegram images.
        Returns None if media is unavailable or download fails.
        """
        if not self.is_available:
            return None
        try:
            msg = await self._client.get_messages(chat_id, ids=message_id)
            if msg is None or not msg.media:
                return None
            return await self._client.download_media(msg, bytes)
        except Exception as e:
            logger.debug(
                f"Failed to download media for message {message_id} "
                f"in chat {chat_id}: {e}"
            )
            return None
