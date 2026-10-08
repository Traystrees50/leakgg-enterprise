import logging
import time
from typing import Optional, Dict, Any
import requests

from models import Platform

logger = logging.getLogger(__name__)

_STAKE_US_GRAPHQL = "https://stake.us/_api/graphql"
_STAKE_COM_GRAPHQL = "https://stake.com/graphql"

_VALIDATOR_QUERY = """
query BonusCodeInformation($code: String!, $couponType: CouponType!) {
  bonusCodeInformation(code: $code, couponType: $couponType) {
    availabilityStatus
    bonusValue
    cryptoMultiplier
  }
}
"""

_COUPON_TYPE_MAP = {
    Platform.STAKE_US: "drop",
    Platform.STAKE_COM: "drop",
    Platform.STAKE_US_VIP_NOTICES: "vip",
    Platform.STAKE_COM_VIP_NOTICES: "vip",
    Platform.DUAL_STAKE: "drop",
}

_PLATFORM_ENDPOINT_MAP = {
    Platform.STAKE_US: _STAKE_US_GRAPHQL,
    Platform.STAKE_COM: _STAKE_COM_GRAPHQL,
    Platform.STAKE_US_VIP_NOTICES: _STAKE_US_GRAPHQL,
    Platform.STAKE_COM_VIP_NOTICES: _STAKE_COM_GRAPHQL,
    Platform.DUAL_STAKE: _STAKE_US_GRAPHQL,
}

_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


class StakeCodeValidator:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self._last_request_ts = 0.0

    def _respect_rate_limit(self) -> None:
        min_interval = 1.0
        now = time.monotonic()
        delta = now - self._last_request_ts
        if delta < min_interval:
            time.sleep(min_interval - delta)
        self._last_request_ts = time.monotonic()

    def validate(self, code: str, platform: Platform) -> Dict[str, Any]:
        clean_code = code.strip()
        endpoint = _PLATFORM_ENDPOINT_MAP.get(platform)
        coupon_type = _COUPON_TYPE_MAP.get(platform, "drop")

        if not endpoint:
            return {
                "status": "UNKNOWN",
                "raw": None,
                "platform": platform.value,
                "code": clean_code,
                "reason": "No validator endpoint configured for platform",
            }

        payload = {
            "query": _VALIDATOR_QUERY,
            "variables": {"code": clean_code, "couponType": coupon_type},
            "operationName": "BonusCodeInformation",
        }

        try:
            self._respect_rate_limit()
            response = requests.post(endpoint, json=payload, headers=_HEADERS, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            logger.debug(f"Stake GraphQL validator request failed for {platform.value}: {exc}")
            return {
                "status": "UNKNOWN",
                "raw": None,
                "platform": platform.value,
                "code": clean_code,
                "reason": f"Request failed: {exc}",
            }
        except Exception as exc:
            logger.debug(f"Stake GraphQL validator parse failed for {platform.value}: {exc}")
            return {
                "status": "UNKNOWN",
                "raw": None,
                "platform": platform.value,
                "code": clean_code,
                "reason": f"Parse failed: {exc}",
            }

        bonus_info = None
        if data is not None and isinstance(data, dict):
            data_block = data.get("data") or {}
            if isinstance(data_block, dict):
                bonus_info = data_block.get("bonusCodeInformation")

        if not bonus_info:
            errors = data.get("errors") if isinstance(data, dict) else None
            reason = "No bonusCodeInformation returned"
            if errors:
                reason = f"GraphQL errors: {errors}"
            return {
                "status": "UNKNOWN",
                "raw": data,
                "platform": platform.value,
                "code": clean_code,
                "reason": reason,
            }

        raw_status = bonus_info.get("availabilityStatus")
        status = self._normalize_status(raw_status)
        return {
            "status": status,
            "raw": bonus_info,
            "platform": platform.value,
            "code": clean_code,
            "bonusValue": bonus_info.get("bonusValue"),
            "cryptoMultiplier": bonus_info.get("cryptoMultiplier"),
            "reason": None if status != "UNKNOWN" else f"Unexpected availabilityStatus: {raw_status}",
        }

    @staticmethod
    def _normalize_status(raw_status: Optional[str]) -> str:
        if not raw_status:
            return "UNKNOWN"
        upper = str(raw_status).upper()
        if upper in {"VALID", "AVAILABLE", "ACTIVE", "OPEN"}:
            return "AVAILABLE"
        if upper in {"CLAIMED", "FULLY_CLAIMED", "SOLD_OUT", "EXHAUSTED"}:
            return "FULLY_CLAIMED"
        if upper in {"EXPIRED", "INACTIVE", "INVALID"}:
            return "EXPIRED"
        return "UNKNOWN"


validator = StakeCodeValidator()
