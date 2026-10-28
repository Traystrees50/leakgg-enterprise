import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")


def _get_client():
    """Lazily create and cache the Supabase client."""
    global _client
    if _client is not None:
        return _client
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in the environment")
    try:
        from supabase import create_client, Client
        _client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        logger.debug("Supabase client initialized for drop history")
        return _client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        raise


_client = None


def record_drop(item_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Upsert a bonus code drop into drop_history.
    If (code, platform) already exists, increment sightings and update last_seen_at.
    Returns the row from drop_history, or None on failure.
    """
    try:
        client = _get_client()
        code = item_dict.get("code", "").strip()
        platform = item_dict.get("platform", "").strip()
        if not code or not platform:
            return None

        existing = client.table("drop_history").select("id, sightings") \
            .eq("code", code).eq("platform", platform).maybe_single().execute()

        if existing is not None:
            drop_id = existing.data["id"]
            new_sightings = (existing.data.get("sightings") or 1) + 1
            client.table("drop_history").update({
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "sightings": new_sightings,
                "amount_value": item_dict.get("amount_value"),
                "wager_requirement": item_dict.get("wager_requirement"),
                "claims_count": item_dict.get("claims_count"),
                "availability_status": item_dict.get("availability_status"),
            }).eq("id", drop_id).execute()
        else:
            row = {
                "code": code,
                "platform": platform,
                "source_name": item_dict.get("source_name"),
                "source_url": item_dict.get("source_url"),
                "amount_value": item_dict.get("amount_value"),
                "wager_requirement": item_dict.get("wager_requirement"),
                "claims_count": item_dict.get("claims_count"),
                "availability_status": item_dict.get("availability_status"),
                "event_type": item_dict.get("event_type"),
                "is_affiliate": item_dict.get("is_affiliate", False),
                "is_highroller": item_dict.get("is_highroller", False),
                "is_dual_stake": item_dict.get("is_dual_stake", False),
                "currency": item_dict.get("currency"),
                "image_url": item_dict.get("image_url"),
            }
            result = client.table("drop_history").insert(row).execute()
            if not result.data:
                return None
            drop_id = result.data[0]["id"]

        _record_sighting(drop_id, item_dict.get("source_name"), item_dict.get("source_url"))
        return {"id": drop_id, "code": code, "platform": platform}
    except Exception as e:
        logger.error(f"Failed to record drop to Supabase: {e}")
        return None


def _record_sighting(drop_id: str, source_name: Optional[str], source_url: Optional[str]) -> None:
    try:
        client = _get_client()
        client.table("drop_sightings").insert({
            "drop_id": drop_id,
            "source_name": source_name,
            "source_url": source_url,
        }).execute()
    except Exception as e:
        logger.debug(f"Failed to record sighting: {e}")


def is_code_seen(code: str, platform: str) -> bool:
    """Check if a code+platform combo already exists in drop_history."""
    try:
        client = _get_client()
        result = client.table("drop_history").select("id") \
            .eq("code", code.strip()).eq("platform", platform.strip()).maybe_single().execute()
        return result is not None
    except Exception as e:
        logger.debug(f"is_code_seen query failed: {e}")
        return False


def get_recent_history(limit: int = 25) -> List[Dict[str, Any]]:
    """Return the most recently seen drops, newest first."""
    try:
        client = _get_client()
        result = client.table("drop_history") \
            .select("code, platform, amount_value, source_name, first_seen_at, last_seen_at, sightings, availability_status, event_type") \
            .order("last_seen_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to fetch drop history: {e}")
        return []


def get_stats() -> Dict[str, Any]:
    """
    Generate analytics: total drops, per-platform counts, per-source leaderboard,
    hourly heatmap, and daily volume for the last 7 days.
    """
    try:
        client = _get_client()
        all_drops = client.table("drop_history") \
            .select("platform, source_name, first_seen_at, sightings").execute()
        rows = all_drops.data or []

        total = len(rows)
        by_platform: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        hourly_heatmap: Dict[str, int] = {}
        for r in rows:
            p = r.get("platform", "Unknown")
            by_platform[p] = by_platform.get(p, 0) + 1
            s = r.get("source_name", "Unknown")
            by_source[s] = by_source.get(s, 0) + 1
            ts = r.get("first_seen_at")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    hour_key = dt.strftime("%H:00")
                    hourly_heatmap[hour_key] = hourly_heatmap.get(hour_key, 0) + 1
                except Exception:
                    pass

        source_leaderboard = sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:10]
        platform_leaderboard = sorted(by_platform.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_drops": total,
            "platform_breakdown": platform_leaderboard,
            "source_leaderboard": source_leaderboard,
            "hourly_heatmap": dict(sorted(hourly_heatmap.items())),
        }
    except Exception as e:
        logger.error(f"Failed to generate stats: {e}")
        return {"total_drops": 0, "platform_breakdown": [], "source_leaderboard": [], "hourly_heatmap": {}}


def update_availability_status(code: str, platform: str, status: str) -> bool:
    """Update the availability_status for a code after GraphQL validation."""
    try:
        client = _get_client()
        client.table("drop_history").update({"availability_status": status}) \
            .eq("code", code.strip()).eq("platform", platform.strip()).execute()
        return True
    except Exception as e:
        logger.debug(f"Failed to update availability status: {e}")
        return False
