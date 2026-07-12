import os
from dotenv import load_dotenv

from enum import Enum
from datetime import datetime

from fastapi import FastAPI
from supabase import create_client, Client

class TABLE_NAMES(Enum):
    GAMES = "Games"
    PLAYERS = "Players"
    PLAYERSXGAMES = "Players_X_Games"
    PLAYERROUNDSCORE = "PlayerRoundScore"
    ROUNDS = "Rounds"



tags_metadata = [
    {"name": "Default", "description": "idk if i even need this"},
    {"name": "Game Management", "description": "do stuff to da games"},
]

load_dotenv()

app = FastAPI(openapi_tags=tags_metadata)
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
        .select()
        .execute()
    )
    return response

@app.post("/games/{game_id}", tags=["Game Management"])
def insert_game(game_id):
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .insert({"game_id": game_id, "game_datetime": datetime.now().isoformat()})
        .execute()
    )
    return response

@app.delete("/games/{game_id}", tags=["Game Management"])
def delete_game(game_id):
    response = (
        supabase.table(TABLE_NAMES.GAMES.value)
        .delete()
        .eq("game_id", game_id)
        .execute()
    )
    return response