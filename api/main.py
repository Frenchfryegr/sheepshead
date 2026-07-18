import os
import re
import logging
from dataclasses import dataclass
from dotenv import load_dotenv

from enum import Enum
from datetime import datetime, timezone
from uuid import uuid4
from typing import Callable

from fastapi import FastAPI, Body, Header, HTTPException, Depends, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client

class TABLE_NAMES(Enum):
    GAMES = "Games"
    PLAYERS = "Players"
    PLAYERSXGAMES = "Players_X_Games"
    PLAYERROUNDSCORE = "PlayerRoundScore"
    ROUNDS = "Rounds"
    ACCOUNTS = "Accounts"
    BADGES = "Badges"

class ROUND_RESULTS(Enum):
    PICKER_WIN = "Picker Win"
    PICKER_LOSS = "Picker Loss"
    LEASTER = "Leaster"

SYNTHETIC_EMAIL_DOMAIN = "accounts.sheepsheadscores.internal"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PROFILE_BUCKET = "profile-pictures"
MAX_PROFILE_PICTURE_BYTES = 2 * 1024 * 1024
INITIALS_PATTERN = re.compile(r"^[A-Z0-9]{1,4}$")
COLOR_PATTERN = re.compile(r"^#[0-9A-F]{6}$")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BadgeDef:
    key: str
    title: str
    description: str
    value: Callable[[dict], float]
    eligible: Callable[[dict], bool]
    tiebreak_sample: Callable[[dict], float]
    format: Callable[[float], str]
    # Extra tiebreak extractors evaluated (in order) after tiebreak_sample and before the
    # generic games_played/player_id fallback. Empty for every badge except ones that need a
    # bespoke tiebreak chain — leaving this empty preserves the original 4-tuple sort exactly.
    tiebreakers: tuple[Callable[[dict], object], ...] = ()


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _count(value: float) -> str:
    return str(int(value))


def _alpha_priority(name: str) -> tuple:
    # Inverts lexicographic order so that, under max(), the alphabetically-earliest name wins.
    return tuple(-ord(ch) for ch in (name or "").lower())


BADGE_DEFS: list[BadgeDef] = [
    BadgeDef(
        key="just_plain_good",
        title="Just Plain Good",
        description="Highest picker win %",
        value=lambda stats: stats["picker_wins"] / stats["picker_rounds"],
        eligible=lambda stats: stats["picker_rounds"] >= 5,
        tiebreak_sample=lambda stats: stats["picker_rounds"],
        format=_pct,
    ),
    BadgeDef(
        key="the_sidekick",
        title="The Sidekick",
        description="Highest partner win %",
        value=lambda stats: stats["partner_wins"] / stats["partner_rounds"],
        eligible=lambda stats: stats["partner_rounds"] >= 5,
        tiebreak_sample=lambda stats: stats["partner_rounds"],
        format=_pct,
    ),
    BadgeDef(
        key="dominator",
        title="Dominator",
        description="Highest schneider-win rate as picker",
        value=lambda stats: stats["picker_schneider_wins"] / stats["picker_rounds"],
        eligible=lambda stats: stats["picker_rounds"] >= 5,
        tiebreak_sample=lambda stats: stats["picker_rounds"],
        format=_pct,
    ),
    BadgeDef(
        key="lone_wolf",
        title="Lone Wolf",
        description="Most times going alone (no partner)",
        value=lambda stats: float(stats["lone_wolf_count"]),
        eligible=lambda stats: stats["lone_wolf_count"] >= 1,
        tiebreak_sample=lambda stats: stats["lone_wolf_count"],
        format=lambda value: str(int(value)),
    ),
    BadgeDef(
        key="overconfident",
        title="Overconfident",
        description="Most times going alone and losing",
        value=lambda stats: float(stats["overconfident_count"]),
        eligible=lambda stats: stats["overconfident_count"] >= 1,
        tiebreak_sample=lambda stats: stats["overconfident_count"],
        format=_count,
        tiebreakers=(
            lambda stats: stats.get("overconfident_last_created") or "",
            lambda stats: _alpha_priority(stats.get("player_name")),
        ),
    ),
    BadgeDef(
        key="punching_bag",
        title="Punching Bag",
        description="Most times losing with no schneider",
        value=lambda stats: float(stats["punching_bag_count"]),
        eligible=lambda stats: stats["punching_bag_count"] >= 1,
        tiebreak_sample=lambda stats: stats["punching_bag_count"],
        format=_count,
    ),
]


