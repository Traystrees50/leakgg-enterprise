# Original Sources — Complete Bonus Code History and Regex
## For leakgg-enterprise / Leaked.GG bot — add to project
**Repo:** https://github.com/Traystrees50/leakgg-enterprise.git
**Server:** CTRL ALT DEGEN (Ctrl Alt Delete), Discord server ID `1412350608786325536`
**Collected:** Nov 26, 2026, 4:39–4:43 PM EST (history) and 4:48–4:53 PM EST (original sources)
**Collection only — no code was redeemed, no casino was logged into, no Claim/Redeem/Copy button was used. Discord left signed in as A PURPLE BAG / naughtynelson09.**

This file supersedes the earlier history file for original-source purposes. The earlier file
`Bonus-Code-History-and-Platform-Regex.md` still holds the full 135-code tables; this file adds
the original-source layer, the wrong-platform / duplicate findings, and the corrected regex
your bot needs. Do not invent a per-code original source where none is stated — see §1.

---

## 1. Headline finding — read this first

**Only #low-wager-codes states an original source, and only as a site name.**
Every other CodeStats embed has NO Source field, no submitter name, no "via" note, and no
Telegram handle.

- #stake-codes BONUS DROP and USER SUBMITTED: no Source, no submitter, no via.
- #rainbet-us-codes: only a footer handle, @rainbetuscodes / @rainbetusvip. No Source label.
- #shuffle-codes, #gamba-codes, #thrill-codes, #razed-codes: no Source at all.
- #low-wager-codes: every embed has `Source: [name]` — site name only, never a URL or handle.

CodeStats.gg's own FAQ is the only place that names upstream sources in general terms.
Paraphrased: codes are monitored around the clock from its CodeStats Telegram channel,
the official Stake and Shuffle drop channels on Telegram, social media like X and Instagram,
other bonus-code sites it watches, and direct community submissions. The site does NOT name
which of those sources any individual code came from.

So for most codes, the honest `original_source` value is:
`CodeStats.gg feed — no per-code origin stated`
with `original_source_type = "codestats_feed"`, NOT a guessed affiliate site or Telegram channel.
For low-wager codes, `original_source` is the Source-line site name, with the URL mapped
from your repo (see §3) — the URL was NOT in the Discord embed.

## 2. Per-channel original-source table

| Discord channel | App / poster | Embed footer | Original source in embed | Source type | URL / handle in embed |
|---|---|---|---|---|---|
| #stake-codes — https://discord.com/channels/1412350608786325536/1423549369365565470 | CodeStats (BONUS DROP) / Code Stats (USER SUBMITTED) | `codestats.gg/autoclaimer • [date/time]` (Bonus Drop) / `CodeStats.gg • [date/time]` (User Submitted) | NONE STATED | none stated | none |
| #low-wager-codes — https://discord.com/channels/1412350608786325536/1530999347284803605 | Low Wager Code Bot | `codestats.gg/autoclaimer • [date/time]` | `Source: [site name]` — see §3 | affiliate review site, site name only | none in embed |
| #rainbet-us-codes — https://discord.com/channels/1412350608786325536/1569023258769105096 | Code Stats - Rainbet.US Edition | `CodeStats.gg • Rainbet.US • @rainbetuscodes` (regular) / `CodeStats.gg • Rainbet.US • @rainbetusvip` (VIP) | No Source label; footer handle only | footer handle only | @rainbetuscodes / @rainbetusvip, no URL for the handle. Affiliate link in embed: `Claim more codes at Rainbet.US` http://rainbet.us/?r=codestats |
| #shuffle-codes — https://discord.com/channels/1412350608786325536/1423549817480679494 | CodeStats - Shuffle Edition / CodeStats - Shuffle.US Edition | `codestats.gg/autoclaimer • [date/time]` | NONE STATED | none stated | Claim links only: https://shuffle.com/?modal=c&md-code=[code] / https://shuffle.us/?modal=c&md-code=[code] |
| #gamba-codes — https://discord.com/channels/1412350608786325536/1423549684957450240 | CodeStats - Gamba Edition, role @🎰 Gamba.com | `CodeStats.gg • [date/time]` | NONE STATED | none stated | none. STALE: latest code Nov 10, 2026, 3:32 AM; nothing Nov 11–26. Codes are emoji-obfuscated, embed says "Remove the 🤑 to claim it". Embeds also carry Gamba.com announcements (e.g. "Monthly out now", "Points shop + community…"). |
| #thrill-codes — https://discord.com/channels/1412350608786325536/1433292762673053811 | Code Stats - Thrill Edition, role @Thrill.com | `CodeStats.gg • [date/time]` | NONE STATED | none stated | Join link: https://thrill.com/?r=CODESTATS |
| #razed-codes — https://discord.com/channels/1412350608786325536/1541607173426118766 | Code Stats - Razed Edition | `CodeStats.gg • [date/time]` | NONE STATED | none stated | Sign-up link: https://www.razed.com/signup/?raf=dyzzastertime . STALE: latest Nov 8, 2026. Nov 8, 6:20 AM "DOUBLE CODE DROP" notice: "We will drop one more code in our Discord server! Join now! discord.gg/razed" — the only pointer to an original drop venue in this channel. |
| #submit-stake-code — https://discord.com/channels/1412350608786325536/1466711376406773912 | — | — | Topic only, no source statement | submission channel | Topic verbatim: "Stake.com and Stake.us Bonus Code Submission Channel! Accepts single word bonus codes [ stakecom15a5d55 ], as well as ALL code links including non-standard obfuscated ones. 😉" — this explains USER SUBMITTED codes: users post codes there; the bot re-posts them to #stake-codes with no submitter attribution preserved. History not viewable by this user. |

