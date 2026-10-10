import os
import re
import time
import random
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib.parse

logger = logging.getLogger(__name__)

from config import ENABLE_JITTER, ENABLE_PROXY_ROTATION, MIN_JITTER_DELAY, MAX_JITTER_DELAY

# Modern browser User-Agents for rotation
BROWSER_USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
]

class UserAgentRotator:
    """
    Generates realistic, browser-matched HTTP headers and rotates User-Agents.
    """
    @staticmethod
    def get_random_ua() -> str:
        return random.choice(BROWSER_USER_AGENTS)

    @staticmethod
    def generate_headers(custom_ua: Optional[str] = None, referer: Optional[str] = None) -> Dict[str, str]:
        ua = custom_ua or UserAgentRotator.get_random_ua()
        is_chrome = "Chrome" in ua and "Edg" not in ua
        is_edge = "Edg" in ua
        is_firefox = "Firefox" in ua
        is_mac = "Macintosh" in ua

        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site" if referer else "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

        if referer:
            headers["Referer"] = referer

        if is_chrome or is_edge:
            brand = '"Chromium";v="125", "Google Chrome";v="125", "Not.A/Brand";v="24"'
            if is_edge:
                brand = '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"'
            headers["sec-ch-ua"] = brand
            headers["sec-ch-ua-mobile"] = "?0"
            headers["sec-ch-ua-platform"] = '"macOS"' if is_mac else '"Windows"'

        return headers


class JitterManager:
    """
    Applies per-domain rate limiting, randomized jitter delays, and exponential backoff.
    """
    def __init__(self, default_min_delay: float = 0.8, default_max_delay: float = 2.2):
        self.default_min_delay = default_min_delay
        self.default_max_delay = default_max_delay
        self.last_request_times: Dict[str, float] = {}
        self.lock = threading.Lock()

    def get_domain(self, url: str) -> str:
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.netloc.lower() or "default"
        except Exception:
            return "default"

    def apply_jitter(self, url: str, min_delay: Optional[float] = None, max_delay: Optional[float] = None) -> float:
        """
        Calculates and sleeps for a randomized jitter delay to prevent bursting against target domains.
        """
        domain = self.get_domain(url)
        min_d = min_delay if min_delay is not None else self.default_min_delay
        max_d = max_delay if max_delay is not None else self.default_max_delay
        if max_d < min_d:
            max_d = min_d + 0.5

        target_delay = random.uniform(min_d, max_d)

        with self.lock:
            now = time.time()
            last_time = self.last_request_times.get(domain, 0.0)
            elapsed = now - last_time
            needed_sleep = max(0.0, target_delay - elapsed)
            self.last_request_times[domain] = now + needed_sleep

        if needed_sleep > 0:
            time.sleep(needed_sleep)

        return needed_sleep

    def calculate_backoff(self, attempt: int, base_seconds: float = 2.0, max_backoff: float = 30.0, retry_after: Optional[int] = None) -> float:
        """
        Computes exponential backoff with randomized jitter on rate limit or connection errors.
        """
        if retry_after and retry_after > 0:
            delay = float(retry_after) + random.uniform(0.5, 2.0)
            return min(max_backoff, delay)

        # Exponential backoff: base * 2^attempt + jitter
        exp_delay = base_seconds * (2 ** max(0, attempt - 1))
        jitter = random.uniform(0.5, 2.0)
        total_delay = min(max_backoff, exp_delay + jitter)
        return total_delay


