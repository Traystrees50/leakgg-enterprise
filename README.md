# Leaked.GG Code Monitoring Bot

An enterprise-ready, multi-platform bonus code and low-wager drop monitoring engine branded to **Leaked.GG Code Monitoring**.

Monitors Telegram channels, StakeStats.net live database, CodeStats.gg, and premier affiliate review sources, dispatching real-time branded Discord embed alerts to platform-specific channels and providing rich interactive dashboard controls.

---

## 🌟 Key Features

- **Multi-Platform Support (24 Platforms + Dual Stake + VIP Notices)**:
  - 🎰 🇺🇸 **Stake.us** (`0xFEAA00` - Gold / Amber) • Signup: `https://www.stake.us/?c=selfmade`
  - 🎰 🌍 **Stake.com** (`0x1475E1` - Royal Blue) • Signup: `https://stake.com/?c=SELFMADE`
  - 👑 🇺🇸 **Stake.us - VIP Notices** (`0xFFB347` - Warm Amber) • Signup: `https://www.stake.us/?c=selfmade`
  - 👑 🌍 **Stake.com - VIP Notices** (`0xFF6B9D` - Soft Pink) • Signup: `https://stake.com/?c=SELFMADE`
  - 🔀 🇺🇸 **Shuffle.us** (`0x00B4D8` - Teal / Cyan) • Signup: `https://shuffle.us/?r=selfmade`
  - 🔀 🌍 **Shuffle.com** (`0x8A2BE2` - Purple / Violet) • Signup: `https://shuffle.com/?r=selfmade`
  - 🎲 🤖 **Qzino** (`0x10B981` - Emerald Green) • Signup: `https://qzino.ai/?r=SELFMADE`
  - 🌧️ ⚡ **Rainbet** (`0x3B82F6` - Electric Blue) • Signup: `https://rainbet.com/?r=smokerzsektion`
  - 🔥 ⚡ **Degen** (`0xEF4444` - Crimson Red) • Signup: `https://degen.com/r/selfmade`
  - 🐐 👑 **Goated** (`0xEC4899` - Magenta Pink) • Signup: `https://goated.com/?r=selfmade`
  - 💎 🇺🇸 **MYPRIZE.US** (`0x06B6D4` - Cyan) • Signup: `https://myprize.us/invite/Traystrees50`
  - 👑 🏆 **CrownCoins** (`0xEAB308` - Gold) • Signup: `https://crowncoinscasino.com/?utm_campaign=856db775-8290-42d7-93b4-76ddc67ddf4b&utm_source=friends`
  - 🎁 🎉 **RealPrize** (`0xEC4899` - Pink) • Signup: `https://www.realprize.com/refer/212990`
  - 🎰 🃏 **AceBet Casino** (`0xEF4444` - Red) • Signup: `https://acebet.cc/welcome/r/selfmade`
  - ⭐ 🤠 **LoneStar Casino** (`0xF97316` - Orange) • Signup: `https://lonestarcasino.com/refer/869128`
  - 🍀 🎲 **Chanced Casino** (`0x22C55E` - Green) • Signup: `https://chanced.com/c/v5a5yh`
  - 💎 🎰 **PULSZ** (`0x8B5CF6` - Purple) • Signup: `https://www.pulsz.com/?invited_by=ga1vnk`
  - 🎢 ⚡ **THRILL** (`0xEF4444` - Red) • Signup: `https://thrill.com/?r=selfmade`
  - 🎮 🪙 **MODO** (`0x3B82F6` - Blue) • Signup: `https://modo.us/?referralCode=Z901K9`
  - 🎰 🎪 **BABA** (`0x10B981` - Green) • Signup: `https://play.babacasino.com/#/?referral_id=5403a829ac9926527b94e7c068708e07&inv_referral=true&fb_source=invite`
  - 🍳 🇺🇸 **COOKED.US** (`0xF59E0B` - Amber) • Signup: `https://cooked.us/?auth=register&referral_source=SELFMADE`
  - 🍳 🌍 **COOKED.COM** (`0xF59E0B` - Amber) • Signup: `https://cooked.com/?auth=register&referral_source=SELFMADE`
  - 🌟 🎰 **WOWVEGAS** (`0x8B5CF6` - Violet) • Signup: `https://www.wowvegas.com/?raf=1274028`
  - 🎉 🎰 **YAYCASINO** (`0xEC4899` - Pink) • Signup: `https://www.yaycasino.com/signup/7ab97436-a07a-4514-9506-bcbbcd2495e8`
  - 🏆 🎁 **WINNA** (`0xFFD700` - Gold) • Signup: `https://winna.com/?bonus-center=true&SELFMADE`
  - 🎰 🌐 **Dual Stake (US & COM)** (`0x8B5CF6` - Dual Indigo)