Other code channels showed no topic in the header.

### Public web sources checked Nov 26, ~4:52 PM EST

**https://codestats.gg**
- Home: "Real money bonus codes from the community, auto-validated and pushed straight to our claim tools"
- "Active Stake Codes 18" at ~4:52 PM, "Recent Drops — Shared by the CodeStats.gg community"
- Stats: 302 codes last 7 days, $1,988.15 value tracked, 83 users online; history page keeps last 36 hours
- https://codestats.gg/recent ("Recent Drops 40", last 24 hours) has filters Stake.com, Stake.us, Shuffle.com, Shuffle.us, Thrill, User Submitted, All Codes
- No per-code source channel or Telegram channel is listed — only a category label (platform or USER SUBMITTED), a droppedAt timestamp (e.g. "11/26/2026, 4:34:47 PM"), value, and Claim/US/Com links. No status field per code beyond Active vs Recent Drops.
- Join Telegram Channel: https://t.me/codestats2 (@codestats2). Join Discord link is the CTRL+ALT+DEGEN server.

**https://stakestats.net/stake/tools/code**
- "Active Bonus Codes — Fresh Stake drop codes with values, wager requirements, drop times, and one-click redemption."
- Stake.us: ACTIVE 16, 72H DROPS 51, HIGH ROLLER 17, LATEST 1h ago, 16 codes, Total Value $219.50
- Stake.com: ACTIVE 2, 72H DROPS 51, HIGH ROLLER 17, LATEST 2h ago, 2 codes, Total Value $4 — stakepyq6arvne0ogq6m0 ($1, Dropped Nov 26, 2:52 PM, Wager $4,000, STANDARD) and bonusbuyspins ($3, Nov 21, 9:22 AM, Wager $9,579, STANDARD)
- Lists the same Stake codes as CodeStats Active (same drop times, values, wagers), with a Dropped time, Value, Wager and STANDARD/HIGH ROLLER badge per code. No source field, no status beyond the Active list, and no Shuffle, Thrill, Rainbet, Gamba, Razed or low-wager codes. Owned by Casino Stats, LLC, "not directly affiliated with Stake.com".

---

## 3. #low-wager-codes — original Source line for every code, Nov 21–26

Format in every embed: `Source: [name]` — site name only, never a URL or Telegram handle.
Footer in all: `codestats.gg/autoclaimer`.
**Original-source URL mapping below is from the leakgg-enterprise repo
(`config.py TARGET_SOURCES` and `scrapers/sources.py` known_site_codes), NOT from the
Discord embed. Where the repo has no URL for that source, it is marked "no URL in repo".**

