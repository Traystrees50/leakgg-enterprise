/*
# Create drop_history and drop_sightings tables for persistent drop tracking and analytics

1. New Tables
- `drop_history` — persistent record of every detected bonus code with platform, source, value, validation status, first/last seen timestamps, and sighting count
- `drop_sightings` — individual observation records enabling channel leaderboards and hourly heatmap analytics
2. Indexes
- Unique index on (code, platform) for dedup upserts
- Indexes on last_seen_at, first_seen_at, platform for fast queries
3. Security
- RLS enabled on both tables, CRUD granted to anon + authenticated (single-tenant, no sign-in)
- Policies use USING(true) because the data is intentionally shared within the app
*/

CREATE TABLE IF NOT EXISTS drop_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL,
    platform text NOT NULL,
    source_name text,
    source_url text,
    amount_value text,
    wager_requirement text,
    claims_count text,
    availability_status text,
    event_type text,
    is_affiliate boolean NOT NULL DEFAULT false,
    is_highroller boolean NOT NULL DEFAULT false,
    is_dual_stake boolean NOT NULL DEFAULT false,
    currency text,
    image_url text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    sightings integer NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_drop_history_code_platform
    ON drop_history (code, platform);

CREATE INDEX IF NOT EXISTS idx_drop_history_last_seen
    ON drop_history (last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_drop_history_first_seen
    ON drop_history (first_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_drop_history_platform
    ON drop_history (platform);

CREATE TABLE IF NOT EXISTS drop_sightings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    drop_id uuid REFERENCES drop_history(id) ON DELETE CASCADE,
    source_name text,
    source_url text,
    seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drop_sightings_drop_id
    ON drop_sightings (drop_id);

CREATE INDEX IF NOT EXISTS idx_drop_sightings_seen_at
    ON drop_sightings (seen_at DESC);

ALTER TABLE drop_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE drop_sightings ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON drop_history TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON drop_sightings TO anon, authenticated;

DROP POLICY IF EXISTS "anon_select_drops" ON drop_history;
CREATE POLICY "anon_select_drops" ON drop_history FOR SELECT
    TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_insert_drops" ON drop_history;
CREATE POLICY "anon_insert_drops" ON drop_history FOR INSERT
    TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update_drops" ON drop_history;
CREATE POLICY "anon_update_drops" ON drop_history FOR UPDATE
    TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete_drops" ON drop_history;
CREATE POLICY "anon_delete_drops" ON drop_history FOR DELETE
    TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_select_sightings" ON drop_sightings;
CREATE POLICY "anon_select_sightings" ON drop_sightings FOR SELECT
    TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_insert_sightings" ON drop_sightings;
CREATE POLICY "anon_insert_sightings" ON drop_sightings FOR INSERT
    TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update_sightings" ON drop_sightings;
CREATE POLICY "anon_update_sightings" ON drop_sightings FOR UPDATE
    TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete_sightings" ON drop_sightings;
CREATE POLICY "anon_delete_sightings" ON drop_sightings FOR DELETE
    TO anon, authenticated USING (true);