- **Enterprise Interactive Dashboard (`/dashboard` & `!dashboard`)**:
  - Full Discord UI control panel with **Platform Multi-Select Dropdown** and **Action Dropdown**.
  - Configure **multiple channel IDs** and **multiple webhook URLs** (at least 2+ per platform).
  - Add/remove channels, add/remove webhooks via secure modals, fast-bind current channels, and dispatch instant test embeds.
  - Live toggles for Real-time background sweep daemon and interval adjustment.

- **Enterprise Health Monitor (`/dashboard` Health Button)**:
  - Live system diagnostic dashboard tracking Uptime, Process Memory RSS (MB), OS, and PID.
  - Real-time API & scraper health checks: StakeStats live API latency (ms), Telegram channels (8 active streams), CodeStats, and Web scrapers.
  - State database inspection (`seen_codes.json` size & tracked drops count) and route mapping verification.

- **Live Active Code Scanners (`/activecodes`)**:
  - Queries `https://stakestats.net/stake/tools/code` in real-time.
  - Displays organized lists of active codes for Stake.us and Stake.com with copyable code blocks, wager requirements, values, and one-click redeem links.
  - Highlights High Roller drops with `🔥 [HIGHROLLER]`.

- **100% Strict Case Preservation**:
  - All codes, URLs, and state keys preserve exact letter casing (`UIJXBQUS`, `stakeus...`, `mjp6axxg`).
  - Direct redeem URLs are generated with exact case query parameters.

- **Telegram Drop Channel Monitoring**:
  - **Stake.us**: `@highrollerscodeUS`, `@dailybonuscodeUS`, `t.me/codestats2`, and channel `1542279201`.
  - **Stake.com**: `@highrollerscode`, `@dailybonuscodes`, `t.me/codestats2`.
  - **Rainbet**: `@EddiesCodesRainbet` with dedicated drop format (Code, Redeem URL `https://rainbet.com/affiliates?modal=wallet&tab=redeem`, Reward, Wager, Claims).
  - **Degen**: `@degendotcom` with full image/media attachment previews.
  - **Shuffle**: `codestats2` for Shuffle.us and Shuffle.com drops.
  - **VIP Events**: Detects Stake.us `WEEKLY BOOST`, `MONTHLY BONUS`, and `VIP EVENTS` with complete text, links, and banners.
  - **Stake VIP Notices**: Dedicated platforms for Stake.com - VIP Notices and Stake.us - VIP Notices with independent routing, weekly bonus parsing, monthly bonus parsing, and complete event preservation.
  - **Private Telegram Sources**: Supports monitoring private Telegram groups/channels by chat ID (`-2922581483`, `-1542279201`) with optional Telethon API authentication for continuous monitoring.

- **Manual Bonus Code Submission (`!code`)**:
  - Submit any bonus code directly via Discord chat for instant validation and broadcast.
  - Auto-detects platform from code prefix or allows explicit platform specification.
  - Validates code quality, prevents duplicate submissions, and dispatches embeds to configured routes.

- **Dynamic Monitored Source Management (`/dashboard`)**:
  - Add or remove custom Telegram channels and Web Review URLs on-the-fly directly from the dashboard.
  - Web Review & Affiliate Sources are grouped by platform in the sources view.
  - Seamlessly routes custom Telegram feeds to target platforms or general monitoring.
  - Full source inventory overview displaying all active feeds, review URLs, and live poller endpoints.

- **Anti-Rate Limiting, Jitter & Proxy Pool Resilience**:
  - **Per-Domain Jitter Delays**: Randomized request intervals preventing burst patterns and robotic signatures.
  - **Browser Fingerprint & UA Rotation**: Dynamic rotation across modern Chrome, Firefox, Edge, and Safari user-agents with `sec-ch-ua` headers.
  - **Cloudflare Challenge Evasion**: Automated challenge detection with exponential backoff, stealth retry headers, and `Retry-After` honoring.
  - **Free Proxy Rotation Pool**: Dynamic discovery and rotation through verified public HTTP/HTTPS proxies with automatic dead proxy isolation.