| Code | Platform | Date/time EST | Amount | Original Source (embed) | Original source URL (repo mapping) |
|---|---|---|---|---|---|
| SPORTSGRdrop435k | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo — source name only |
| SPORTSGRboost34596 | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo |
| SPORTS7749GRID53 | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo |
| SG583hgjity7453 | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo |
| SGRID558LGO957 | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo |
| SPORTSGR8438vip9 | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo |
| SGRID943reward9358 | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo |
| SPORTSGR9395jgiu4 | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo |
| SG5492bonus39053 | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo |
| SGRID5gjfdrop53s4 | Stake.us | Nov 21, 7:13 PM | not stated | SportsGrid | no URL in repo |
| BILFBC9KKP | Stake.us | Nov 22, 7:32 AM | $000 | Ballislife | https://www.ballislife.com/betting/reviews/stake-us/bonus-drops/ |
| ThanksgivingGold | Stake.com | Nov 23, 2:41 AM | not stated | FreeTips | no URL in repo — source name only |
| BILHX8K2H3 | Stake.us | Nov 23, 6:46 AM | $000 | Ballislife | https://www.ballislife.com/betting/reviews/stake-us/bonus-drops/ |
| CHAMP994X2086 | Stake.us | Nov 23, 8:52 AM | $125.00 | GameChampions US | https://www.gamechampions.com/en/reviews/stake-us/bonus-drop-codes/ |
| CHAMPK6R41082 | Stake.us | Nov 23, 8:52 AM | $125.00 | GameChampions US | https://www.gamechampions.com/en/reviews/stake-us/bonus-drop-codes/ |
| CHAMP409L7263 | Stake.com | Nov 23, 8:53 AM | not stated | GameChampions | https://www.gamechampions.com/en/reviews/stake-com/bonus-drop-codes/ |
| CHAMPQ5T28416 | Stake.com | Nov 23, 8:53 AM | not stated | GameChampions | https://www.gamechampions.com/en/reviews/stake-com/bonus-drop-codes/ |
| BILHYC9BWF | Stake.us | Nov 24, 6:37 AM | $000 | Ballislife | https://www.ballislife.com/betting/reviews/stake-us/bonus-drops/ |
| ESBCOM158ELITERUSH6 | Stake.com | Nov 24, 8:30 AM | $5 | EsportsBetting COM | no URL in repo — source name only |
| ESBUS158ELITERUSH6 | Stake.us | Nov 24, 8:30 AM | $5 | EsportsBetting | no URL in repo |
| BILJ3Z3WKF | Stake.us | Nov 25, 4:45 AM | $000 | Ballislife | https://www.ballislife.com/betting/reviews/stake-us/bonus-drops/ |
| CHAMP3N8P7254 | Stake.us | Nov 25, 7:24 AM | $125.00 | GameChampions US | https://www.gamechampions.com/en/reviews/stake-us/bonus-drop-codes/ |
| CHAMPM3X91852 | Stake.com | Nov 25, 7:25 AM | not stated | GameChampions | https://www.gamechampions.com/en/reviews/stake-com/bonus-drop-codes/ |
| BILJG8TF6H | Stake.us | Nov 26, 4:45 AM | $000 | Ballislife | https://www.ballislife.com/betting/reviews/stake-us/bonus-drops/ |
| DIMERSUPFND2IL88 | Stake.us | Nov 26, 3:55–3:56 PM | $5 | Dimers | dimers.com (repo known_site_codes; no full bonus-drop URL in repo) |
| DIMERSDFV801PFFQ | Stake.us | Nov 26, 3:55–3:56 PM | $5 | Dimers | dimers.com |
| DIMERSBG6NW7SPKA | Stake.us | Nov 26, 3:55–3:56 PM | $5 | Dimers | dimers.com |
| DIMERSRRBEWW87XL | Stake.us | Nov 26, 3:55–3:56 PM | $5 | Dimers | dimers.com |
| DIMERSPMFTHX43LN | Stake.us | Nov 26, 3:55–3:56 PM | $5 | Dimers | dimers.com |
| DIMERSFZX9U7C671 | Stake.us | Nov 26, 3:55–3:56 PM | $5 | Dimers | dimers.com |
| DIMERSRD7S2F003F | Stake.us | Nov 26, 3:55–3:56 PM | $5 | Dimers | dimers.com |
| DIMERSJ30JX5P675 | Stake.us | Nov 26, 3:55–3:56 PM | $5 | Dimers | dimers.com |

Other original affiliate sources in the repo that did NOT appear in this Nov 21–26 low-wager window, but are in `TARGET_SOURCES` / `known_site_codes` and should stay in the source map: TheLines (thelines.com), VegasInsider (vegasinsider.com), Wetten (wetten.com), TheGruelingTruth (thegruelingtruth.com), PromoGuy / PROMOBOY (promoguy.us), Jaxon (jaxon.gg), TheSpike.gg, Strafe / STFSOCIAL, Deadspin (deadspin.com), NEXT.io (next.io), TheGameHaus (thegamehaus.com).

