import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Branding
BOT_NAME = "Leaked.GG"
BOT_AVATAR_URL = os.getenv("BOT_AVATAR_URL", "https://i.imgur.com/8Q9Z5bF.png")

# Discord Configuration (Webhook URLs per platform)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_WEBHOOK_STAKE_COM = os.getenv("DISCORD_WEBHOOK_STAKE_COM", "")
DISCORD_WEBHOOK_STAKE_US = os.getenv("DISCORD_WEBHOOK_STAKE_US", "")
DISCORD_WEBHOOK_STAKE_COM_VIP = os.getenv("DISCORD_WEBHOOK_STAKE_COM_VIP", "")
DISCORD_WEBHOOK_STAKE_US_VIP = os.getenv("DISCORD_WEBHOOK_STAKE_US_VIP", "")
DISCORD_WEBHOOK_SHUFFLE_COM = os.getenv("DISCORD_WEBHOOK_SHUFFLE_COM", "")
DISCORD_WEBHOOK_SHUFFLE_US = os.getenv("DISCORD_WEBHOOK_SHUFFLE_US", "")
DISCORD_WEBHOOK_QZINO = os.getenv("DISCORD_WEBHOOK_QZINO", "")
DISCORD_WEBHOOK_RAINBET = os.getenv("DISCORD_WEBHOOK_RAINBET", "")
DISCORD_WEBHOOK_DEGEN = os.getenv("DISCORD_WEBHOOK_DEGEN", "")
DISCORD_WEBHOOK_GOATED = os.getenv("DISCORD_WEBHOOK_GOATED", "")
DISCORD_WEBHOOK_WINNA = os.getenv("DISCORD_WEBHOOK_WINNA", "")
DISCORD_WEBHOOK_THRILL = os.getenv("DISCORD_WEBHOOK_THRILL", "")

# Discord Bot Token (for on-demand !code and /activecodes commands)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# Owner & Project Creator Discord User ID (Full administrative access)
OWNER_USER_ID = 1051355279511519273
DISCORD_INVITE_URL = "https://discord.gg/TvJe6BV7ge"

# Platform Embed Colors (Hex integer) - Strict Platform Color Palette:
# shuffle.us: white, shuffle.com: purple, qzino: yellow, stake.us: orange, stake.com: pink, rainbet: dark blue
COLOR_STAKE_COM = 0xFF1493    # Stake.com Pink (Deep Pink)
COLOR_STAKE_US = 0xFF7700     # Stake.us Orange (Vibrant Orange)
COLOR_STAKE_COM_VIP_NOTICES = 0xFF6B9D  # Stake.com VIP Notices Soft Pink
COLOR_STAKE_US_VIP_NOTICES = 0xFFB347   # Stake.us VIP Notices Warm Amber
COLOR_SHUFFLE_COM = 0x8A2BE2  # Shuffle.com Purple (Blue Violet)
COLOR_SHUFFLE_US = 0xFFFFFF   # Shuffle.us White (Clean Pure White)
COLOR_QZINO = 0xFFD700        # Qzino Yellow (Gold Yellow)
COLOR_RAINBET = 0x0A2540      # Rainbet Dark Blue (Navy Dark Blue)
COLOR_DEGEN = 0xEF4444        # Degen Crimson Red
COLOR_GOATED = 0xF59E0B       # Goated Amber Gold
COLOR_DUAL_STAKE = 0x8B5CF6   # Dual Stake Violet
COLOR_MYPRIZE_US = 0x06B6D4   # MYPRIZE.US Cyan
COLOR_CROWNSCOINS = 0xEAB308  # CrownCoins Gold
COLOR_REALPRIZE = 0xEC4899    # RealPrize Pink
COLOR_ACEBET = 0xEF4444       # AceBet Casino Red
COLOR_LONESTAR = 0xF97316     # LoneStar Casino Orange
COLOR_CHANCED = 0x22C55E      # Chanced Casino Green
COLOR_PULSZ = 0x8B5CF6        # PULSZ Purple
COLOR_THRILL = 0xEF4444       # THRILL Red
COLOR_MODO = 0x3B82F6         # MODO Blue
COLOR_BABA = 0x10B981         # BABA Green
COLOR_COOKED_US = 0xF59E0B    # COOKED.US Amber
COLOR_COOKED_COM = 0xF59E0B   # COOKED.COM Amber
COLOR_WOWVEGAS = 0x8B5CF6     # WOWVEGAS Violet
COLOR_YAYCASINO = 0xEC4899    # YAYCASINO Pink
COLOR_WINNA = 0xFFD700        # WINNA Gold
COLOR_DEFAULT = 0x5865F2      # Discord Blurple fallback

