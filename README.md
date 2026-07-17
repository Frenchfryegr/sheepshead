## Local Development ##

### Prerequisites
- Get the `.env` file from Caleb (only if you want to push to deployed Supabase, you don't need it for local dev)
- Install `uv`: `pip install uv`
- Install Angular CLI: `npm install -g @angular/cli`
- [Install Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started#installing-the-supabase-cli) 

### Install Dependencies 
```bash
cd angular
npm i
```

### Start Frontend
```bash
ng serve --open
```

### Start Backend
```bash
uv run fastapi dev
```

## Database Setup & Migrations

### Local Development Database

You can stand up a local supabase instance, load the schema, and start going ham doing whatever you want

**Initialize Supabase locally:**
```bash
npx supabase start
```
This starts a local PostgreSQL database and Supabase instance. You'll see connection details in the output. There's a lot of useful things in that output that you should look at, including the browser URL to manage the supabase instance. Grab the APIs -> Project URL and Authentication Keys -> Secret from the output.
In the /api directory, create .env and set
```bash
SUPABASE_URL="<Project URL>"
SUPABASE_KEY="<Secret Authentication Key>"
```
You also need to create SIGNUP_INVITE_CODE in the .env file. You can set it to anything, you will use that code to make an account in Sheepshead for your local instance

You should now be set up for local development. Start the web app and start adding data.



### Connecting to Test and Prod Databases
**Link to your Supabase project (one-time setup):**
```bash
npx supabase link
```

### Database Migrations

**Create a new migration:**
```bash
npx supabase migration new <migration_name>
```
This creates a new file in `./supabase/migrations/`. Edit it to write your SQL.

**Test migration locally:**
```bash
npx supabase migration up
```
Check the local database to verify the migration worked correctly.

**Push migration to test environment:**
```bash
npx supabase db push --db-url "TEST_SUPABASE_CONN_STRING" --debug --yes
```
This applies all pending migrations to the test supabase project. If you are making schema changes that have corresponding code changes, only do this AFTER the deploy to test succeeds

**Deploy migration to production:**
Before deploying, ensure the migration has been tested in the test environment

Then run:
```bash
npx supabase db push --linked
```
(Make sure you're linked to the production project first)

### Useful Supabase Commands

**Check migration status:**
```bash
npx supabase migration list --linked
```

**Reset local database to clean state:**
```bash
npx supabase db reset
```

### Syncing Local Database with Production

**Pull production schema and data to local (with reset):**
```bash
npx supabase db pull --linked
```
This resets your local database and pulls the current schema and data from the linked production project. Useful for getting back in sync after changes have been deployed.

**Pull production schema only (preserves local data):**
```bash
npx supabase db pull --linked --schema-only
```
Pulls just the schema changes from production without resetting or overwriting your local data.

**Full reset and sync from production:**
```bash
npx supabase db reset
npx supabase db pull --linked
```
First resets to migrations only, then pulls fresh data from production. Use this when you want a completely clean local state matching production.