class ProfileUpdate(BaseModel):
    username: str | None = None
    contact_email: str | None = None
    scoreboard_initials: str | None = None
    scoreboard_color: str | None = None
    show_avatar_on_scoreboard: bool | None = None


tags_metadata = [
    {"name": "Default", "description": "idk if i even need this"},
    {"name": "Game Management", "description": "do stuff to da games"},
    {"name": "Player Management", "description": "do stuff to da playas"},
    {"name": "Auth", "description": "accounts, login, and player claiming"},
    {"name": "Badge Management", "description": "badge standings"},

]

load_dotenv()

app = FastAPI(openapi_tags=tags_metadata)

default_origins = "http://localhost:4200,http://127.0.0.1:4200"
allowed_origins = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)


def create_auth_client() -> Client:
    # Fresh client per call so a signed-in user's session never gets attached
    # to (and doesn't contaminate) the shared service-role `supabase` client above.
    return create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))


def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_response = create_auth_client().auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not user_response or not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_response.user.id


def profile_avatar_url(avatar_path: str | None) -> str | None:
    if not avatar_path:
        return None
    try:
        return supabase.storage.from_(PROFILE_BUCKET).get_public_url(avatar_path)
    except Exception:
        logger.exception("Could not generate public profile picture URL for %s", avatar_path)
        return None


def serialize_profile(account: dict) -> dict:
    claimed_player = account.get(TABLE_NAMES.PLAYERS.value)
    return {
        "username": account["username"],
        "contact_email": account.get("contact_email"),
        "avatar_url": profile_avatar_url(account.get("avatar_path")),
        "scoreboard_initials": account.get("scoreboard_initials"),
        "scoreboard_color": account.get("scoreboard_color"),
        "show_avatar_on_scoreboard": account.get("show_avatar_on_scoreboard", False),
        "claimed_player_id": account.get("claimed_player_id"),
        "claimed_player_name": claimed_player["player_name"] if claimed_player else None,
    }


def load_profile(user_id: str) -> dict:
    account_response = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .select(f"username, contact_email, avatar_path, scoreboard_initials, scoreboard_color, show_avatar_on_scoreboard, claimed_player_id, {TABLE_NAMES.PLAYERS.value}(player_name)")
        .eq("user_id", user_id)
        .execute()
    )
    if not account_response.data:
        raise HTTPException(status_code=404, detail="Account not found")
    return account_response.data[0]


def validate_profile_update(payload: ProfileUpdate, user_id: str) -> dict:
    supplied_fields = payload.model_fields_set
    if not supplied_fields:
        raise HTTPException(status_code=400, detail="Profile update cannot be empty")

    update: dict = {}

    if "username" in supplied_fields:
        username = payload.username.strip() if payload.username is not None else ""
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")
        if not USERNAME_PATTERN.match(username):
            raise HTTPException(status_code=400, detail="Username can only contain letters, numbers, periods, hyphens, and underscores (no spaces)")

        existing = (
            supabase.table(TABLE_NAMES.ACCOUNTS.value)
            .select("user_id")
            .ilike("username", username)
            .neq("user_id", user_id)
            .execute()
        )
        if existing.data:
            raise HTTPException(status_code=409, detail="Username is already taken")
        update["username"] = username

    if "contact_email" in supplied_fields:
        contact_email = payload.contact_email.strip() if payload.contact_email is not None else ""
        if not contact_email:
            update["contact_email"] = None
        elif not EMAIL_PATTERN.match(contact_email):
            raise HTTPException(status_code=400, detail="Invalid email address")
        else:
            update["contact_email"] = contact_email

    if "scoreboard_initials" in supplied_fields:
        initials = payload.scoreboard_initials.strip().upper() if payload.scoreboard_initials is not None else ""
        if not initials:
            update["scoreboard_initials"] = None
        elif not INITIALS_PATTERN.match(initials):
            raise HTTPException(status_code=400, detail="Scoreboard initials must be 1-4 letters or digits")
        else:
            update["scoreboard_initials"] = initials

    if "scoreboard_color" in supplied_fields:
        color = payload.scoreboard_color.strip().upper() if payload.scoreboard_color is not None else ""
        if not color:
            update["scoreboard_color"] = None
        elif not COLOR_PATTERN.match(color):
            raise HTTPException(status_code=400, detail="Scoreboard color must be a hex color like #667EEA")
        else:
            update["scoreboard_color"] = color

    if "show_avatar_on_scoreboard" in supplied_fields:
        update["show_avatar_on_scoreboard"] = bool(payload.show_avatar_on_scoreboard)

    if not update:
        raise HTTPException(status_code=400, detail="Profile update cannot be empty")
    return update