**Repo Telegram originals (from `config.py TELEGRAM_CHANNELS`):**
Stake.us: @highrollerscodeUS, @dailybonuscodeUS, @codestats2, @stakeusdrops, @stakeusbonus, @stakecodesus
Stake.com: @highrollerscode, @dailybonuscodes, @codestats2, @stakecomdrops, @stakecombonus, @stakecodescom
Rainbet: @EddiesCodesRainbet, @rainbetcodes, @rainbetdrops, @rainbetbonus, @rainbetofficial
Rainbet.us: @rainbetus, @rainbetuscodes, @rainbetusdrops
Shuffle: @anyclaimershuffle, @codestats2, @shufflecodes, @shuffledrops, @shuffleuscodes
Thrill: @thrillcodes, @thrilldrops, @thrillbonus, @thrillofficial
Winna: @EddiesCodesWinna, @winnacodes, @winnadrops, @winnabonus, @winnaofficial
Gamba: @faircodes, @gambacodes, @gambadrops, @gambaofficial
Degen: @degendotcom, @degencodes, @degendrops, @degenbonus
Goated: @goatedcodes, @goateddrops, @goatedbonus, @goatedofficial
Razed: @razedcodes, @razeddrops, @razedbonus, @razedofficial
Qzino: @qzino_code, @qzino, @qzinodotai, @qzinocodes, @qzinodrops
CodeStats: @codestats2, @codestatsgg

These Telegram handles are the bot's configured upstream sources. They are NOT stated per-code in the Ctrl Alt Discord embeds — do not attach a specific Telegram handle to a specific Discord code unless that embed says so.

---

## 4. #stake-codes — BONUS DROP has NO original source

Verbatim embed pattern: title "STAKE BONUS DROP ALERT", then Code / Value / Total Drop Limit / Requirements / CLICK TO CLAIM, footer `codestats.gg/autoclaimer • [time]`; no Source line, no submitter, no "via", no site/Telegram.

Examples checked Nov 24–26:
- stakecom4gpxsae9w8c7w0 — Nov 26, 4:34 PM, $2, Total $2,000, Req $8,000 wagered in last 7 days, @Stake.com
- stakeusnh3j9gmi5bmahx — Nov 26, 3:36 PM, 12.50 SC, Total 50,000 SC, Req 50,000 SC played in last 7 days, @Stake.us
- stakepyq6arvne0ogq6m0 — Nov 26, 2:52 PM, $1, Req $4,000 wagered in last 7 days (no Total Drop Limit shown), @Stake.com
- stakecomt493u3coausr3g — Nov 26, 11:34 AM, $2, Total $2,000, Req $8,000 wagered in last 7 days, @Stake.com
- stakeus7ejidl8xn4b4pi — Nov 26, 10:14 AM, 2 SC, Total 2,000 SC, Req 8,000 SC played in last 7 days, @Stake.us
- stakecomtdplyyg2umofmj — Nov 26, 7:53 AM, $25, Total $2,500 in this check (earlier history table said $50,000 — see amount mismatch in §5), Req $10,000 wagered in last 7 days, @Stake.com
- stakeus3wobz2zkmrtxzr — Nov 24, 2:20 PM, 12.50 SC, Total 50,000 SC, Req 50,000 SC played in last 7 days, @Stake.us

USER SUBMITTED embeds are the same: no submitter, no Source. Pattern: title "USER SUBMITTED", "Support the community share the codes.", then platform (Stake.com / Stake.us / Both Platforms) and CLICK TO CLAIM, footer `CodeStats.gg • [time]`.
Examples Nov 24–26: samurai88y11 (Nov 24, 3:45 PM, Both), ninja3ty5 (8:16 PM, Both), 4bir2iuko1nj (10:41 PM, .com), violence2e33 (11:47 PM, .us), shadow8ii33 (Nov 25, 12:35 PM, Both), izxlfh0wisk18u (2:11 PM, .com), kairosaa99ii (2:11 PM, Both), wings7ii2 (4:03 PM, .us), tuvrd7p5 (5:49 PM, Both), 7wamg2cc (5:51 PM, Both), 7lktqwha (5:52 PM, Both), hkyizm1u (8:12 PM, Both).

Full #stake-codes history (48 codes Nov 24–26 + 1 pinned Jun 22 example), #rainbet-us-codes (11), #shuffle-codes (11), #gamba-codes (11), #thrill-codes (11), #razed-codes (10) is in the companion file `Bonus-Code-History-and-Platform-Regex.md`. For all of those, `original_source = "CodeStats.gg feed — no per-code origin stated"`, except Rainbet where the footer handle @rainbetuscodes / @rainbetusvip is the only handle, and Razed where the Nov 8 double-code notice points to discord.gg/razed.

---

## 5. Wrong channel / wrong platform / duplicate findings

No code was found in a wholly wrong channel in the sampled period (no Stake code in Shuffle/Rainbet/Thrill, etc.), but these mismatches were found — these are the bugs to fix in the bot:

