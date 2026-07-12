import os
from dotenv import load_dotenv

from enum import Enum
from datetime import datetime

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

class TABLE_NAMES(Enum):
    GAMES = "Games"
    PLAYERS = "Players"
    PLAYERSXGAMES = "Players_X_Games"
    PLAYERROUNDSCORE = "PlayerRoundScore"
    ROUNDS = "Rounds"

class ROUND_RESULTS(Enum):
    PICKER_WIN = "Picker Win"
    PICKER_LOSS = "Picker Loss"
    LEASTER = "Leaster"


tags_metadata = [
    {"name": "Default", "description": "idk if i even need this"},
    {"name": "Game Management", "description": "do stuff to da games"},
    {"name": "Player Management", "description": "do stuff to da playas"},

]

load_dotenv()

app = FastAPI(openapi_tags=tags_metadata)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"), 
    os.environ.get("SUPABASE_KEY")
)


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
def create_game(num_players: int = Body(...), player_ids: list[int] = Body(...)):
    game_response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .insert({"num_players": num_players, "game_datetime": datetime.now().isoformat()})
        .execute()
    )
    game = game_response.data[0]
    game_id = game["game_id"]

    player_x_game_rows = [{"player_id": pid, "game_id": game_id} for pid in player_ids]
    supabase.table(TABLE_NAMES.PLAYERSXGAMES.value).insert(player_x_game_rows).execute()

    return game

@app.delete("/games/{game_id}", tags=["Game Management"])
def delete_game(game_id):
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .delete()
        .eq("game_id", game_id)
        .execute()
    )
    return response.data

@app.patch("/games/{game_id}/complete", tags=["Game Management"])
def complete_game(game_id):
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
    player_scores: list = Body(...)
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
    player_scores: list = Body(...)
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
def delete_round(round_id):
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
def create_player(player_name: str):
    response = (
        supabase.table(TABLE_NAMES.PLAYERS.value)
        .insert({"player_name": player_name})
        .execute()
    )
    return response.data[0]