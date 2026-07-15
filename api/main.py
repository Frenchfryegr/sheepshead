import os
import re
from dotenv import load_dotenv

from enum import Enum
from datetime import datetime, timezone

from fastapi import FastAPI, Body, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

class TABLE_NAMES(Enum):
    GAMES = "Games"
    PLAYERS = "Players"
    PLAYERSXGAMES = "Players_X_Games"
    PLAYERROUNDSCORE = "PlayerRoundScore"
    ROUNDS = "Rounds"
    ACCOUNTS = "Accounts"

class ROUND_RESULTS(Enum):
    PICKER_WIN = "Picker Win"
    PICKER_LOSS = "Picker Loss"
    LEASTER = "Leaster"

SYNTHETIC_EMAIL_DOMAIN = "accounts.sheepsheadscores.internal"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


tags_metadata = [
    {"name": "Default", "description": "idk if i even need this"},
    {"name": "Game Management", "description": "do stuff to da games"},
    {"name": "Player Management", "description": "do stuff to da playas"},
    {"name": "Auth", "description": "accounts, login, and player claiming"},

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
    return response.data

@app.post("/games", tags=["Game Management"])
def create_game(num_players: int = Body(...), player_ids: list[int] = Body(...), user_id: str = Depends(get_current_user_id)):
    game_response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .insert({"num_players": num_players, "game_datetime": datetime.now(timezone.utc).isoformat()})
        .execute()
    )
    game = game_response.data[0]
    game_id = game["game_id"]

    player_x_game_rows = [{"player_id": pid, "game_id": game_id} for pid in player_ids]
    supabase.table(TABLE_NAMES.PLAYERSXGAMES.value).insert(player_x_game_rows).execute()

    return game

@app.delete("/games/{game_id}", tags=["Game Management"])
def delete_game(game_id, user_id: str = Depends(get_current_user_id)):
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
    return response.data

@app.patch("/games/{game_id}/status", tags=["Game Management"])
def set_game_status(game_id, is_completed: bool = Body(..., embed=True), user_id: str = Depends(get_current_user_id)):
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .update({"is_completed": is_completed})
        .eq("game_id", game_id)
        .execute()
    )
    return response.data[0]

@app.patch("/games/{game_id}/complete", tags=["Game Management"])
def complete_game(game_id, user_id: str = Depends(get_current_user_id)):
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .update({"is_completed": True})
        .eq("game_id", game_id)
        .execute()
    )
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
def create_round(
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

    return created_round

@app.patch("/rounds/{round_id}", tags=["Game Management"])
def update_round(
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

    return updated_round

@app.delete("/rounds/{round_id}", tags=["Game Management"])
def delete_round(round_id, user_id: str = Depends(get_current_user_id)):
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

    return response.data

@app.get("/players", tags=["Player Management"])
def get_players():
    response = (
        supabase.table(TABLE_NAMES.PLAYERS.value)
        .select()
        .execute()
    )
    return response.data

@app.post("/players", tags=["Player Management"])
def create_player(player_name: str, user_id: str = Depends(get_current_user_id)):
    response = (
        supabase.table(TABLE_NAMES.PLAYERS.value)
        .insert({"player_name": player_name})
        .execute()
    )
    return response.data[0]

@app.post("/players/{player_id}/claim", tags=["Player Management"])
def claim_player(player_id: int, user_id: str = Depends(get_current_user_id)):
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
    return response.data[0]

@app.post("/players/{player_id}/unclaim", tags=["Player Management"])
def unclaim_player(player_id: int, user_id: str = Depends(get_current_user_id)):
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
    return response.data[0]

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
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at,
        "username": account["username"],
        "claimed_player_id": account["claimed_player_id"],
        "claimed_player_name": None,
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

    claimed_player = account.get(TABLE_NAMES.PLAYERS.value)
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": session.expires_at,
        "username": account["username"],
        "claimed_player_id": account["claimed_player_id"],
        "claimed_player_name": claimed_player["player_name"] if claimed_player else None,
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
    account_response = (
        supabase.table(TABLE_NAMES.ACCOUNTS.value)
        .select(f"username, claimed_player_id, {TABLE_NAMES.PLAYERS.value}(player_name)")
        .eq("user_id", user_id)
        .execute()
    )
    if not account_response.data:
        raise HTTPException(status_code=404, detail="Account not found")
    account = account_response.data[0]
    claimed_player = account.get(TABLE_NAMES.PLAYERS.value)
    return {
        "username": account["username"],
        "claimed_player_id": account["claimed_player_id"],
        "claimed_player_name": claimed_player["player_name"] if claimed_player else None,
    }