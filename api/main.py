import os
from dotenv import load_dotenv

from fastapi import FastAPI
from supabase import create_client, Client

load_dotenv()

app = FastAPI()
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"), 
    os.environ.get("SUPABASE_KEY")
)


@app.get("/")
def read_root():
    return {"Bruh": "You made a request to the base endpoint. You prolly don't know what you're doing huh?"}