1. **CodeStats.gg /recent vs Discord platform mismatch:** stakepyq6arvne0ogq6m0, staketrhuh8824dyokyqh, stakepl3a3gt53hqfbbt4, stakepyolnnyhjviibmr1 and BILJG8TF6H are labelled "USER SUBMITTED" with BOTH "US" and "Com" claim links on codestats.gg, while Discord labels the py/tr/pl codes BONUS DROP @Stake.com only and BILJG8TF6H LOW WAGER Stake.us only. Do not trust the /recent category label as platform — use the Discord embed role + claim-link domain/currency.
2. **bonusbuyspins is genuinely both-platform:** bonusbuyspins ($3, dropped Nov 21, 9:22 AM, wager $9,579) is listed under BOTH Stake.com and Stake.us on codestats.gg Active (18 codes: 2 .com / 16 .us) and on stakestats.net (Active 2 .com / 16 .us); enginegames ($4, Nov 21, 9:24 AM) is .us only. This one should be DUAL / BOTH, not single-platform.
3. **codestats.gg first-load duplication:** on first load the Active list duplicated every code (including Shuffle codes 75I9596U, VC7DZ6YU, DY19WCW1) under both STAKE.COM and STAKE.US headings — a transient loading state; after refresh the lists were correctly separated except for bonusbuyspins. A scraper that reads the first load will post Shuffle codes to Stake channels. Wait for / re-fetch after load, and validate platform per code.
4. **Non-.com prefixes posted as @Stake.com only:** staketr8z62wib21kn3uk ($3, Nov 24, 10:02 PM), stakepl3a3gt53hqfbbt4 ($1, Nov 26, 1:09 AM), stakepyq6arvne0ogq6m0 / stakepyolnnyhjviibmr1 ($1/$3) — prefix does not match "stakecom", but embed/link platform is Stake.com. Several also omit Total Drop Limit (only Value + Requirements shown). Prefix-only extraction will mis-route these.
5. **Systematic VERIFICATION FAILED duplicates in #stake-codes:** almost every BONUS DROP code is re-posted in the same minute as "USER SUBMITTED" with "VERIFICATION FAILED" (same code, same timestamp), e.g. stakeus3wobz2zkmrtxzr, stakeusdvk27lvz3y6egm, stakecomw0zqqmosvm42jj, stakecom3hjtf5zph6wwb8, stakeusshbrq69iamaenf, staketr8z62wib21kn3uk (Nov 24); stakecomtjkmpt8a576t12 (Nov 25, 1:42 AM), stakeus8b9mh6tmwylaol, stakecom1tes4x736asi6u, stakepyolnnyhjviibmr1, stakeusao56vue48dds0g; stakecombdwlri5bl6e7k0, stakeusomhdtcopbn13v3, stakeus7ejidl8xn4b4pi, stakecomt493u3coausr3g (Nov 26). Deduplicate by exact code string; do not count the failed copy as a new code and do not mark the drop as invalid because a submitted copy failed.
6. **Amount mismatches:** Ballislife low-wager codes show "Amount: $000" in Discord, but codestats.gg /recent shows BILJG8TF6H as $5. SportsGrid, FreeTips and GameChampions (.com) low-wager embeds have no Amount field at all, while GameChampions US shows $125.00. Do not treat "$000" as $0, and do not infer an amount where the embed has none. Also stakecomtdplyyg2umofmj: $25 value with Total $50,000 in the first history pass, $2,500 in the second source pass — treat Total as unverified for that row, do not hard-code it.
7. **#shuffle-codes mixes Shuffle.com and Shuffle.us in one channel**, but each embed is correctly labelled (Shuffle Edition vs Shuffle.US Edition, shuffle.com vs shuffle.us link) — not wrong, just shared. Channel alone cannot decide platform here.
8. **Timing drift:** stakeusnh3j9gmi5bmahx is 3:36 PM in Discord and 3:36:47 PM on codestats.gg, but "Dropped Nov 26, 3:39 PM" on stakestats.net. stakecom4gpxsae9w8c7w0 (Nov 26, 4:34 PM, $2) was in codestats.gg Active on first load (~4:52 PM) but absent from Active on refresh and absent from StakeStats .com Active (LATEST there: 2h ago = stakepyq6arvne0ogq6m0) — it left the active list within ~18 minutes. Do not use Active-list presence as a permanent platform/source signal; record droppedAt from the first sighting.

### Repo bugs found by reading leakgg-enterprise (no code was run, tested, or applied)

