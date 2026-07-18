# AGENTS.md

## 🚀 Project Overview
This repository contains a full-stack application for "Sheepshead." It consists of two main parts: a modern frontend built with Angular (TypeScript) and a backend API implemented using FastAPI/Python. The goal is to connect the user interface provided by the Angular client with the business logic exposed by the Python API.

## 🛠️ Tech Stack
*   **Frontend:** Angular (v21+), TypeScript, JavaScript. Dependencies managed via `npm`. Key libraries include `@angular/*` packages and Express for SSR functionality.
*   **Backend:** Python (FastAPI). Uses `uv` for virtual environment and dependency management.
*   **Package Managers/Tools:** `npm`, `pip`, `uv`.

## ⚙️ Setup Commands
To get a working development environment, follow these steps:

1.  **Get Environment Variables:** Obtain the required `.env` file from Caleb.
2.  **Backend Dependencies (API):** Install dependencies using `pip install uv`.
3.  **Start Backend Server:** Run the FastAPI application using `uv run fastapi dev`.
4.  **Frontend Dependencies (Angular):** Navigate to the `angular/` directory and install node modules (`npm install`).
5.  **Start Frontend Server:** Use `ng serve --open` from the root or within the `angular/` directory.

## 🏗️ Build, Test, and Lint Commands
### Angular Frontend
*   **Development Serve (Run):** `npm start` (or `ng serve --open`)
*   **Build Production Bundle:** `npm run build` (Generates optimized assets in `dist/`).
*   **Testing (Unit):** `ng test` (Runs unit tests using Vitest).
*   **E2e Testing:** `ng e2e` (End-to-end testing).

### Backend API
*   (No dedicated build/lint commands were found for the backend.)

## 📁 Project Structure Map
*   `angular/`: Contains all frontend source code. This is an Angular workspace with components, services, and modules defined in TypeScript.
*   `api/`: Houses the backend API logic, written in Python (FastAPI).
*   `.vscode/`: VS Code workspace configuration files.

## 🎨 Code Style Conventions
*   **Frontend:** Follows standard Angular conventions using TypeScript and RxJS patterns.
*   **Formatting:** Prettier is listed as a dependency (`devDependencies`), implying it should be used for code formatting consistency across the project.
*   **Naming:** Standard PascalCase/camelCase conventions are followed, typical of Angular development.

## 🧪 Testing Conventions
*   **Frameworks:** Angular utilizes **Vitest** (via `ng test`) for unit testing.
*   **Location:** Test files generally follow the pattern defined by the CLI and should be co-located or imported into the component/module being tested.

## 🔐 Environment Variables & Secrets
*   **Required Vars:** The backend requires an environment file (`.env`) to operate, containing necessary credentials (e.g., database URLs, external service keys).
*   **Example Location:** Look for example variable files provided by the team. *Note: No explicit secret examples were found in the codebase.*

## ⚠️ Gotchas / Non-obvious Things
1.  **Two-Part Execution:** The frontend and backend run independently. Both services must be started, and cross-service communication (like CORS) must be verified.
2.  **Dependency Management:** Use `npm` for Angular dependencies and `pip`/`uv` for Python dependencies.
3.  **API Backend Setup:** Initial setup requires obtaining the `.env` file from Caleb before running the API development server.

## 🏅 Adding a Badge

A "badge" is a single statistic held by exactly one `Player` at a time (or nobody, if no one
qualifies). The whole system is **registry-driven and self-contained inside `api/main.py`** — a
new badge is almost always a pure-Python change to that one file, with **no migration, no new
endpoint, and no frontend change required**. This section is the authoritative, current state of
the engine — read it before scanning `main.py` yourself.

### Where everything lives (all in `api/main.py`)

- `BadgeDef` (dataclass) — one badge's definition: `key`, `title`, `description`, `value()`,
  `eligible()`, `tiebreak_sample()`, `format()`, plus two opt-in extension fields explained below:
  `tiebreakers` (tuple of extra tiebreak lambdas, default `()`) and `lower_is_better` (bool,
  default `False`).
