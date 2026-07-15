CREATE TABLE IF NOT EXISTS "public"."Accounts" (
    "user_id" "uuid" NOT NULL,
    "username" character varying NOT NULL,
    "email" character varying NOT NULL,
    "claimed_player_id" bigint,
    "created" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."Accounts" OWNER TO "postgres";


COMMENT ON TABLE "public"."Accounts" IS 'Links a Supabase Auth user to an app username, and optionally to one claimed Player';



ALTER TABLE ONLY "public"."Accounts"
    ADD CONSTRAINT "Accounts_pkey" PRIMARY KEY ("user_id");



ALTER TABLE ONLY "public"."Accounts"
    ADD CONSTRAINT "Accounts_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."Accounts"
    ADD CONSTRAINT "Accounts_claimed_player_id_fkey" FOREIGN KEY ("claimed_player_id") REFERENCES "public"."Players"("player_id") ON DELETE SET NULL;



CREATE UNIQUE INDEX "Accounts_username_lower_idx" ON "public"."Accounts" USING "btree" ("lower"(("username")::"text"));



CREATE UNIQUE INDEX "Accounts_email_idx" ON "public"."Accounts" USING "btree" ("email");



CREATE UNIQUE INDEX "Accounts_claimed_player_id_unique_idx" ON "public"."Accounts" USING "btree" ("claimed_player_id") WHERE ("claimed_player_id" IS NOT NULL);



CREATE POLICY "Full Access for postgres user" ON "public"."Accounts" TO "postgres" USING (true);



ALTER TABLE "public"."Accounts" ENABLE ROW LEVEL SECURITY;




GRANT ALL ON TABLE "public"."Accounts" TO "anon";
GRANT ALL ON TABLE "public"."Accounts" TO "authenticated";
GRANT ALL ON TABLE "public"."Accounts" TO "service_role";
