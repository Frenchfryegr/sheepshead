ALTER TABLE "public"."Accounts" ADD COLUMN "contact_email" character varying;



COMMENT ON COLUMN "public"."Accounts"."contact_email" IS 'Optional real email address provided by the user for contact purposes; separate from the "email" column, which is the synthetic address used internally with Supabase Auth';