def detect_image_type(data: bytes, declared_content_type: str | None) -> tuple[str, str]:
    content_type = (declared_content_type or "").split(";")[0].strip().lower()
    allowed_content_types = {"image/jpeg", "image/png", "image/webp"}
    if content_type not in allowed_content_types:
        raise HTTPException(status_code=415, detail="Unsupported profile picture type")

    detected: tuple[str, str] | None = None
    if data.startswith(b"\xff\xd8\xff"):
        detected = ("image/jpeg", "jpg")
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = ("image/png", "png")
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        detected = ("image/webp", "webp")

    if detected is None or detected[0] != content_type:
        raise HTTPException(status_code=415, detail="Unsupported profile picture type")
    return detected


def delete_profile_picture_object(path: str | None) -> None:
    if not path:
        return
    try:
        supabase.storage.from_(PROFILE_BUCKET).remove([path])
    except Exception:
        logger.exception("Could not delete profile picture object %s", path)


def get_scoreboard_preferences(player_ids: set[int]) -> dict[int, dict]:
    if not player_ids:
        return {}
    response = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .select("claimed_player_id, scoreboard_initials, scoreboard_color, avatar_path, show_avatar_on_scoreboard")
        .in_("claimed_player_id", list(player_ids))
        .execute()
    )
    return {
        row["claimed_player_id"]: {
            "scoreboard_initials": row.get("scoreboard_initials"),
            "scoreboard_color": row.get("scoreboard_color"),
            "scoreboard_avatar_url": profile_avatar_url(row.get("avatar_path")) if row.get("show_avatar_on_scoreboard") else None,
        }
        for row in response.data
        if row.get("claimed_player_id") is not None
    }


def enrich_players_with_scoreboard_preferences(players: list[dict]) -> None:
    preferences = get_scoreboard_preferences({player["player_id"] for player in players})
    for player in players:
        preference = preferences.get(player["player_id"], {})
        player["scoreboard_initials"] = preference.get("scoreboard_initials")
        player["scoreboard_color"] = preference.get("scoreboard_color")
        player["scoreboard_avatar_url"] = preference.get("scoreboard_avatar_url")


def _empty_stats(player_id: int) -> dict:
    return {
        "player_id": player_id,
        "player_name": "",
        "games_played": 0,
        "picker_rounds": 0,
        "picker_wins": 0,
        "partner_rounds": 0,
        "partner_wins": 0,
        "picker_schneider_wins": 0,
        "lone_wolf_count": 0,
        "overconfident_count": 0,
        "overconfident_last_created": None,
        "punching_bag_count": 0,
    }


def aggregate_player_stats() -> dict[int, dict]:
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .select(
            f"game_id, {TABLE_NAMES.PLAYERSXGAMES.value}(player_id), "
            f"{TABLE_NAMES.ROUNDS.value}(round_result, no_schneider, no_partner, created, "
            f"{TABLE_NAMES.PLAYERROUNDSCORE.value}(player_id, player_role))"
        )
        .eq("is_completed", True)
        .execute()
    )
    stats: dict[int, dict] = {}

    def bucket(player_id: int) -> dict:
        if player_id not in stats:
            stats[player_id] = _empty_stats(player_id)
        return stats[player_id]

    for game in response.data:
        for player_game in game.get(TABLE_NAMES.PLAYERSXGAMES.value, []):
            bucket(player_game["player_id"])["games_played"] += 1

        for round_row in game.get(TABLE_NAMES.ROUNDS.value, []):
            round_result = round_row.get("round_result")
            is_picker_win = round_result == ROUND_RESULTS.PICKER_WIN.value
            is_picker_loss = round_result == ROUND_RESULTS.PICKER_LOSS.value
            no_schneider = bool(round_row.get("no_schneider"))
            no_partner = bool(round_row.get("no_partner"))
            round_created = round_row.get("created")
            for player_score in round_row.get(TABLE_NAMES.PLAYERROUNDSCORE.value, []):
                role = player_score.get("player_role")
                stats_for_player = bucket(player_score["player_id"])
                if role == "Picker":
                    stats_for_player["picker_rounds"] += 1
                    if is_picker_win:
                        stats_for_player["picker_wins"] += 1
                    if no_schneider and is_picker_win:
                        stats_for_player["picker_schneider_wins"] += 1
                    if no_schneider and is_picker_loss:
                        stats_for_player["punching_bag_count"] += 1
                    if no_partner:
                        stats_for_player["lone_wolf_count"] += 1
                        if is_picker_loss:
                            stats_for_player["overconfident_count"] += 1
                            last_created = stats_for_player["overconfident_last_created"]
                            if round_created and (last_created is None or round_created > last_created):
                                stats_for_player["overconfident_last_created"] = round_created
                elif role == "Partner":
                    stats_for_player["partner_rounds"] += 1
                    if is_picker_win:
                        stats_for_player["partner_wins"] += 1
                    if no_schneider and is_picker_loss:
                        stats_for_player["punching_bag_count"] += 1
                elif role == "Opponent":
                    if no_schneider and is_picker_win:
                        stats_for_player["punching_bag_count"] += 1

    if stats:
        players_response = (
            supabase.table(TABLE_NAMES.PLAYERS.value)
            .select("player_id, player_name")
            .in_("player_id", list(stats.keys()))
            .execute()
        )
        for row in players_response.data:
            stats[row["player_id"]]["player_name"] = row["player_name"]

    return stats