- `BADGE_DEFS` — the ordered list of all `BadgeDef`s. **List order is the backend/API order**;
  the frontend re-sorts alphabetically by title for display (see "Frontend display order" below),
  so `BADGE_DEFS` order is otherwise only cosmetic to `GET /badges`'s raw JSON order. Currently:
  `just_plain_good`, `the_sidekick`, `dominator`, `lone_wolf`, `overconfident`, `punching_bag`,
  `icarus`, `chicken_dinner`, `biggest_loser`, `big_loser`, `always_finds_a_way`.
- `_empty_stats(player_id)` — the zeroed per-player stats dict shape. Every counter a badge reads
  must be initialized here.
- `aggregate_player_stats()` — the **single** query + single pass that builds one stats dict per
  player, for every completed game. This is the only place that talks to the database for badge
  purposes. Never add a per-badge query.
- `_select_holder(badge, stats)` — picks the winner for one badge via a `max()` over a tuple:
  `(value_or_negated, tiebreak_sample, *tiebreakers, games_played, -player_id)`.
- `recompute_badges()` — calls `aggregate_player_stats()` once, runs `_select_holder()` for every
  `BadgeDef`, and upserts the whole `Badges` table. Wrapped in try/except so a badge bug can never
  break a game-mutation request. Full recompute every time, never incremental.
