"""
platform_rules.py
=================
Complete 13-platform registry, 5-stage classification pipeline, and
persistent source-history auto-learning for the Leaked.GG bot.

Stage 1 - Explicit platform badge / domain keyword match
Stage 2 - Unambiguous code-prefix regex match
Stage 3 - Shared-prefix disambiguation (CHAMP)
Stage 4 - Known Source: lookup (static + data/source_history.json)
Stage 5 - Channel-origin guarded fallback (never defaults to Shuffle)
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path to the persistent source-history cache
# ---------------------------------------------------------------------------
_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "source_history.json"
)
_history_lock = threading.Lock()


def _load_history() -> Dict[str, str]:
    try:
        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_history(data: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(_HISTORY_PATH), exist_ok=True)
    with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def learn_source(source_name: str, platform: str) -> None:
    """
    Persist a newly confirmed source -> platform mapping.
    Skips shared multi-platform sources (GameChampions without US/COM suffix).
    """
    if not source_name or not platform:
        return
    # Skip ambiguous shared sources
    if re.match(r"^GameChampions$", source_name.strip(), re.I):
        return
    with _history_lock:
        data = _load_history()
        if data.get(source_name) != platform:
            data[source_name] = platform
            _save_history(data)
            logger.debug(f"[source_history] Learned: {source_name!r} -> {platform!r}")


# ---------------------------------------------------------------------------
# Banner UI stopword blocklist (used by OCR banner parser and Stage 2)
# ---------------------------------------------------------------------------
BANNER_STOPWORDS: frozenset = frozenset({
    "GOATED", "GOATEDCOM", "DEGEN", "DEGENCASINO", "DEGENCOM",
    "BONUS", "DROP", "DROPS", "CODE", "CODES", "FLASH", "ALERT",
    "BOOST", "BOOSTS", "BIRTHDAY", "PROMO", "CLAIM", "CLAIMS",
    "REDEEM", "WAGER", "WAGERED", "REQUIREMENT", "LAST", "DAYS",
    "FIRST", "USERS", "PLAYERS", "LIMIT", "LIMITED", "VIP", "EVENT",
    "HUNT", "FREE", "SPINS", "CASH", "USDC", "USDT", "BTC",
    "PLAY", "NOW", "JOIN", "TELEGRAM", "DISCORD", "HTTPS", "HTTP",
    "WWW", "COM", "STAKE", "SHUFFLE", "RAINBET", "QZINO", "WINNA",
    "THRILL", "GAMBA", "RAZED",
})

# ---------------------------------------------------------------------------
# PLATFORM_RULES registry
# ---------------------------------------------------------------------------
# Each entry:
#   "platform_id"  : canonical lowercase slug
#   "keywords"     : list of lowercase substrings that identify the platform
#   "sources_us"   : affiliate source names that map to this platform
#   "code_regexes" : list of (compiled_re, note) — ordered most-specific first
#   "claim_url"    : direct redemption URL template (use {code} placeholder)
#   "claim_note"   : optional human-readable note for embed
# ---------------------------------------------------------------------------

PLATFORM_RULES: List[Dict] = [
    # ── stake.us ────────────────────────────────────────────────────────────
    {
        "id": "stake.us",
        "keywords": [
            "stake.us", "stakeus", "stake-us",
            "stake.us/settings/offers",
        ],
        "sources": [
            "ballislife", "thespike.gg", "gamechampions us",
            "sportsgrid stake.us", "vegasinsider", "deadspin",
            "esportsbetting us", "esportsbetting", "dimers", "stake.us telegram", "stakeus",
        ],
        "code_regexes": [
            (re.compile(r"^BIL[A-Z0-9]{7}$"), "Ballislife"),
            (re.compile(r"^SPIKEUS[A-Za-z0-9]{8}$"), "TheSpike.gg"),
            (re.compile(r"^stakeus[a-z0-9]{10,}$", re.I), "Stake.us prefix (fixed: was {12}, most real codes are longer)"),
            (re.compile(r"^ESBUS[A-Z0-9]+$"), "EsportsBetting US"),
            (re.compile(r"^DIMERS[A-Z0-9]{8,}$"), "Dimers"),
            (re.compile(r"^BIL[A-Z0-9]{7,}$"), "Ballislife (lenient)"),
            (re.compile(r"^(?:SPORTS(?:GR|\d+GRID)|SGRID|SG\d+)[A-Za-z0-9]+$"), "SportsGrid"),
            (re.compile(r"^DSN[A-Z0-9]{6,}$", re.I), "Deadspin"),
            (re.compile(r"^LatestDrops\d+[a-z]+$", re.I), "Deadspin"),
            (re.compile(r"^BonusDROP[A-Z0-9]+$", re.I), "Deadspin"),
        ],
        "claim_url": "https://stake.us/settings/offers?type=code&code={code}&currency=sweeps&modal=redeemBonus",
        "claim_note": None,
    },
    # ── stake.com ───────────────────────────────────────────────────────────
    {
        "id": "stake.com",
        "keywords": [
            "stake.com", "stakecom", "stake-com",
            "stake.ac", "stake.games", "stake.bet",
            "stake.pet", "stake.mba", "stake.jp", "stake.bz",
            "stake.com/settings/offers",
        ],
        "sources": [
            "freetips", "esportsbetting com", "eddie stream",
            "stake.com telegram", "kick drop",
        ],
        "code_regexes": [
            (re.compile(r"^ESBCOM[A-Z0-9]+$"), "EsportsBetting COM"),
            (re.compile(r"^stakecom[a-z0-9]+$", re.I), "Stake.com prefix"),
            # FreeTips PascalCase drops (validated by source/keyword context)
            (re.compile(r"^[A-Z][a-z]+(?:[A-Z][a-z]+){1,3}$"), "FreeTips PascalCase"),
        ],
        "claim_url": "https://stake.com/settings/offers?type=code&code={code}&currency=ltc&modal=redeemBonus",
        "claim_note": None,
    },
    # ── goated ──────────────────────────────────────────────────────────────
    {
        "id": "goated",
        "keywords": [
            "goated.com", "goated", "t.me/goateddrops",
            "t.me/goatedcom", "@goateddrops", "@goatedcom",
        ],
        "sources": [
            "goated drops", "goated official", "goated telegram",
            "flash code alert", "goated boost", "birthday promo",
        ],
        "code_regexes": [
            (re.compile(r"^(?:GOATED|GOAT)[A-Za-z0-9_-]{3,20}$", re.I), "Goated prefix"),
            # REMOVED 2026-11-26: generic 4-to-24-char context pattern.
            # It matched any 8-char Rainbet/Shuffle code. Prefix-only now.
        ],
        "claim_url": "https://www.goated.com",
        "claim_note": 'Click "Redeem Code" on Goated.com',
    },
    # ── degen ───────────────────────────────────────────────────────────────
    {
        "id": "degen",
        "keywords": [
            "degen.com", "degen", "degen casino",
            "degen legend", "discord.gg/degencom",
        ],
        "sources": [
            "degen telegram", "degen official", "degen drop",
            "degen bonus hunt", "degen boost", "degen event",
        ],
        "code_regexes": [
            (re.compile(r"^(?:DEGEN|DGN)[A-Za-z0-9_-]{3,20}$", re.I), "Degen prefix"),
            # REMOVED 2026-11-26: generic 4-to-24-char context pattern.
            # It matched any 8-char Rainbet/Shuffle code. Prefix-only now.
        ],
        "claim_url": "https://degen.com",
        "claim_note": 'Redeem via Rewards / Code modal on Degen.com',
    },
    # ── shuffle.us ──────────────────────────────────────────────────────────
    {
        "id": "shuffle.us",
        "keywords": ["shuffle.us", "shuffleus", "shuffle_us"],
        "sources": ["shuffle.us telegram", "codestats shuffle.us", "shuffleus"],
        "code_regexes": [
            (re.compile(r"^shuffleus[a-z0-9]+$", re.I), "Shuffle.us prefix"),
            # SHARED FORMAT (8-char) - keyword/app/footer required, see Stage 2.
            (re.compile(r"^[A-Z0-9]{8}$"), "SHARED FORMAT 8-char Shuffle.us"),
        ],
        "claim_url": "https://shuffle.us/vip-program?modal=redeem",
        "claim_note": None,
    },
    # ── shuffle.com ─────────────────────────────────────────────────────────
    {
        "id": "shuffle.com",
        "keywords": [
            "shuffle.com", "shufflecom", "shuffle.bet",
            "t.me/anyclaimershuffle",
        ],
        "sources": [
            "shuffle telegram", "shuffle vip", "noah stream",
            "codestats shuffle", "anyclaimershuffle",
        ],
        "code_regexes": [
            (re.compile(r"^shuffle(?:com)?[a-z0-9]+$", re.I), "Shuffle.com prefix"),
            # SHARED FORMAT (8-char) - keyword/app/footer required, see Stage 2.
            (re.compile(r"^[A-Z0-9]{8}$"), "SHARED FORMAT 8-char Shuffle.com"),
        ],
        "claim_url": "https://shuffle.com/vip-program?modal=redeem",
        "claim_note": None,
    },
    # ── rainbet.us ──────────────────────────────────────────────────────────
    {
        "id": "rainbet.us",
        "keywords": ["rainbet.us", "rainbetus"],
        "sources": ["rainbet.us telegram", "rainbet us"],
        "code_regexes": [
            (re.compile(r"^(?:RBUS|RAINBETUS)[A-Za-z0-9_-]+$", re.I), "Rainbet.us prefix"),
            # SHARED FORMAT (8-char) - keyword/app/footer required, see Stage 2.
            # Footer handle is @rainbetuscodes / @rainbetusvip.
            (re.compile(r"^[A-Z0-9]{8}$"), "SHARED FORMAT 8-char Rainbet.us"),
        ],
        "claim_url": "https://rainbet.us",
        "claim_note": None,
    },
    # ── rainbet ─────────────────────────────────────────────────────────────
    {
        "id": "rainbet",
        "keywords": ["rainbet.com", "rainbet"],
        "sources": [
            "rainbet telegram", "rainbet official",
            "rainbet kick", "moonbootmurphy", "selfmade",
        ],
        "code_regexes": [
            (re.compile(r"^(?:RB|RAINBET)[A-Za-z0-9_-]+$", re.I), "Rainbet prefix"),
            # SHARED FORMAT - keyword/app/footer required, see Stage 2.
            (re.compile(r"^[A-Z0-9]{6,12}$"), "SHARED FORMAT Rainbet"),
        ],
        "claim_url": "https://rainbet.com",
        "claim_note": None,
    },
    # ── thrill.com ──────────────────────────────────────────────────────────
    {
        "id": "thrill.com",
        "keywords": ["thrill.com", "thrill"],
        "sources": ["thrill telegram", "codestats thrill", "thrill official"],
        "code_regexes": [
            (re.compile(r"^THRILL[A-Za-z0-9_-]+$", re.I), "Thrill prefix"),
            # SHARED FORMAT (10-char) - app/footer required, see Stage 2.
            # Do not assume Thrill from 10-char format alone.
            (re.compile(r"^[A-Z0-9]{10}$"), "SHARED FORMAT 10-char Thrill"),
        ],
        "claim_url": "https://thrill.com",
        "claim_note": None,
    },
    # ── winna ───────────────────────────────────────────────────────────────
    {
        "id": "winna",
        "keywords": ["winna.com", "winna"],
        "sources": ["winna telegram", "winna official"],
        "code_regexes": [
            (re.compile(r"^WINNA[A-Za-z0-9_-]+$", re.I), "Winna prefix"),
        ],
        "claim_url": "https://winna.com",
        "claim_note": None,
    },
    # ── gamba ───────────────────────────────────────────────────────────────
    {
        "id": "gamba",
        "keywords": ["gamba.com", "gamba"],
        "sources": ["gamba telegram", "gamba official"],
        "code_regexes": [
            (re.compile(r"^GAMBA[A-Za-z0-9_-]+$", re.I), "Gamba prefix"),
            # Gamba format, matched against the emoji-stripped code (see Stage 2).
            (re.compile(r"^[a-z0-9]{9,17}$"), "Gamba format (emoji-stripped)"),
        ],
        "claim_url": "https://gamba.com",
        "claim_note": None,
    },
    # ── razed ───────────────────────────────────────────────────────────────
    {
        "id": "razed",
        "keywords": ["razed.com", "razed"],
        "sources": ["razed telegram", "razed official"],
        "code_regexes": [
            (re.compile(r"^RAZED[A-Za-z0-9_-]+$", re.I), "Razed prefix"),
            # Usually ends "rzd" - NOT a rule (lmd3c8qtxfr is the exception).
            (re.compile(r"^[a-z0-9]{9,12}$"), "Razed format"),
        ],
        "claim_url": "https://razed.com",
        "claim_note": None,
    },
    # ── qzino ───────────────────────────────────────────────────────────────
    {
        "id": "qzino",
        "keywords": ["qzino.com", "qzino"],
        "sources": ["qzino telegram", "qzino official"],
        "code_regexes": [
            (re.compile(r"^QZINO[A-Za-z0-9_-]+$", re.I), "Qzino prefix"),
        ],
        "claim_url": "https://qzino.com",
        "claim_note": None,
    },
]

# Shared CHAMP prefix — needs source/keyword context to disambiguate
_RE_CHAMP = re.compile(r"^CHAMP[A-Z0-9]{8}$")

# FreeTips PascalCase pattern (only valid when stake.com source/keyword present)
_RE_FREETIPS_PASCAL = re.compile(r"^[A-Z][a-z]+(?:[A-Z][a-z]+){1,3}$")

# Codes verified (by both claim links AND both platforms in the source feed)
# to be genuinely dual-platform. Only "bonusbuyspins" was verified dual in
# the Nov 21-26, 2026 Ctrl Alt Delete window. Every other code that merely
# lists both stake.us and stake.com links is AMBIGUOUS, not dual.
VERIFIED_DUAL_CODES = frozenset({"bonusbuyspins"})

# Example ambiguous user-submitted Stake codes, Nov 24-26, 2026 (both links
# listed as candidates, neither platform verified): samurai88y11, ninja3ty5,
# shadow8ii33, kairosaa99ii, tuvrd7p5, 7wamg2cc, 7lktqwha, hkyizm1u.
# Do not hard-code the list - ambiguity is decided by the Stage 1 rule below.

# ---------------------------------------------------------------------------
# Build fast lookup indexes
# ---------------------------------------------------------------------------
_KEYWORD_INDEX: List[Tuple[str, str]] = []   # (keyword_lower, platform_id)
_SOURCE_INDEX: Dict[str, str] = {}           # source_lower -> platform_id

for _rule in PLATFORM_RULES:
    _pid = _rule["id"]
    for _kw in _rule["keywords"]:
        _KEYWORD_INDEX.append((_kw.lower(), _pid))
    for _src in _rule["sources"]:
        _SOURCE_INDEX[_src.lower()] = _pid

# Sort keywords longest-first so more specific matches win
_KEYWORD_INDEX.sort(key=lambda x: -len(x[0]))


# ---------------------------------------------------------------------------
# 5-Stage Classification Pipeline
# ---------------------------------------------------------------------------

def classify_platform(
    text: str,
    code: str,
    source_name: str = "",
    channel_id: str = "",
    channel_name: str = "",
) -> Optional[str]:
    """
    Returns a platform_id string (e.g. 'stake.us', 'goated') or None.

    Evaluation order:
      Stage 1 — Explicit platform keyword / domain in text
      Stage 2 — Unambiguous code-prefix regex
      Stage 3 — Shared CHAMP prefix disambiguation
      Stage 4 — Known Source: lookup (static + source_history.json)
      Stage 5 — Channel-origin guarded fallback
    """
    t_lower = text.lower() if text else ""
    code_upper = (code or "").strip().upper()
    src_lower = (source_name or "").strip().lower()

    # ── Stage 1: Explicit keyword / domain ──────────────────────────────────
    # Both stake.us and stake.com present does NOT mean a verified dual drop.
    # Only a code in VERIFIED_DUAL_CODES is dual_stake; everything else with
    # both links is "ambiguous_stake" - both claim links are candidates only.
    has_stake_us = bool(re.search(r"stake\.us|stakeus|stake-us", t_lower))
    has_stake_com = bool(re.search(r"stake\.com|stakecom|stake-com", t_lower))
    if has_stake_us and has_stake_com:
        if (code or "").strip().lower() in VERIFIED_DUAL_CODES:
            return "dual_stake"
        return "ambiguous_stake"
    if has_stake_us:
        return "stake.us"
    if has_stake_com:
        return "stake.com"

    # Walk keyword index (longest match first, skipping stake already handled)
    for kw, pid in _KEYWORD_INDEX:
        if pid in ("stake.us", "stake.com"):
            continue  # already handled above
        if kw in t_lower:
            # Shuffle guard: only match shuffle if no other platform keyword present
            if pid in ("shuffle.us", "shuffle.com"):
                # Confirm no other non-shuffle platform keyword is present
                other_platforms = [
                    p for p in ("goated", "degen", "rainbet", "thrill", "winna",
                                "gamba", "razed", "qzino")
                    if p in t_lower
                ]
                if other_platforms:
                    continue
            return pid

    # ── Stage 2: Unambiguous code-prefix regex ───────────────────────────────
    # Gamba codes are emoji-obfuscated in the embed ("Remove the emoji to
    # claim it"); strip non-alphanumeric characters before format matching.
    code_stripped = re.sub(r"[^A-Za-z0-9_-]", "", code or "")
    for rule in PLATFORM_RULES:
        pid = rule["id"]
        regexes = rule["code_regexes"]
        for pattern, note in regexes:
            # SHARED FORMAT regexes (8-char Rainbet/Shuffle, 10-char Thrill,
            # 6-12-char Rainbet) must NEVER route on format alone. They only
            # match when the platform keyword / app / footer / source is also
            # present in the text or source name.
            if note.startswith("SHARED FORMAT"):
                _kw = pid.replace(".", "")
                if _kw not in t_lower and _kw not in src_lower and pid not in t_lower:
                    continue
            # Gamba / Razed lowercase formats match against the emoji-stripped code.
            _target = code_stripped if pid in ("gamba", "razed") else code
            if pattern.match(_target):
                # FreeTips PascalCase: only valid with stake.com source/keyword
                if pid == "stake.com" and _RE_FREETIPS_PASCAL.match(code):
                    if not (
                        "freetips" in src_lower
                        or "stake.com" in t_lower
                        or "stakecom" in t_lower
                    ):
                        continue
                return pid

    # ── Stage 3: Shared CHAMP prefix disambiguation ──────────────────────────
    if _RE_CHAMP.match(code_upper):
        if (
            "gamechampions us" in t_lower
            or "gamechampions us" in src_lower
            or "stake.us" in t_lower
        ):
            return "stake.us"
        return "stake.com"

    # ── Stage 4: Known Source: lookup ────────────────────────────────────────
    if src_lower:
        # Static index
        if src_lower in _SOURCE_INDEX:
            return _SOURCE_INDEX[src_lower]
        # GameChampions without US -> stake.com
        if re.match(r"^gamechampions(?!\s*us)", src_lower, re.I):
            return "stake.com"
        # EsportsBetting without COM -> stake.us
        if re.match(r"^esportsbetting(?!\s*com)", src_lower, re.I):
            return "stake.us"
        # Persistent history
        with _history_lock:
            history = _load_history()
        # Try exact match first, then case-insensitive
        if source_name in history:
            return history[source_name]
        for hist_src, hist_plat in history.items():
            if hist_src.lower() == src_lower:
                return hist_plat

    # ── Stage 5: Channel-origin guarded fallback ─────────────────────────────
    if channel_name:
        ch = channel_name.lower()
        if "shuffle" in ch:
            if "us" in ch:
                return "shuffle.us"
            return "shuffle.com"
        if "stake" in ch:
            if "us" in ch:
                return "stake.us"
            return "stake.com"
        for pid in ("goated", "degen", "rainbet", "thrill", "winna",
                    "gamba", "razed", "qzino"):
            if pid.replace(".", "") in ch:
                return pid

    # No match — never default to shuffle
    return None


def get_claim_url(platform_id: str, code: str) -> str:
    """Returns the direct claim URL for a platform, with code substituted."""
    for rule in PLATFORM_RULES:
        if rule["id"] == platform_id:
            return rule["claim_url"].replace("{code}", code)
    return ""


def get_claim_note(platform_id: str) -> Optional[str]:
    """Returns the optional claim helper note for a platform."""
    for rule in PLATFORM_RULES:
        if rule["id"] == platform_id:
            return rule.get("claim_note")
    return None


def platform_id_to_model_value(platform_id: str) -> str:
    """Maps a platform_id slug to the Platform enum value string."""
    _MAP = {
        "stake.us": "Stake.us",
        "stake.com": "Stake.com",
        "dual_stake": "Stake.us & Stake.com",
        "ambiguous_stake": "Stake.us & Stake.com (ambiguous)",
        "goated": "Goated",
        "degen": "Degen",
        "shuffle.us": "Shuffle.us",
        "shuffle.com": "Shuffle.com",
        "rainbet.us": "Rainbet",
        "rainbet": "Rainbet",
        "thrill.com": "THRILL",
        "winna": "WINNA",
        "gamba": "GAMBA",
        "razed": "Razed",
        "qzino": "Qzino",
    }
    return _MAP.get(platform_id, platform_id)