def _select_holder(badge: BadgeDef, stats: dict[int, dict]) -> dict | None:
    candidates = [player_stats for player_stats in stats.values() if badge.eligible(player_stats)]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda player_stats: (
            badge.value(player_stats),
            badge.tiebreak_sample(player_stats),
            *[tiebreaker(player_stats) for tiebreaker in badge.tiebreakers],
            player_stats["games_played"],
            -player_stats["player_id"],
        ),
    )


def recompute_badges() -> None:
    try:
        stats = aggregate_player_stats()
        updated_at = datetime.now(timezone.utc).isoformat()
        rows = []
        for badge in BADGE_DEFS:
            holder = _select_holder(badge, stats)
            if holder is None:
                rows.append({
                    "badge_key": badge.key,
                    "holder_player_id": None,
                    "value": None,
                    "display_value": None,
                    "sample_size": None,
                    "updated_at": updated_at,
                })
                continue
            value = badge.value(holder)
            rows.append({
                "badge_key": badge.key,
                "holder_player_id": holder["player_id"],
                "value": value,
                "display_value": badge.format(value),
                "sample_size": int(badge.tiebreak_sample(holder)),
                "updated_at": updated_at,
            })
        supabase.table(TABLE_NAMES.BADGES.value).upsert(rows, on_conflict="badge_key").execute()
    except Exception:
        logger.exception("recompute_badges failed")


def _game_is_completed(game_id: int) -> bool:
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .select("is_completed")
        .eq("game_id", game_id)
        .execute()
    )
    return bool(response.data and response.data[0]["is_completed"])


@app.on_event("startup")
def _seed_badges_on_startup():
    recompute_badges()


