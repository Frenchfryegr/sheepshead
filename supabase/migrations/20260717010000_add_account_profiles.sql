ALTER TABLE "public"."Accounts"
  ADD COLUMN "avatar_path" text,
  ADD COLUMN "scoreboard_initials" character varying(4),
  ADD COLUMN "scoreboard_color" character(7),
  ADD COLUMN "show_avatar_on_scoreboard" boolean DEFAULT false NOT NULL;

ALTER TABLE "public"."Accounts"
  ADD CONSTRAINT "Accounts_scoreboard_initials_check"
    CHECK (
      "scoreboard_initials" IS NULL
      OR "scoreboard_initials" ~ '^[A-Z0-9]{1,4}$'
    ),
  ADD CONSTRAINT "Accounts_scoreboard_color_check"
    CHECK (
      "scoreboard_color" IS NULL
      OR "scoreboard_color" ~ '^#[0-9A-F]{6}$'
    );

COMMENT ON COLUMN "public"."Accounts"."avatar_path" IS
  'Server-generated Supabase Storage object path for the account profile picture.';

COMMENT ON COLUMN "public"."Accounts"."scoreboard_initials" IS
  'Optional scoreboard initials preference applied to this account''s claimed player.';

COMMENT ON COLUMN "public"."Accounts"."scoreboard_color" IS
  'Optional scoreboard header color preference applied to this account''s claimed player.';

COMMENT ON COLUMN "public"."Accounts"."show_avatar_on_scoreboard" IS
  'When true, this account''s profile picture may be shown next to initials for the claimed player on public scoreboards.';

INSERT INTO storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
VALUES (
  'profile-pictures',
  'profile-pictures',
  true,
  2097152,
  ARRAY['image/jpeg', 'image/png', 'image/webp']
)
ON CONFLICT (id) DO NOTHING;