# Affiliate Signup Links per Platform
AFFILIATE_SIGNUP_LINKS = {
    "Stake.com": os.getenv("AFFILIATE_STAKE_COM", "https://stake.com/?c=SELFMADE"),
    "Stake.us": os.getenv("AFFILIATE_STAKE_US", "https://www.stake.us/?c=selfmade"),
    "Stake.com - VIP Notices": os.getenv("AFFILIATE_STAKE_COM_VIP", "https://stake.com/?c=SELFMADE"),
    "Stake.us - VIP Notices": os.getenv("AFFILIATE_STAKE_US_VIP", "https://www.stake.us/?c=selfmade"),
    "Shuffle.com": os.getenv("AFFILIATE_SHUFFLE_COM", "https://shuffle.com/?r=selfmade"),
    "Shuffle.us": os.getenv("AFFILIATE_SHUFFLE_US", "https://shuffle.us/?r=selfmade"),
    "Qzino": os.getenv("AFFILIATE_QZINO", "https://qzino.ai/?r=SELFMADE"),
    "Rainbet": os.getenv("AFFILIATE_RAINBET", "https://rainbet.com/?r=murphy"),
    "Degen": os.getenv("AFFILIATE_DEGEN", "https://degen.com/r/selfmade"),
    "Goated": os.getenv("AFFILIATE_GOATED", "https://goated.com/?r=selfmade"),
    "MYPRIZE.US": os.getenv("AFFILIATE_MYPRIZE_US", "https://myprize.us/invite/Traystrees50"),
    "CrownCoins": os.getenv("AFFILIATE_CROWNSCOINS", "https://crowncoinscasino.com/?utm_campaign=856db775-8290-42d7-93b4-76ddc67ddf4b&utm_source=friends"),
    "RealPrize": os.getenv("AFFILIATE_REALPRIZE", "https://www.realprize.com/refer/212990"),
    "AceBet Casino": os.getenv("AFFILIATE_ACEBET", "https://acebet.cc/welcome/r/selfmade"),
    "LoneStar Casino": os.getenv("AFFILIATE_LONESTAR", "https://lonestarcasino.com/refer/869128"),
    "Chanced Casino": os.getenv("AFFILIATE_CHANCED", "https://chanced.com/c/v5a5yh"),
    "PULSZ": os.getenv("AFFILIATE_PULSZ", "https://www.pulsz.com/?invited_by=ga1vnk"),
    "THRILL": os.getenv("AFFILIATE_THRILL", "https://thrill.com/?r=selfmade"),
    "MODO": os.getenv("AFFILIATE_MODO", "https://modo.us/?referralCode=Z901K9"),
    "BABA": os.getenv("AFFILIATE_BABA", "https://play.babacasino.com/#/?referral_id=5403a829ac9926527b94e7c068708e07&inv_referral=true&fb_source=invite"),
    "COOKED.US": os.getenv("AFFILIATE_COOKED_US", "https://cooked.us/?auth=register&referral_source=SELFMADE"),
    "COOKED.COM": os.getenv("AFFILIATE_COOKED_COM", "https://cooked.com/?auth=register&referral_source=SELFMADE"),
    "WOWVEGAS": os.getenv("AFFILIATE_WOWVEGAS", "https://www.wowvegas.com/?raf=1274028"),
    "YAYCASINO": os.getenv("AFFILIATE_YAYCASINO", "https://www.yaycasino.com/signup/7ab97436-a07a-4514-9506-bcbbcd2495e8"),
    "WINNA": os.getenv("AFFILIATE_WINNA", "https://winna.com/?bonus-center=true&SELFMADE"),
}

