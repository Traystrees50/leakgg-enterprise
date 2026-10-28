/*
# Create drop_history table for persistent drop tracking and analytics

1. New Tables
- `drop_history`
  - `id` (uuid, primary key) — unique row id
  - `code` (text, not null) — the bonus code, case preserved
  - `platform` (text, not null) — platform name matching Platform enum values (e.g. "Stake.us", "Stake.com")
  - `source_name` (text) — human-readable source name (e.g. "@codestats2")
  - `source_url` (text) — permalink to the source message/post
  - `amount_value` (text) — bonus value description (e.g. "$5.00 USD")
  - `wager_requirement` (text) — wager/play-through requirement text
  - `claims_count` (text) — claims limit info if available
  - `availability_status` (text) — validated status from Stake GraphQL ("AVAILABLE", "FULLY_CLAIMED", "EXPIRED", "UNKNOWN")
  - `event_type` (text) — drop type ("DROP", "WEEKLY BOOST", "MONTHLY BONUS", "VIP EVENT", "AFFILIATE")
  - `is_affiliate` (boolean, default false) — whether this is an affiliate code
  - `is_highroller` (boolean, default false) — highroller flag
  - `is_dual_stake` (boolean, default false) — dual Stake.us + Stake.com flag
  - `currency` (text) — currency hint (e.g. "ltc", "sweeps")
  - `image_url` (text) — optional media image URL
  - `first_seen_at` (timestamptz, default now()) — when the code was first detected
  - `last_seen_at` (timestamptz, default now()) — last time the code was re-observed in a sweep
  - `sightings` (integer, default 1) — count of times this code was seen across sweeps
- `drop_sightings`
  - `id` (uuid, primary key) — unique row id
  - `drop_id` (uuid, references drop_history.id) — which drop was sighted
  - `source_name` (text) — which source reported it this time
  - `source_url` (text) — permalink for this specific sighting
  - `seen_at` (timestamptz, default now()) — timestamp of this sighting
2. Indexes
- `idx_drop_history_code_platform` — unique index on (code, platform) for fast dedup lookups
- `idx_drop_history_last_seen` — index on last_seen_at for recency queries
- `idx_drop_history_first_seen` — index on first_seen_at for history queries
- `idx_drop_sightings_drop_id` — index on drop_id for join queries
3. Security
- Enable RLS on both tables.
- Grant CRUD to `anon` + `authenticated` since this is a single-tenant monitoring app (no sign-in screen).
- All policies use `USING (true)` / `WITH CHECK (true)` because the data is intentionally public/shared within the app.
4. Notes
- The `drop_history` table replaces the fragile `seen_codes.json` flat-file as the durable, queryable history store.
- The `drop_sightings` table records every individual observation, enabling channel leaderboards and heatmap analytics.
- Upsert logic: if (code, platform) already exists, increment sightings and update last_seen_at.
*/