class GameConnectionManager:
    def __init__(self):
        self.connections: dict[int, set[WebSocket]] = {}
        self.list_connections: set[WebSocket] = set()

    async def connect(self, game_id: int, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(game_id, set()).add(websocket)

    def disconnect(self, game_id: int, websocket: WebSocket):
        conns = self.connections.get(game_id)
        if conns:
            conns.discard(websocket)
            if not conns:
                del self.connections[game_id]

    async def broadcast(self, game_id: int):
        for ws in list(self.connections.get(game_id, [])):
            try:
                await ws.send_json({"type": "game_updated", "game_id": game_id})
            except Exception:
                self.disconnect(game_id, ws)

    async def connect_list(self, websocket: WebSocket):
        await websocket.accept()
        self.list_connections.add(websocket)

    def disconnect_list(self, websocket: WebSocket):
        self.list_connections.discard(websocket)

    async def broadcast_list(self):
        for ws in list(self.list_connections):
            try:
                await ws.send_json({"type": "games_list_updated"})
            except Exception:
                self.disconnect_list(ws)


game_connections = GameConnectionManager()


@app.websocket("/ws/games/{game_id}")
async def game_updates_ws(websocket: WebSocket, game_id: int):
    origin = websocket.headers.get("origin")
    if origin and origin not in allowed_origins:
        await websocket.close(code=1008)
        return
    await game_connections.connect(game_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        game_connections.disconnect(game_id, websocket)


@app.websocket("/ws/games")
async def games_list_ws(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin not in allowed_origins:
        await websocket.close(code=1008)
        return
    await game_connections.connect_list(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        game_connections.disconnect_list(websocket)


@app.get("/", tags=["Default"])
def read_root():
    return {"Bruh": "You made a request to the base endpoint. You probably don't know what you're doing huh"}

@app.get("/games", tags=["Game Management"])
def get_games():
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .select(f"*, {TABLE_NAMES.PLAYERSXGAMES.value}({TABLE_NAMES.PLAYERS.value}(*)), Rounds(*, {TABLE_NAMES.PLAYERROUNDSCORE.value}(*))")
        .order("game_datetime", desc=True)
        .execute()
    )
    player_ids: set[int] = set()
    for game in response.data:
        for player_game in game.get(TABLE_NAMES.PLAYERSXGAMES.value, []):
            player = player_game.get(TABLE_NAMES.PLAYERS.value)
            if player:
                player_ids.add(player["player_id"])

    preferences = get_scoreboard_preferences(player_ids)
    for game in response.data:
        for player_game in game.get(TABLE_NAMES.PLAYERSXGAMES.value, []):
            player = player_game.get(TABLE_NAMES.PLAYERS.value)
            if not player:
                continue
            preference = preferences.get(player["player_id"], {})
            player["scoreboard_initials"] = preference.get("scoreboard_initials")
            player["scoreboard_color"] = preference.get("scoreboard_color")
            player["scoreboard_avatar_url"] = preference.get("scoreboard_avatar_url")

    return response.data

@app.post("/games", tags=["Game Management"])
async def create_game(num_players: int = Body(...), player_ids: list[int] = Body(...), user_id: str = Depends(get_current_user_id)):
    game_response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .insert({"num_players": num_players, "game_datetime": datetime.now(timezone.utc).isoformat()})
        .execute()
    )
    game = game_response.data[0]
    game_id = game["game_id"]

    player_x_game_rows = [{"player_id": pid, "game_id": game_id} for pid in player_ids]
    supabase.table(TABLE_NAMES.PLAYERSXGAMES.value).insert(player_x_game_rows).execute()

    await game_connections.broadcast_list()
    return game

@app.delete("/games/{game_id}", tags=["Game Management"])
async def delete_game(game_id, user_id: str = Depends(get_current_user_id)):
    await game_connections.broadcast(int(game_id))

    rounds_response = (
        supabase.table(TABLE_NAMES.ROUNDS.value)
        .select("round_id")
        .eq("game_id", game_id)
        .execute()
    )

    for round_row in rounds_response.data:
        supabase.table(TABLE_NAMES.PLAYERROUNDSCORE.value).delete().eq("round_id", round_row["round_id"]).execute()

    supabase.table(TABLE_NAMES.ROUNDS.value).delete().eq("game_id", game_id).execute()
    supabase.table(TABLE_NAMES.PLAYERSXGAMES.value).delete().eq("game_id", game_id).execute()

    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .delete()
        .eq("game_id", game_id)
        .execute()
    )
    await game_connections.broadcast_list()
    recompute_badges()
    return response.data

@app.patch("/games/{game_id}/status", tags=["Game Management"])
async def set_game_status(game_id, is_completed: bool = Body(..., embed=True), user_id: str = Depends(get_current_user_id)):
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .update({"is_completed": is_completed})
        .eq("game_id", game_id)
        .execute()
    )
    await game_connections.broadcast(int(game_id))
    await game_connections.broadcast_list()
    recompute_badges()
    return response.data[0]

@app.patch("/games/{game_id}/name", tags=["Game Management"])
async def set_game_name(game_id, game_name: str | None = Body(None, embed=True), user_id: str = Depends(get_current_user_id)):
    normalized_name = game_name.strip() if game_name else None
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .update({"game_name": normalized_name or None})
        .eq("game_id", game_id)
        .execute()
    )
    await game_connections.broadcast(int(game_id))
    await game_connections.broadcast_list()
    return response.data[0]

@app.patch("/games/{game_id}/complete", tags=["Game Management"])
async def complete_game(game_id, user_id: str = Depends(get_current_user_id)):
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .update({"is_completed": True})
        .eq("game_id", game_id)
        .execute()
    )
    await game_connections.broadcast(int(game_id))
    await game_connections.broadcast_list()
    recompute_badges()
    return response.data[0]

@app.get("/rounds/{game_id}", tags=["Game Management"])
def get_rounds_in_game(game_id):
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .select(f"*, {TABLE_NAMES.ROUNDS.value}(*)")
        .eq("game_id", game_id)
        .execute()
    )
    return response.data