# Platform-specific KICK stream links and labels
DEFAULT_KICK_LINK = "https://www.kick.com/traystrees50"
DEFAULT_KICK_LABEL = "🎥 Follow Traystrees50"
KICK_STREAM_LINKS = {
    "Rainbet": "https://www.kick.com/moonbootmurphy",
}
KICK_STREAM_LABELS = {
    "Rainbet": "🎥 Watch On Kick",
}

# Platform-specific source name & URL overrides for embed "Source" field
PLATFORM_SOURCE_OVERRIDES = {
    "Rainbet": ("Rainbet Affiliate", "https://rainbet.com/?r=murphy"),
}

# Polling & Runtime Settings
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "20"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
STATE_FILE_PATH = os.getenv("STATE_FILE_PATH", "seen_codes.json")

# Anti-Rate Limit, Cloudflare Evasion & Proxy Settings
ENABLE_JITTER = os.getenv("ENABLE_JITTER", "true").lower() in ("true", "1", "yes")
MIN_JITTER_DELAY = float(os.getenv("MIN_JITTER_DELAY", "0.8"))
MAX_JITTER_DELAY = float(os.getenv("MAX_JITTER_DELAY", "2.2"))
ENABLE_PROXY_ROTATION = os.getenv("ENABLE_PROXY_ROTATION", "false").lower() in ("true", "1", "yes")
PROXY_LIST_ENV = os.getenv("PROXY_LIST", "")

# Telegram Monitoring Sources
TELEGRAM_CHANNELS = {
    "stake_us": ["highrollerscodeUS", "dailybonuscodeUS", "codestats2"],
    "stake_com": ["highrollerscode", "dailybonuscodes", "codestats2"],
    "degen": ["degendotcom"],
    "rainbet": ["EddiesCodesRainbet"],
    "winna": ["EddiesCodesWinna"],
    "shuffle": ["anyclaimershuffle", "codestats2"],
    "thrill": ["thrillcodes"],
    "qzino": ["qzino_code", "qzino", "qzinodotai"],
    "codestats": ["codestats2"],
}

# Telegram Private Group/Channel Sources
# These are private Telegram sources identified by chat ID.
# Reference message IDs are used for discovery metadata.
TELEGRAM_PRIVATE_SOURCES = {
    "-2922581483": {
        "reference_msg_id": 61,
        "label": "Stake.com VIP Notices",
        "source_url": "https://t.me/c/2922581483/61",
    },
    "-1542279201": {
        "reference_msg_id": 257,
        "label": "Stake.us VIP Notices",
        "source_url": "https://t.me/c/1542279201/257",
    },
}

# Telegram Optional API Credentials (for private groups like t.me/c/1542279201/257)
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# External Tool Endpoints
STAKESTATS_CODE_URL = "https://stakestats.net/stake/tools/code"
STAKESTATS_API_URL = "https://stakestats.net/api/codes"
CODESTATS_URL = "https://codestats.gg"

# OCR.space API (optional, for extracting bonus codes embedded in images)
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "")
OCR_SPACE_API_URL = "https://api.ocr.space/parse/image"

# Default Target Affiliate Web Review Sources
# Note: Dead sites (dimers.com, next.io, thespike.gg, etc.) are filtered out
# from the sweep to reduce timeout delays and improve detection speed.
# The Telegram sources + StakeStats API + CodeStats feeds cover all active codes.
TARGET_SOURCES = [
    "https://www.jaxon.gg/gambling/stake-com/bonus-drop-codes/",
    "https://www.thelines.com/casino/sweepstakes/stake-us/bonus-drop-codes/",
    "https://www.vegasinsider.com/sweepstakes-casinos/stake-us/bonus-drop/",
    "https://www.wetten.com/us/reviews/stake-us/bonus-drops/",
    "https://www.ballislife.com/betting/reviews/stake-us/bonus-drops/",
    "https://www.promoguy.us/reviews/stake-us/bonus-drops/",
    "https://www.gamechampions.com/en/reviews/stake-com/bonus-drop-codes/",
    "https://www.gamechampions.com/en/reviews/stake-us/bonus-drop-codes/",
    "https://thegruelingtruth.com/reviews/stake-us/bonus-drops/",
    "https://www.deadspin.com/sweepstakes-casinos/reviews/stake-us/bonus-drop-code/",
]

# Standard HTTP Headers to ensure reliable access
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}