class ProxyPool:
    """
    Manages a dynamic pool of working HTTP/HTTPS proxies with health tracking and automatic rotation.
    Supports user-defined proxy lists (.env PROXY_LIST) and public free proxy auto-discovery.
    """
    def __init__(self, enabled: bool = True, custom_proxies: Optional[List[str]] = None, load_env_proxies: bool = True):
        self.enabled = enabled
        self.proxies: List[str] = []
        self.failed_proxies: Dict[str, int] = {}
        self.current_index = 0
        self.lock = threading.Lock()
        self.last_discovery_time = 0.0
        self.discovery_interval = 1800.0  # refresh free proxies every 30 minutes

        if custom_proxies:
            self.proxies.extend([p.strip() for p in custom_proxies if p.strip()])

        # Load from env var if present and not already loaded from custom_proxies
        if load_env_proxies:
            env_proxies = os.getenv("PROXY_LIST", "")
            if env_proxies:
                for p in env_proxies.split(","):
                    if p.strip() and p.strip() not in self.proxies:
                        self.proxies.append(p.strip())

    def get_proxy(self) -> Optional[Dict[str, str]]:
        """
        Returns the next active proxy in the rotation pool, formatted for requests.
        """
        if not self.enabled:
            return None

        with self.lock:
            active_proxies = [p for p in self.proxies if self.failed_proxies.get(p, 0) < 3]
            if not active_proxies:
                return None

            self.current_index = (self.current_index + 1) % len(active_proxies)
            proxy_url = active_proxies[self.current_index]

            if not proxy_url.startswith("http://") and not proxy_url.startswith("https://") and not proxy_url.startswith("socks"):
                proxy_url = f"http://{proxy_url}"

            return {
                "http": proxy_url,
                "https": proxy_url
            }

    def report_failure(self, proxy_dict: Optional[Dict[str, str]]):
        """
        Marks a proxy as failed. Disables proxy if failures exceed threshold.
        """
        if not proxy_dict:
            return
        proxy_url = proxy_dict.get("http") or proxy_dict.get("https")
        if not proxy_url:
            return

        with self.lock:
            # strip scheme for tracking
            clean_proxy = proxy_url.replace("http://", "").replace("https://", "")
            self.failed_proxies[clean_proxy] = self.failed_proxies.get(clean_proxy, 0) + 1
            logger.debug(f"Proxy failure recorded for {clean_proxy} (fail count: {self.failed_proxies[clean_proxy]})")

    def report_success(self, proxy_dict: Optional[Dict[str, str]]):
        """
        Resets failure count on successful request.
        """
        if not proxy_dict:
            return
        proxy_url = proxy_dict.get("http") or proxy_dict.get("https")
        if not proxy_url:
            return

        with self.lock:
            clean_proxy = proxy_url.replace("http://", "").replace("https://", "")
            if clean_proxy in self.failed_proxies:
                self.failed_proxies[clean_proxy] = 0

    def failed_all(self) -> bool:
        """Returns True if all proxies in the pool have exceeded the failure threshold."""
        with self.lock:
            active = [p for p in self.proxies if self.failed_proxies.get(p, 0) < 3]
            return len(self.proxies) > 0 and len(active) == 0

    def add_proxies(self, proxy_list: List[str]):
        with self.lock:
            for p in proxy_list:
                p_clean = p.strip()
                if p_clean and p_clean not in self.proxies:
                    self.proxies.append(p_clean)

    def fetch_free_proxies(self, max_proxies: int = 20) -> int:
        """
        Discovers and adds working public free proxies from open mirrors.
        """
        sources = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=yes&anonymity=elite",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
        ]
        discovered = []
        for src in sources:
            try:
                resp = requests.get(src, timeout=5)
                if resp.status_code == 200:
                    lines = resp.text.splitlines()
                    for line in lines:
                        candidate = line.strip()
                        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}$", candidate):
                            discovered.append(candidate)
                            if len(discovered) >= max_proxies:
                                break
                if len(discovered) >= max_proxies:
                    break
            except Exception as e:
                logger.debug(f"Free proxy mirror {src} not reachable: {e}")

        if discovered:
            self.add_proxies(discovered)
            logger.info(f"Loaded {len(discovered)} public free proxies into rotation pool.")
        return len(discovered)


class CloudflareDetector:
    """
    Detects Cloudflare challenges, anti-bot screens, and rate limits.
    """
    @staticmethod
    def is_cloudflare_challenge(status_code: int, headers: Dict[str, str], body_text: str) -> bool:
        if status_code in (403, 503, 429):
            if any(h in headers for h in ["cf-ray", "cf-mitigated", "cf-chl-bypass"]):
                return True
            b_lower = body_text.lower()
            if any(marker in b_lower for marker in [
                "just a moment...",
                "attention required! | cloudflare",
                "cf-browser-verification",
                "challenges.cloudflare.com",
                "turnstile",
                "please enable javascript",
                "checking your browser before accessing"
            ]):
                return True
        return False

    @staticmethod
    def is_rate_limited(status_code: int, body_text: str = "") -> bool:
        if status_code == 429:
            return True
        if status_code in (403, 503) and ("rate limit" in body_text.lower() or "too many requests" in body_text.lower()):
            return True
        return False

    @staticmethod
    def get_retry_after(headers: Dict[str, str]) -> Optional[int]:
        val = headers.get("Retry-After") or headers.get("retry-after")
        if val:
            try:
                return int(val)
            except Exception:
                pass
        return None


