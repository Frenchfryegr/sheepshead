CREATE TABLE IF NOT EXISTS "public"."Badges" (
    "badge_key" text PRIMARY KEY,
    "holder_player_id" bigint REFERENCES "public"."Players"("player_id") ON DELETE SET NULL,
    "value" double precision,
    "display_value" text,
    "sample_size" integer,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

ALTER TABLE "public"."Badges" OWNER TO "postgres";

COMMENT ON TABLE "public"."Badges" IS
  'Current holder + value for each badge. One row per badge_key. Definitions live in api/main.py; this table is rebuilt in full by recompute_badges().';

CREATE POLICY "Full Access for postgres user" ON "public"."Badges" TO "postgres" USING (true);

ALTER TABLE "public"."Badges" ENABLE ROW LEVEL SECURITY;

GRANT ALL ON TABLE "public"."Badges" TO "anon";
GRANT ALL ON TABLE "public"."Badges" TO "authenticated";
GRANT ALL ON TABLE "public"."Badges" TO "service_role";