- `platform_rules.py` — Stake.us regex `^stakeus[a-z0-9]{12}$` is too strict; most real `stakeus...` codes are longer. Fix to `^stakeus[a-z0-9]{10,}$`.
- `platform_rules.py` — Rainbet.US, Shuffle, Thrill, Gamba, Razed have NO format regex, only `THRILL...`, `WINNA...`, etc. prefixes that never match the real codes. Add the formats in §6.
- `platform_rules.py` Stage 1 — both `stake.us` and `stake.com` present returns `dual_stake`. That is correct for a true dual code like bonusbuyspins, but wrong for the 8 ambiguous user-submitted codes where the embed lists both links as candidates. Those must be `AMBIGUOUS / BOTH`, with both claim links kept, not a single dual embed posted to both channels as if verified.
- `platform_rules.py` Stage 2 — Goated/Degen context regex `^[A-Z0-9_-]{4,24}$` would match any 8-char Rainbet/Shuffle code if ordering changes. Never use a generic alphanumeric pattern as a platform signal.
- `scrapers/codestats.py` — HTML fallback picks the first platform keyword (`shuffle.us` → `shuffle` → `stake.us` → `stake`), losing the second platform. Live feed uses `elif` for Shuffle US vs COM, so only one is kept. Use independent `if` checks per platform flag, as the Stake part already does.
- `scrapers/codestats.py` + `scrapers/telegram.py` — `classify_platform` is called with text only, often without the Source line / embed footer. Pass `source_name` from the Source line, and the embed footer / app name, every time.
- `tracker.py` / `scrapers/engine.py` — dedup key is `platform:code`, with cross-platform aliases only for Stake/Shuffle. Rainbet vs Shuffle 8-char codes are not deduped against each other, and a code seen on CodeStats and then on StakeStats / Telegram with a different `source_url` can re-post. Dedup on exact code string (case-sensitive) first, then platform, then source — see §7.
- `models.py Platform.from_str` — checks Stake before Shuffle/Rainbet, and matches "shuffle" as a substring. A message mentioning both will mis-route. Use the 5-stage pipeline in `platform_rules.py`, not `from_str`, for routing.
- `routes_config.json` — THRILL, GAMBA, and WINNA all share channel `1460666123484794880`; one subscriber route maps Shuffle, WINNA, THRILL, Goated, Rainbet, Stake, and Razed all to channel `1575388708545364057`. Even a correctly classified code lands in a shared / wrong channel. Give each platform its own channel, or the bot cannot prove correct routing.
- `discord_notifier.py` — dual-stake items post the SAME embed (with both claim links) to both Stake.us and Stake.com channels. For AMBIGUOUS codes, that looks like a verified dual drop. Split ambiguous codes into two candidate items, or post once to a dual channel with both links labelled as candidates, not verified.

---

## 6. Complete corrected regex — all platforms

Use these in `platform_rules.py`, in this priority order. Platform is decided by
role / claim-link / Source / app / footer FIRST, code format LAST. Never decide
platform from code format alone where the format is shared.

