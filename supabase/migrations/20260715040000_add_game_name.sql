ALTER TABLE "public"."Games" ADD COLUMN "game_name" character varying;



COMMENT ON COLUMN "public"."Games"."game_name" IS 'Optional user-chosen name for the game; falls back to displaying the date/game number when null';