- `_game_is_completed(game_id)` — guard used before recomputing on a round change.
- `GET /badges` — the only badge read endpoint; loops `BADGE_DEFS` in order and enriches the
  holder with scoreboard preferences. Fully generic — never needs editing for a new badge unless
  the badge requires a genuinely new response field (rare; see "When you DO need to touch other
  files" below).

### What's already selected in the one query (`aggregate_player_stats`)

The query already pulls, per completed game: `game_id`, roster player IDs
(`Players_X_Games(player_id)`), and per round: `round_number`, `round_result`, `no_schneider`,
`no_partner`, `created`, and per player-round-score row: `player_id`, `player_role`, `point_delta`.
**If your badge only needs these fields, no query change is needed at all** — just add counters
and increment them in the existing loops.

### Two loops per game — know which one your badge belongs in

1. **Flat per-round loop** (iterates `PlayerRoundScore` rows in no particular order, one branch per
   `role in {"Picker", "Partner", "Opponent", "Leaster Winner", "Leaster Loser"}`; `"Dealer"` rows
   — the 4-player sit-out role, `point_delta: 0` — are never counted as a round played by any
   badge and have no branch). Use this for anything countable from a single round in isolation —
   win/loss counts, no-schneider/no-partner flags, streak-free tallies. This is where
   `picker_rounds`, `picker_wins`, `partner_rounds`, `partner_wins`, `picker_schneider_wins`,
   `lone_wolf_count`, `overconfident_count`, `punching_bag_count`, and
   `big_loser_rounds_played`/`big_loser_rounds_won` are computed. A round "win" depends on role:
   Picker/Partner win on `round_result == 'Picker Win'`, Opponent wins on `'Picker Loss'`, and
   `Leaster Winner`/`Leaster Loser` are unconditional (the role itself is the outcome).
2. **Per-game replay loop** (rounds sorted by `round_number`, maintains a `running_totals` dict per
   roster player, computes `winner_ids` via the tie-inclusive "highest final total" rule — same
   rule the frontend's `getGameWinnerName()` in `games.ts` uses). Use this for anything that needs
   **whole-game context**: who won, running point margins, peak leads, final scores. **Icarus,
   Chicken Dinner, and Biggest Loser all share this one loop** — it already computes
   `running_totals`, `max_lead`, `final_max`, and `winner_ids` per game, then branches once per
   roster player into a winner side (`games_won`, `best_won_score`) and a non-winner side
   (`worst_lost_score`, `icarus_max_lead`/`icarus_final_score`). **Extend this shared loop rather
   than writing a second per-game replay** — the running-totals computation is the expensive part
   and should not be duplicated.

### Existing stats fields (current `_empty_stats` shape)

`player_id`, `player_name`, `games_played`, `picker_rounds`, `picker_wins`, `partner_rounds`,
`partner_wins`, `picker_schneider_wins`, `lone_wolf_count`, `overconfident_count`,
`overconfident_last_created`, `punching_bag_count`, `icarus_max_lead`, `icarus_final_score`,
`games_won`, `best_won_score`, `worst_lost_score`, `big_loser_rounds_played`,
`big_loser_rounds_won`. Check this list before adding a counter — your badge may already be one
division away from an existing field (e.g. any new per-game win % badge reuses
`games_won`/`games_played`; any new all-role round win % badge reuses
`big_loser_rounds_won`/`big_loser_rounds_played` directly instead of re-deriving from the
role-specific counters).

### Tiebreak extension points (already built, don't reinvent)

- **Default chain** (no extra fields set): `tiebreak_sample` (the natural denominator/count) →
  `games_played` → lowest `player_id`. This is enough for most badges.
- **Custom extra tiebreak steps**: pass a tuple of lambdas to `tiebreakers=(...)`, evaluated in
  order between `tiebreak_sample` and the generic fallback. Since the selector is a `max()`, a
  tiebreak lambda must return a value where **larger = wins the tie**. To make a "lower value wins
  the tie" rule work, negate it in the lambda (`lambda stats: -stats["some_score"]`, see
  `icarus`/`biggest_loser`). To rank by a string alphabetically-earliest-wins, use the
  `_alpha_priority()` helper (see `overconfident`), which inverts character ordinals so `max()`
  picks the earliest name. Always guard `None`/missing values with a `float("-inf")` fallback so an
  ineligible-for-the-tiebreak player never crashes the comparison (see `chicken_dinner`,
  `biggest_loser`).
- **`lower_is_better=True`**: set this when the badge's *primary metric* itself is "smaller wins"
  (e.g. `biggest_loser`'s win % — see the field). This only flips the sign used inside
  `_select_holder`'s sort key; `value()`'s return value (and therefore the stored/displayed
  percentage) is untouched, so the display always shows the true metric, never a negated one.
  Never negate inside `value()` itself for this reason.

### Frontend display order (alphabetical, not registry order)

`GET /badges` returns badges in `BADGE_DEFS` order, but both frontend surfaces re-sort by `title`
(`localeCompare`) before rendering: `Badges.filteredBadges` (`angular/src/app/badges/badges.ts`)
for the `/badges` page, and `Profile.filterHeldBadges` (`angular/src/app/profile/profile.ts`) for
the held-badges section on `/profile`. **A new badge needs no frontend change for this** — it's
sorted in automatically by title. Don't reorder `BADGE_DEFS` to influence display order; it no
longer does anything for display and would be a no-op end-to-end.

### Trigger wiring (do not add a new trigger)

`recompute_badges()` already fires on: `complete_game`, `set_game_status` (both directions),
`delete_game`, and on `create_round`/`update_round`/`delete_round` **only when
`_game_is_completed()` is true** for that round's game. A new badge needs zero new trigger wiring
— it's picked up automatically because `recompute_badges()` iterates all of `BADGE_DEFS`. There's
also a `@app.on_event("startup")` call so standings are correct immediately after a deploy/restart.

### Workflow for a new badge

1. Get from whoever's asking: title, description, exact metric (numerator/denominator or raw
   count), direction (higher/lower wins), minimum sample, and tiebreak rule. Don't guess these —
   ambiguity here (e.g. "win %" meaning rate vs. frequency) has bitten this codebase before.
2. Check whether the metric can be built from fields already selected (see above) and from
   counters already in `_empty_stats` — most new badges need at most one new counter.
3. Add the counter(s) to `_empty_stats()`, increment them in the correct loop (flat per-round vs.
   per-game replay — see above), reusing the shared per-game replay loop if whole-game context is
   needed.
4. Add one `BadgeDef` entry to the end of `BADGE_DEFS` (append, unless the requester wants a
   specific display position).
5. Do **not** touch: the `Badges` table/migration, `GET /badges`, the recompute triggers, the
   `/profile` badges section, or the `/badges` page — all of them are generic over `BADGE_DEFS`.
6. Validate with `python -c "import ast; ast.parse(open('api/main.py', encoding='utf-8').read())"`
   (or equivalent) rather than running the server, unless asked to run/verify live.

### When you DO need to touch other files

Only if the badge needs a **response field no existing badge can share** (e.g. something beyond
`value`/`display_value`/`sample_size`/holder info) — in that case update `GET /badges`'s per-badge
dict, `angular/src/app/interfaces/badge.ts`, and any template reading the new field, keeping the
field generic (populated for every badge, not just the new one) rather than badge-specific.