| Platform | Code format (regex) | Platform signals, in order | Claim link |
|---|---|---|---|
| Stake.us | `^stakeus[a-z0-9]{10,}$` (fix: was `{12}`), plus `^BIL[A-Z0-9]{7,}$`, `^ESBUS[A-Z0-9]+$`, `^(?:SPORTS(?:GR\|\d+GRID)\|SGRID\|SG\d+)[A-Za-z0-9]+$`, `^DSN[A-Z0-9]{6,}$`, `^SPIKEUS[A-Za-z0-9]{8}$`, `^DIMERS\d[A-Za-z0-9]{7,}$` | 1. @Stake.us role, 2. stake.us link + `currency=sweeps`, 3. value in SC, 4. verb "played", 5. Source: Ballislife / GameChampions US / SportsGrid / EsportsBetting (no COM) / Dimers / TheSpike.gg / VegasInsider / Deadspin | https://stake.us/settings/offers?currency=sweeps&type=code&code={code}&modal=redeemBonus — note: repo `platform_rules.py` uses `currency=sweeps`, repo `models.py` uses `currency=sweeps` for .us and `currency=ltc` for .com; CodeStats embeds use `currency=sweeps` (.us) / `currency=ltc` (.com). Do not use `currency=btc` from the old claim_url in `platform_rules.py` for .com — that is a mismatch to fix. |
| Stake.com | `^stakecom[a-z0-9]+$`, plus `^stake[a-z0-9]{6,}$` (stake+random, e.g. stakepyq6…, staketr…, stakepl… — platform must still be confirmed by role/embed, do NOT hard-code stake+anything = .com), plus `^ESBCOM[A-Z0-9]+$`, plus FreeTips PascalCase `^[A-Z][a-z]+(?:[A-Z][a-z]+){1,3}$` only with Source: FreeTips | 1. @Stake.com role, 2. stake.com link + `currency=ltc`, 3. value in $, 4. verb "wagered", 5. Source: FreeTips / EsportsBetting COM / GameChampions (no US) | https://stake.com/settings/offers?type=code&code={code}&currency=ltc&modal=redeemBonus |
| Stake — AMBIGUOUS / BOTH | Bare lowercase, no stake prefix: `^[a-z0-9]{6,15}$` e.g. samurai88y11, ninja3ty5, shadow8ii33, kairosaa99ii, tuvrd7p5, 7wamg2cc, 7lktqwha, hkyizm1u | Both @Stake.com and @Stake.us, both claim links (ltc AND sweeps), no value/req. Mark AMBIGUOUS / BOTH, keep both links, do not guess. | Both links above, labelled as candidates |
| Rainbet.US | `^[A-Z0-9]{8}$` case-sensitive | App "Rainbet.US Edition", footer @rainbetuscodes / @rainbetusvip, rainbet.us link. Channel/app/footer must decide — same format as Shuffle. | https://rainbet.us |
| Rainbet (.com) | `^[A-Z0-9]{6,12}$` in Telegram format, plus `^(?:RB\|RAINBET)[A-Za-z0-9_-]+$` only as a prefix hint | Telegram @EddiesCodesRainbet, rainbet.com link, `https://rainbet.com/affiliates?modal=wallet&tab=redeem` | https://rainbet.com/affiliates?modal=wallet&tab=redeem |
| Shuffle.com | `^[A-Z0-9]{8}$` case-sensitive | App "Shuffle Edition", role @Shuffle.com, shuffle.com link, value in $ | https://shuffle.com/?modal=c&md-code={code} |
| Shuffle.us | `^[A-Z0-9]{8}$` case-sensitive | App "Shuffle.US Edition", role @Shuffle.us, shuffle.us link, value in SC + GC | https://shuffle.us/?modal=c&md-code={code} |
| Thrill | `^[A-Z0-9]{10}$` case-sensitive | App "Thrill Edition", thrill.com link, role @Thrill.com. Keep Loss as a separate field when present. | https://thrill.com/?r=selfmade |
| Gamba | `^[a-z0-9]{9,17}$` after removing the embedded emoji | Channel + embed "Gamba Bonus Drop", gamba.com link, value in USDT/LTC/XRP. Strip emoji first. Ignore promo-paragraph words. Correction: latest "OOOOPS MY BAD" code wins. | https://gamba.com |
| Razed | `^[a-z0-9]{9,12}$`, usually ending `rzd` (not a rule — lmd3c8qtxfr is the exception) | Channel + embed "Razed Bonus Drop", razed.com link. Requirement is an explicit UTC window, not "last 7 days". Read bare code lines with no "Code:" label. | https://razed.com |
| Goated | `^(?:GOATED\|GOAT)[A-Za-z0-9_-]{3,20}$` | goated.com, @goateddrops, banner OCR | https://www.goated.com |
| Degen | `^(?:DEGEN\|DGN)[A-Za-z0-9_-]{3,20}$` | degen.com, @degendotcom, banner OCR | https://degen.com |
| Winna | `^WINNA[A-Za-z0-9_-]+$` as prefix hint only | winna.com, @EddiesCodesWinna | https://winna.com/?bonus-center=true&SELFMADE |
| Qzino | `^QZINO[A-Za-z0-9_-]+$` as prefix hint only | qzino.ai, @qzino_code | https://qzino.ai/?r=SELFMADE |

Shared-format warning: `^[A-Z0-9]{8}$` is Rainbet.US AND Shuffle.com AND Shuffle.us. `^[A-Z0-9]{10}$` is Thrill only in this window, but do not assume it is Thrill without the app/footer. A code format alone must never route an embed.

---

## 7. Deduplication and routing rules for the bot