@app.post("/rounds", tags=["Game Management"])
async def create_round(
    game_id: int = Body(...),
    round_number: int = Body(...),
    round_result: ROUND_RESULTS = Body(...),
    no_schneider: bool = Body(False),
    no_partner: bool = Body(False),
    no_trick: bool = Body(False),
    player_scores: list = Body(...),
    user_id: str = Depends(get_current_user_id)
):
    round_response = (
        supabase.table(TABLE_NAMES.ROUNDS.value)
        .insert({"game_id": game_id, "round_number": round_number, "round_result": round_result.value, "no_schneider": no_schneider, "no_partner": no_partner, "no_trick": no_trick})
        .execute()
    )
    created_round = round_response.data[0]
    round_id = created_round["round_id"]

    score_rows = [
        {"round_id": round_id, "player_id": ps["player_id"], "player_role": ps["player_role"], "point_delta": ps["point_delta"]}
        for ps in player_scores
    ]
    supabase.table(TABLE_NAMES.PLAYERROUNDSCORE.value).insert(score_rows).execute()

    await game_connections.broadcast(game_id)
    await game_connections.broadcast_list()
    if _game_is_completed(game_id):
        recompute_badges()
    return created_round

@app.patch("/rounds/{round_id}", tags=["Game Management"])
async def update_round(
    round_id,
    round_result: ROUND_RESULTS = Body(...),
    no_schneider: bool = Body(False),
    no_partner: bool = Body(False),
    no_trick: bool = Body(False),
    player_scores: list = Body(...),
    user_id: str = Depends(get_current_user_id)
):
    round_response = (
        supabase.table(TABLE_NAMES.ROUNDS.value)
        .update({"round_result": round_result.value, "no_schneider": no_schneider, "no_partner": no_partner, "no_trick": no_trick})
        .eq("round_id", round_id)
        .execute()
    )
    updated_round = round_response.data[0]

    supabase.table(TABLE_NAMES.PLAYERROUNDSCORE.value).delete().eq("round_id", round_id).execute()

    score_rows = [
        {"round_id": round_id, "player_id": ps["player_id"], "player_role": ps["player_role"], "point_delta": ps["point_delta"]}
        for ps in player_scores
    ]
    supabase.table(TABLE_NAMES.PLAYERROUNDSCORE.value).insert(score_rows).execute()

    await game_connections.broadcast(int(updated_round["game_id"]))
    await game_connections.broadcast_list()
    if _game_is_completed(updated_round["game_id"]):
        recompute_badges()
    return updated_round

@app.delete("/rounds/{round_id}", tags=["Game Management"])
async def delete_round(round_id, user_id: str = Depends(get_current_user_id)):
    round_lookup = (
        supabase.table(TABLE_NAMES.ROUNDS.value)
        .select("game_id, round_number")
        .eq("round_id", round_id)
        .execute()
    )
    if not round_lookup.data:
        return []
    game_id = round_lookup.data[0]["game_id"]
    deleted_round_number = round_lookup.data[0]["round_number"]

    supabase.table(TABLE_NAMES.PLAYERROUNDSCORE.value).delete().eq("round_id", round_id).execute()
    response = (
        supabase.table(TABLE_NAMES.ROUNDS.value)
        .delete()
        .eq("round_id", round_id)
        .execute()
    )

    later_rounds = (
        supabase.table(TABLE_NAMES.ROUNDS.value)
        .select("round_id, round_number")
        .eq("game_id", game_id)
        .gt("round_number", deleted_round_number)
        .execute()
    )
    for round_row in later_rounds.data:
        supabase.table(TABLE_NAMES.ROUNDS.value).update({"round_number": round_row["round_number"] - 1}).eq("round_id", round_row["round_id"]).execute()

    await game_connections.broadcast(int(game_id))
    await game_connections.broadcast_list()
    if _game_is_completed(game_id):
        recompute_badges()
    return response.data

@app.get("/players", tags=["Player Management"])
def get_players():
    response = (
        supabase.table(TABLE_NAMES.PLAYERS.value)
        .select()
        .execute()
    )
    enrich_players_with_scoreboard_preferences(response.data)
    return response.data