- **Always-On Real-Time Monitoring**:
  - Automated continuous background sweep engine checking all monitored sources with anti-blocking resilience.
  - Real-time instant broadcast across all mapped multi-channel and multi-webhook routes with duplicate prevention.

---

## 🤖 Discord Slash & Prefix Commands

| Command | Access | Type | Description |
|---|---|---|---|
| `/subscribe` / `!subscribe` | 🌐 Public | Hybrid | Subscribe for $2 in crypto to unlock full premium dashboard access in any server. |
| `/activecodes` / `!activecodes` | 🌐 Public | Hybrid | Queries StakeStats.net live for active Stake.us & Stake.com drops with copyable codes and redeem links. |
| `/links` / `!links` | 🌐 Public | Hybrid | Displays all affiliate/signup links for every supported platform plus Discord and Kick. |
| `!code` | 🌐 Public | Prefix | Manually submit a bonus code for validation and broadcast. Usage: `!code <platform> <code>` or `!code <code>`. |
| `!post` | 🔒 Owner / Admin / Subscriber | Prefix | Manually broadcast a raw event/post to selected platform channels. Usage: `!post <platform> <message>`. |
| `/status` / `!status` | 🌐 Public | Hybrid | Displays real-time monitoring engine status, polling interval, and tracked drop statistics. |
| `/info` / `!info` | 🌐 Public | Hybrid | Displays bot overview, supported platforms, theme palette, and quick command overview. |
| `/commands` / `!commands` | 🌐 Public | Hybrid | Lists all currently available commands with descriptions and affiliate links. |
| `/help` / `!help` | 🌐 Public | Hybrid | Displays comprehensive bot guide, usage instructions, and platform registration links. |
| `/dashboard` / `!dashboard` | 🔒 Owner / Admin / Subscriber | Hybrid | Opens the interactive enterprise control panel with platform & action dropdown menus. |
| `/startmonitor` / `!startmonitor` | 🔒 Owner / Admin / Subscriber | Hybrid | Starts background real-time monitoring sweeps across all sources. |

> **Access Levels:**
> - 🌐 **Public** — Available to all users and server members.
> - 🔒 **Owner / Admin / Subscriber** — Restricted to the project owner (`traystrees50`), server administrators, users with an `@admin` role, and active $2 crypto subscribers.

---

## 🛠️ CLI Usage

| Command | Description |
|---|---|
| `python main.py run` | Starts the daemon background monitoring loop. |
| `python main.py health` | Runs the enterprise health monitor diagnostic check in CLI. |
| `python main.py poll-stakestats` | Real-time query against `stakestats.net` showing active US & COM drops. |
| `python main.py poll-telegram` | Scrapes all monitored Telegram drop channels. |
| `python main.py check-once` | Single scan across all sources (StakeStats, Telegram, CodeStats, Web). |
| `python main.py check-once --notify` | Single scan and dispatches Discord embeds. |
| `python main.py test-discord` | Sends test embeds for all platforms to verify formatting. |
| `python main.py test-channel` | Dispatches 4 recent test events for all platforms & sources to Discord channel 1460666123484794880. |
| `python main.py test-degen-qzino` | Live scans Degen and Qzino and dispatches 3 most recent events with images to channel 1460666123484794880. |
| `python main.py fetch-proxies` | Auto-discovers and populates working free proxies into the anti-rate-limit pool. |
| `python main.py bot` | Starts the Discord bot client with interactive slash commands. |
| `python main.py list-sources` | Displays breakdown of all monitored Telegram channels, web review feeds, and custom sources. |
| `python main.py add-source --type <type> --source <val> [--platform <plat>]` | Adds a custom Telegram channel or Web Review URL to monitor. |
| `python main.py remove-source --source <val>` | Removes a custom Telegram channel or Web Review URL from monitoring. |
| `python main.py list-seen` | Displays tracked bonus codes database. |
| `python main.py clear-history` | Clears code history state in `seen_codes.json`. |

---

## 🧪 Testing

Run the full unit test suite:

```bash
python test_bot.py
```
