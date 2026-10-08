import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class TelegramAPIClient:
    """
    Optional Telegram API client for private group/channel monitoring.
    Uses telethon if available and credentials are configured.
    """
    def __init__(self):
        self._client = None
        self._error: Optional[str] = None
        self._try_initialize()

    def _try_initialize(self) -> None:
        try:
            from telethon import TelegramClient
            from telethon.errors import ApiIdInvalidError, PhoneNumberInvalidError
        except ImportError:
            self._error = "telethon library is not installed. Install it with: pip install telethon>=1.36.0"
            logger.warning(self._error)
            return

        try:
            from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION, TELEGRAM_BOT_TOKEN
        except ImportError:
            self._error = "Telegram configuration not found in config.py"
            logger.warning(self._error)
            return

        if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
            self._error = (
                "TELEGRAM_API_ID and TELEGRAM_API_HASH are required for private Telegram monitoring. "
                "Get them from https://my.telegram.org/apps"
            )
            logger.warning(self._error)
            return

        try:
            session_name = TELEGRAM_SESSION or "leaked_gg_bot"
            if TELEGRAM_BOT_TOKEN:
                self._client = TelegramClient(
                    session_name,
                    api_id=int(TELEGRAM_API_ID),
                    api_hash=TELEGRAM_API_HASH,
                ).start(bot_token=TELEGRAM_BOT_TOKEN)
            else:
                self._client = TelegramClient(
                    session_name,
                    api_id=int(TELEGRAM_API_ID),
                    api_hash=TELEGRAM_API_HASH,
                )
                self._client.connect()
                if not self._client.is_user_authorized():
                    self._error = (
                        "Telegram session is not authorized. "
                        "Set TELEGRAM_SESSION to a valid session string or run the auth flow once."
                    )
                    logger.warning(self._error)
                    return
            logger.info("Telegram API client initialized successfully")
        except Exception as e:
            self._error = f"Failed to initialize Telegram API client: {e}"
            logger.error(self._error)

    @property
    def is_available(self) -> bool:
        return self._client is not None and self._error is None

    @property
    def error_message(self) -> Optional[str]:
        return self._error

    async def get_chat_metadata(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Resolves chat metadata for a private Telegram chat/channel.
        Returns dict with id, title, username, type, etc.
        """
        if not self.is_available:
            return None
        try:
            entity = await self._client.get_entity(chat_id)
            return {
                "id": getattr(entity, "id", chat_id),
                "title": getattr(entity, "title", None),
                "username": getattr(entity, "username", None),
                "type": str(type(entity).__name__),
            }
        except Exception as e:
            logger.error(f"Failed to resolve Telegram chat {chat_id}: {e}")
            return None

    async def fetch_messages(self, chat_id: int, limit: int = 50, offset_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetches recent messages from a private Telegram chat/channel.
        Returns list of message dicts with id, text, date, media, etc.
        """
        if not self.is_available:
            return []
        try:
            messages = []
            async for msg in self._client.iter_messages(chat_id, limit=limit, offset_id=offset_id):
                if msg is None:
                    continue
                message_data: Dict[str, Any] = {
                    "id": msg.id,
                    "text": msg.text or "",
                    "date": msg.date.isoformat() if msg.date else None,
                    "media": bool(msg.media),
                    "has_photo": bool(msg.photo),
                    "has_video": bool(msg.video),
                    "has_document": bool(msg.document),
                }
                try:
                    photo_url = getattr(msg.file, "url", None) if msg.file else None
                    if photo_url:
                        message_data["photo_url"] = photo_url
                except Exception:
                    pass
                if msg.entities:
                    links = []
                    for entity in msg.entities:
                        if hasattr(entity, "url") and entity.url:
                            links.append(entity.url)
                    if links:
                        message_data["links"] = links
                messages.append(message_data)
            return messages
        except Exception as e:
            logger.error(f"Failed to fetch messages from Telegram chat {chat_id}: {e}")
            return []

    async def download_message_media(self, chat_id: int, message_id: int) -> Optional[bytes]:
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
            logger.debug(f"Failed to download media for message {message_id} in chat {chat_id}: {e}")
            return None