@app.get("/badges", tags=["Badge Management"])
def get_badges():
    standings = supabase.table(TABLE_NAMES.BADGES.value).select("*").execute()
    standings_by_key = {row["badge_key"]: row for row in standings.data}
    holder_ids = {row["holder_player_id"] for row in standings.data if row.get("holder_player_id")}
    players_by_id = {}
    if holder_ids:
        players_response = (
            supabase.table(TABLE_NAMES.PLAYERS.value)
            .select("player_id, player_name")
            .in_("player_id", list(holder_ids))
            .execute()
        )
        players_by_id = {player["player_id"]: player for player in players_response.data}
        enrich_players_with_scoreboard_preferences(list(players_by_id.values()))

    result = []
    for badge in BADGE_DEFS:
        standing = standings_by_key.get(badge.key)
        holder_id = standing["holder_player_id"] if standing else None
        holder = players_by_id.get(holder_id) if holder_id else None
        result.append({
            "badge_key": badge.key,
            "title": badge.title,
            "description": badge.description,
            "value": standing["value"] if standing else None,
            "display_value": standing["display_value"] if standing else None,
            "sample_size": standing["sample_size"] if standing else None,
            "holder_player_id": holder_id,
            "holder_player_name": holder["player_name"] if holder else None,
            "holder_scoreboard_initials": holder["scoreboard_initials"] if holder else None,
            "holder_scoreboard_color": holder["scoreboard_color"] if holder else None,
            "holder_scoreboard_avatar_url": holder["scoreboard_avatar_url"] if holder else None,
        })
    return result

@app.post("/players", tags=["Player Management"])
def create_player(player_name: str, user_id: str = Depends(get_current_user_id)):
    response = (
        supabase.table(TABLE_NAMES.PLAYERS.value)
        .insert({"player_name": player_name})
        .execute()
    )
    player = response.data[0]
    player["scoreboard_initials"] = None
    player["scoreboard_color"] = None
    player["scoreboard_avatar_url"] = None
    return player

@app.post("/players/{player_id}/claim", tags=["Player Management"])
async def claim_player(player_id: int, user_id: str = Depends(get_current_user_id)):
    player_lookup = (
        supabase.table(TABLE_NAMES.PLAYERS.value)
        .select("player_id")
        .eq("player_id", player_id)
        .execute()
    )
    if not player_lookup.data:
        raise HTTPException(status_code=404, detail="Player not found")

    claimed_by_other = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .select("user_id")
        .eq("claimed_player_id", player_id)
        .neq("user_id", user_id)
        .execute()
    )
    if claimed_by_other.data:
        raise HTTPException(status_code=409, detail="This player is already claimed by another account")

    current_account = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .select("claimed_player_id")
        .eq("user_id", user_id)
        .execute()
    )
    current_claimed_player_id = current_account.data[0]["claimed_player_id"] if current_account.data else None
    if current_claimed_player_id is not None and current_claimed_player_id != player_id:
        raise HTTPException(status_code=409, detail="You already have a claimed player — unclaim it first")

    response = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .update({"claimed_player_id": player_id})
        .eq("user_id", user_id)
        .execute()
    )
    await game_connections.broadcast_list()
    return response.data[0]

@app.post("/players/{player_id}/unclaim", tags=["Player Management"])
async def unclaim_player(player_id: int, user_id: str = Depends(get_current_user_id)):
    current_account = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .select("claimed_player_id")
        .eq("user_id", user_id)
        .execute()
    )
    if not current_account.data or current_account.data[0]["claimed_player_id"] != player_id:
        raise HTTPException(status_code=403, detail="You have not claimed this player")

    response = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .update({"claimed_player_id": None})
        .eq("user_id", user_id)
        .execute()
    )
    await game_connections.broadcast_list()
    return response.data[0]

@app.get("/auth/profile", tags=["Auth"])
def get_profile(user_id: str = Depends(get_current_user_id)):
    return serialize_profile(load_profile(user_id))

