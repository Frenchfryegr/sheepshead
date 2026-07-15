ALTER TYPE "public"."Player Role" ADD VALUE IF NOT EXISTS 'Dealer';



ALTER TABLE "public"."Games" DROP CONSTRAINT "Games_num_players_check";
ALTER TABLE "public"."Games" ADD CONSTRAINT "Games_num_players_check"
    CHECK ((("num_players" = 3) OR ("num_players" = 4) OR ("num_players" = 5)));