class ResilientSession:
    """
    Enterprise resilient HTTP session wrapper with:
    - User-Agent and browser fingerprint rotation
    - Per-domain rate limit protection and randomized jitter
    - Exponential backoff with jitter on 429 / 403 / 503 / connection errors
    - Automatic Cloudflare challenge detection and stealth header retry
    - Optional proxy rotation with automatic failure reporting
    """
    def __init__(
        self,
        timeout: int = 15,
        max_retries: int = 1,
        enable_jitter: bool = True,
        enable_proxy_rotation: bool = False,
        proxy_pool: Optional[ProxyPool] = None
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.enable_jitter = enable_jitter
        self.jitter_manager = JitterManager(default_min_delay=MIN_JITTER_DELAY, default_max_delay=MAX_JITTER_DELAY)
        self.proxy_pool = proxy_pool or ProxyPool(enabled=enable_proxy_rotation)
        
        self.session = requests.Session()
        # Clear any inherited environment proxies to prevent unintended routing
        self.session.trust_env = False
        retry_strategy = Retry(
            total=0,
            backoff_factor=0,
            status_forcelist=[500, 502, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        use_proxy: bool = True,
        referer: Optional[str] = None,
        **kwargs
    ) -> Optional[requests.Response]:
        """
        Executes an HTTP request with jitter, rotating headers, Cloudflare evasion, and retry backoff.
        Falls back to direct connection (no proxy) if proxy connections consistently fail.
        """
        req_timeout = timeout or self.timeout
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            # 1. Apply intelligent jitter before request
            if self.enable_jitter:
                self.jitter_manager.apply_jitter(url)

            # 2. Generate browser-realistic headers with UA rotation
            req_headers = UserAgentRotator.generate_headers(referer=referer)
            if headers:
                req_headers.update(headers)

            # 3. Get proxy if enabled; on retries after failure, fall back to direct
            proxy_dict = None
            if use_proxy and self.proxy_pool.enabled:
                if self.proxy_pool.failed_all():
                    if attempt == 1:
                        logger.warning(f"All proxies exhausted for {url}, falling back to direct connection.")
                else:
                    proxy_dict = self.proxy_pool.get_proxy()

            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    headers=req_headers,
                    timeout=req_timeout,
                    proxies=proxy_dict,
                    **kwargs
                )

                # Check for Cloudflare challenge or rate limit
                headers_map = {k.lower(): v for k, v in resp.headers.items()}
                is_cf = CloudflareDetector.is_cloudflare_challenge(resp.status_code, headers_map, resp.text)
                is_rl = CloudflareDetector.is_rate_limited(resp.status_code, resp.text)

                if is_cf or is_rl:
                    retry_after = CloudflareDetector.get_retry_after(resp.headers)
                    backoff = self.jitter_manager.calculate_backoff(attempt, retry_after=retry_after)
                    logger.warning(
                        f"Rate limit / Cloudflare protection detected on {url} (HTTP {resp.status_code}). "
                        f"Backing off for {backoff:.1f}s (Attempt {attempt}/{self.max_retries})."
                    )
                    if proxy_dict:
                        self.proxy_pool.report_failure(proxy_dict)
                    time.sleep(backoff)
                    continue

                # Successful or non-blocked response
                if proxy_dict:
                    self.proxy_pool.report_success(proxy_dict)
                return resp

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
                last_error = e
                if proxy_dict:
                    self.proxy_pool.report_failure(proxy_dict)

                backoff = self.jitter_manager.calculate_backoff(attempt)
                logger.warning(
                    f"Network error on {url}: {e}. Retrying in {backoff:.1f}s (Attempt {attempt}/{self.max_retries})."
                )
                time.sleep(backoff)

        # Final fallback: try without any proxy
        if last_error and "proxy" in str(last_error).lower():
            logger.warning(f"Proxy-based requests failed for {url}, attempting direct connection.")
            try:
                if self.enable_jitter:
                    self.jitter_manager.apply_jitter(url)
                req_headers = UserAgentRotator.generate_headers(referer=referer)
                if headers:
                    req_headers.update(headers)
                resp = self.session.request(
                    method=method,
                    url=url,
                    headers=req_headers,
                    timeout=req_timeout,
                    proxies=None,
                    **kwargs
                )
                return resp
            except Exception as direct_error:
                logger.error(f"Direct connection also failed for {url}: {direct_error}")

        logger.error(f"Failed to fetch {url} after {self.max_retries} attempts: {last_error}")
        return None

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Optional[requests.Response]:
        return self.request("POST", url, **kwargs)

    def fetch_text(self, url: str, **kwargs) -> Optional[str]:
        resp = self.get(url, **kwargs)
        if resp and resp.status_code == 200:
            return resp.text
        return None

    def fetch_json(self, url: str, **kwargs) -> Optional[Any]:
        resp = self.get(url, **kwargs)
        if resp and resp.status_code == 200:
            try:
                return resp.json()
            except Exception as e:
                logger.debug(f"JSON decode failed for {url}: {e}")
        return None


# Global Shared Singleton Instance
_global_network_manager: Optional[ResilientSession] = None

def get_resilient_session() -> ResilientSession:
    global _global_network_manager
    if _global_network_manager is None:
        _global_network_manager = ResilientSession(enable_proxy_rotation=ENABLE_PROXY_ROTATION)
    return _global_network_manager