@app.patch("/auth/profile", tags=["Auth"])
async def update_profile(payload: ProfileUpdate, user_id: str = Depends(get_current_user_id)):
    existing_profile = load_profile(user_id)
    update = validate_profile_update(payload, user_id)

    try:
        response = (
            supabase.table(TABLE_NAMES.ACCOUNTS.value)
            .update(update)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        message = str(e)
        if "Accounts_username_lower_idx" in message or "duplicate key" in message.lower() or "unique" in message.lower():
            raise HTTPException(status_code=409, detail="Username is already taken")
        raise

    if not response.data:
        raise HTTPException(status_code=404, detail="Account not found")

    preference_changed = any(
        field in update and update[field] != existing_profile.get(field)
        for field in ("scoreboard_initials", "scoreboard_color", "show_avatar_on_scoreboard")
    )
    if preference_changed:
        await game_connections.broadcast_list()

    return serialize_profile(load_profile(user_id))

@app.post("/auth/profile/picture", tags=["Auth"])
async def upload_profile_picture(file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):
    data = await file.read(MAX_PROFILE_PICTURE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Profile picture file is empty")
    if len(data) > MAX_PROFILE_PICTURE_BYTES:
        raise HTTPException(status_code=413, detail="Profile picture must be 2 MiB or smaller")

    content_type, extension = detect_image_type(data, file.content_type)
    current_profile = load_profile(user_id)
    old_avatar_path = current_profile.get("avatar_path")
    new_avatar_path = f"{user_id}/{uuid4()}.{extension}"

    try:
        supabase.storage.from_(PROFILE_BUCKET).upload(
            new_avatar_path,
            data,
            file_options={"content-type": content_type, "upsert": "false"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not upload profile picture: {e}")

    try:
        response = (
            supabase.table(TABLE_NAMES.ACCOUNTS.value)
            .update({"avatar_path": new_avatar_path})
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        delete_profile_picture_object(new_avatar_path)
        raise

    if not response.data:
        delete_profile_picture_object(new_avatar_path)
        raise HTTPException(status_code=404, detail="Account not found")

    delete_profile_picture_object(old_avatar_path)
    if current_profile.get("show_avatar_on_scoreboard"):
        await game_connections.broadcast_list()
    return serialize_profile(load_profile(user_id))

@app.delete("/auth/profile/picture", tags=["Auth"])
async def delete_profile_picture(user_id: str = Depends(get_current_user_id)):
    current_profile = load_profile(user_id)
    old_avatar_path = current_profile.get("avatar_path")
    response = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .update({"avatar_path": None})
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Account not found")

    delete_profile_picture_object(old_avatar_path)
    if current_profile.get("show_avatar_on_scoreboard"):
        await game_connections.broadcast_list()
    return serialize_profile(load_profile(user_id))

@app.post("/auth/signup", tags=["Auth"])
def signup(username: str = Body(...), password: str = Body(...), invite_code: str = Body(...), email: str | None = Body(None)):
    if invite_code != os.environ.get("SIGNUP_INVITE_CODE"):
        raise HTTPException(status_code=403, detail="Invalid invite code")

    username = username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not USERNAME_PATTERN.match(username):
        raise HTTPException(status_code=400, detail="Username can only contain letters, numbers, periods, hyphens, and underscores (no spaces)")

    contact_email = email.strip() if email else None
    if contact_email and not EMAIL_PATTERN.match(contact_email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    existing = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .select("user_id")
        .ilike("username", username)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="Username is already taken")

    synthetic_email = f"{username.lower()}@{SYNTHETIC_EMAIL_DOMAIN}"

    try:
        created_user = supabase.auth.admin.create_user({
            "email": synthetic_email,
            "password": password,
            "email_confirm": True,
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not create account: {e}")

    user_id = created_user.user.id

    account_response = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .insert({"user_id": user_id, "username": username, "email": synthetic_email, "contact_email": contact_email})
        .execute()
    )
    account = account_response.data[0]

    try:
        sign_in_response = create_auth_client().auth.sign_in_with_password({"email": synthetic_email, "password": password})
    except Exception:
        raise HTTPException(status_code=500, detail="Account created, but automatic sign-in failed — please log in")

    session = sign_in_response.session
    profile = serialize_profile(account)
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at,
        **profile,
    }

@app.post("/auth/login", tags=["Auth"])
def login(username: str = Body(...), password: str = Body(...)):
    account_lookup = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .select(f"*, {TABLE_NAMES.PLAYERS.value}(player_name)")
        .ilike("username", username.strip())
        .execute()
    )
    if not account_lookup.data:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    account = account_lookup.data[0]

    try:
        sign_in_response = create_auth_client().auth.sign_in_with_password({
            "email": account["email"],
            "password": password,
        })
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    session = sign_in_response.session
    if not session:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    profile = serialize_profile(account)
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at,
        **profile,
    }

@app.post("/auth/refresh", tags=["Auth"])
def refresh_session(refresh_token: str = Body(..., embed=True)):
    try:
        refresh_response = create_auth_client().auth.refresh_session(refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    session = refresh_response.session
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at,
    }

@app.post("/auth/logout", tags=["Auth"])
def logout(authorization: str = Header(None), user_id: str = Depends(get_current_user_id)):
    token = authorization.removeprefix("Bearer ").strip()
    try:
        create_auth_client().auth.admin.sign_out(token)
    except Exception:
        pass
    return {"status": "ok"}

@app.get("/auth/me", tags=["Auth"])
def get_me(user_id: str = Depends(get_current_user_id)):
    return serialize_profile(load_profile(user_id))