1. **Dedup key = exact code string, case-sensitive, first.** If the exact code was already posted, do not post again, regardless of platform, source, or channel — unless it is a verified dual-platform code (bonusbuyspins) or an AMBIGUOUS code with two separate claim links, in which case post ONCE with both links, not twice.
2. **VERIFICATION FAILED is not a new code.** Same code, same minute, "USER SUBMITTED — VERIFICATION FAILED" = duplicate of the BONUS DROP. Drop it, do not mark the drop invalid.
3. **Correction wins.** Gamba "OOOOPS MY BAD" — latest code for that drop wins; the earlier code must not be used. Same for any later correction message from the same poster.
4. **Do not infer missing fields.** Total Drop Limit / Requirement / Amount absent = null. Do not infer $2,000 / $4,000 defaults. Do not treat "$000" as $0.
5. **Do not post on first load of codestats.gg Active.** Re-fetch / wait for the list to settle; the first load duplicated every code under both Stake headings.
6. **Record droppedAt from first sighting.** Active-list presence is transient — stakecom4gpxsae9w8c7w0 left Active within ~18 minutes. StakeStats droppedAt can differ by minutes from Discord / CodeStats (3:36 PM vs 3:36:47 PM vs 3:39 PM for stakeusnh3j9gmi5bmahx).
7. **Route by platform, not by channel name alone.** #stake-codes, #low-wager-codes, and #shuffle-codes each carry both .com and .us. #rainbet-us-codes, #gamba-codes, #thrill-codes, #razed-codes are single-platform in this window, so channel is a valid signal there only.
8. **Give each platform its own destination channel.** Shared channels in `routes_config.json` make correct routing unprovable — see §5.
9. **Original source field:** add `original_source`, `original_source_type`, and `original_source_url` to `BonusCodeItem` in `models.py`. Values:
   - Low-wager: `original_source = "Ballislife" | "GameChampions US" | "GameChampions" | "EsportsBetting" | "EsportsBetting COM" | "FreeTips" | "SportsGrid" | "Dimers"`, `original_source_type = "affiliate_site"`, `original_source_url = <repo mapping in §3, or null>`.
   - All other CodeStats codes: `original_source = "CodeStats.gg feed"`, `original_source_type = "codestats_feed"`, `original_source_url = "https://codestats.gg/recent"`, with a note `per_code_origin_not_stated = true`.
   - Rainbet.US: add `footer_handle = "@rainbetuscodes" | "@rainbetusvip"`.
   - Razed double-code notice: `original_source_note = "discord.gg/razed"`.
   - USER SUBMITTED Stake codes: `original_source = "community submission via #submit-stake-code"`, `original_source_type = "community_submission"`, submitter not preserved in the embed.

---

## 8. Code-editor prompt — copy / paste this

> Fix bonus-code platform detection in leakgg-enterprise using this file and the companion history file.
>
> 1. Add `original_source`, `original_source_type`, `original_source_url`, and `per_code_origin_not_stated` to `BonusCodeItem`. Fill them from §3 and §7.9. Do NOT invent a per-code original source where the embed says none — use "CodeStats.gg feed — no per-code origin stated".
> 2. Apply the corrected regex in §6, in priority order: role / claim-link domain+currency / Source line / app / footer FIRST, code format LAST. Fix `^stakeus[a-z0-9]{12}$` to `^stakeus[a-z0-9]{10,}$`, add `^[A-Z0-9]{8}$` for Rainbet.US/Shuffle (channel/app decides), `^[A-Z0-9]{10}$` for Thrill, `^[a-z0-9]{9,17}$` (emoji-stripped) for Gamba, `^[a-z0-9]{9,12}$` for Razed, and fix the .com claim URL currency from `btc` to `ltc` in `platform_rules.py`.
> 3. Mark the 8 ambiguous Stake codes as AMBIGUOUS / BOTH, keep both claim links, do not guess. bonusbuyspins is the only verified dual code in this window.
> 4. Dedup by exact code string first (§7.1), drop VERIFICATION FAILED duplicates, apply Gamba corrections, do not infer missing fields, do not treat "$000" as $0.
> 5. Fix `scrapers/codestats.py`: independent `if` checks per platform flag (no `elif` for Shuffle US/COM), wait/re-fetch the Active list before scraping (first load duplicates everything under both Stake headings), and pass Source + footer + app name into `classify_platform` every time.
> 6. Fix routing: give each platform its own channel in `routes_config.json` — remove the shared THRILL/GAMBA/WINNA channel and the shared subscriber channel. Do not use `Platform.from_str` for routing.
> 7. Test against every row in Tables 1–7 of the companion history file and §3 of this file, including ambiguous, paired, duplicate, missing-field, corrected, and amount-mismatch rows. A fix that passes only clean `stakecom...` / `stakeus...` rows is not done.
> 8. Do not redeem, log into, or enter any code on any casino site. This is detection / extraction / routing only.

---

## 9. Limitations

- History is as far as reached in the sessions: #stake-codes Nov 24–26, #low-wager-codes Nov 21–26, #rainbet-us-codes / #shuffle-codes / #thrill-codes Nov 24–26, #gamba-codes Oct 18–Nov 10, #razed-codes Nov 3–8. Older history exists and was not reached.
- Low-wager count: first history pass listed 32 codes, second source pass listed 31 — the tables in §3 list 32 rows explicitly, so count from the rows, not the headline. One row may have been missed in the second pass; do not delete a row from §3 on the basis of the 31 count.
- stakecomtdplyyg2umofmj Total Drop Limit differs between passes ($50,000 vs $2,500) — treat as unverified.
- No message IDs were fabricated. Source for a Discord row is channel URL + poster + date/time. Full message link form: `https://discord.com/channels/1412350608786325536/<channel-ID>/<message-ID>`, obtained in Discord via `...` > Copy Message Link.
- All times EST as shown by Discord, unless noted as codestats.gg / stakestats.net timestamps.
