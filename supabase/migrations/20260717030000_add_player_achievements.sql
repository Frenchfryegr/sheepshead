CREATE TABLE IF NOT EXISTS "public"."PlayerAchievements" (
    "player_achievement_id" bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "player_id" bigint NOT NULL REFERENCES "public"."Players"("player_id") ON DELETE CASCADE,
    "achievement_key" text NOT NULL,
    "tier" text NOT NULL CHECK ("tier" IN ('bronze', 'silver', 'gold')),
    "earned_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "PlayerAchievements_player_key_tier_unique"
        UNIQUE ("player_id", "achievement_key", "tier")
);

ALTER TABLE "public"."PlayerAchievements" OWNER TO "postgres";

COMMENT ON TABLE "public"."PlayerAchievements" IS
  'Earned achievement tiers, one row per (player, achievement, tier). Sticky: rows are only ever inserted by recompute, never deleted, so earned_at is the first time the tier was reached. Definitions live in api/main.py (ACHIEVEMENT_DEFS).';

CREATE POLICY "Full Access for postgres user" ON "public"."PlayerAchievements" TO "postgres" USING (true);

ALTER TABLE "public"."PlayerAchievements" ENABLE ROW LEVEL SECURITY;

GRANT ALL ON TABLE "public"."PlayerAchievements" TO "anon";
GRANT ALL ON TABLE "public"."PlayerAchievements" TO "authenticated";
GRANT ALL ON TABLE "public"."PlayerAchievements" TO "service_role";
