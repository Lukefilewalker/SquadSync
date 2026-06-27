from pathlib import Path
import sqlite3

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).parent
DATA_DIR = Path("/app/data")
if not DATA_DIR.exists():
    DATA_DIR = APP_DIR.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "gamenight.db"

app = FastAPI(title="Game Night Finder")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

STATUSES = ["Installed", "Owned", "Game Pass", "Not Owned", "Unknown"]
ACCESS_STATUSES = {"Installed", "Owned", "Game Pass"}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL UNIQUE,
                crossplay TEXT DEFAULT 'Unknown',
                min_players INTEGER DEFAULT 1,
                max_players INTEGER DEFAULT 4,
                tags TEXT DEFAULT '',
                notes TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS player_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                game_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Unknown',
                platform TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(player_id, game_id),
                FOREIGN KEY(player_id) REFERENCES players(id),
                FOREIGN KEY(game_id) REFERENCES games(id)
            );
            """
        )

        players = [
            "Steven",
            "Nick Dragswolf",
            "Anthony Folden",
            "Ray Holt",
            "Derek Uran",
            "Kenny Hissong",
        ]
        for name in players:
            conn.execute("INSERT OR IGNORE INTO players(name) VALUES (?)", (name,))

        starter_games = [
            ("Halo Infinite", "Yes", 1, 24, "FPS,PvP,Free-to-play", "PC/Xbox crossplay"),
            ("Sea of Thieves", "Yes", 1, 4, "Co-op,PvP,Game Pass", "Good Xbox/PC option"),
            ("Fortnite", "Yes", 1, 4, "Free-to-play,Battle Royale", "Easy cross-platform fallback"),
            ("Deep Rock Galactic", "Partial", 1, 4, "Co-op,Game Pass", "Check store compatibility"),
            ("Valheim", "Yes", 1, 10, "Survival,Co-op", "Crossplay support depends on setup"),
            ("Minecraft", "Partial", 1, 8, "Survival,Co-op", "Bedrock is crossplay, Java is not"),
        ]
        for title, crossplay, min_p, max_p, tags, notes in starter_games:
            conn.execute(
                """
                INSERT OR IGNORE INTO games(title, crossplay, min_players, max_players, tags, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, crossplay, min_p, max_p, tags, notes),
            )

        conn.commit()


@app.on_event("startup")
def startup():
    init_db()


def get_players(conn):
    return conn.execute("SELECT * FROM players ORDER BY name").fetchall()


def get_games(conn):
    return conn.execute("SELECT * FROM games ORDER BY title").fetchall()


def get_matrix(conn):
    players = get_players(conn)
    games = get_games(conn)

    rows = []
    for game in games:
        statuses = {}
        for player in players:
            pg = conn.execute(
                """
                SELECT status, platform, notes
                FROM player_games
                WHERE player_id = ? AND game_id = ?
                """,
                (player["id"], game["id"]),
            ).fetchone()
            statuses[player["id"]] = dict(pg) if pg else {
                "status": "Unknown",
                "platform": "",
                "notes": "",
            }
        rows.append({"game": game, "statuses": statuses})
    return players, rows


def classify_game(status_values):
    total = len(status_values)
    installed = sum(1 for s in status_values if s == "Installed")
    accessible = sum(1 for s in status_values if s in ACCESS_STATUSES)
    unknown = sum(1 for s in status_values if s == "Unknown")
    not_owned = sum(1 for s in status_values if s == "Not Owned")

    if installed == total:
        return "Ready tonight"
    if accessible == total and installed >= total - 2:
        return "One download away"
    if accessible == total:
        return "Everyone has access"
    if not_owned > 0:
        return "Needs purchase"
    if unknown > 0:
        return "Unknown"
    return "Mixed"


@app.get("/")
def dashboard(request: Request):
    with db() as conn:
        players, rows = get_matrix(conn)
        buckets = {
            "Ready tonight": [],
            "One download away": [],
            "Everyone has access": [],
            "Needs purchase": [],
            "Unknown": [],
            "Mixed": [],
        }

        for row in rows:
            status_values = [row["statuses"][p["id"]]["status"] for p in players]
            bucket = classify_game(status_values)
            buckets[bucket].append(row)

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "players": players,
                "rows": rows,
                "buckets": buckets,
            },
        )


@app.get("/games")
def games(request: Request):
    with db() as conn:
        players, rows = get_matrix(conn)
        return templates.TemplateResponse(
            "games.html",
            {
                "request": request,
                "players": players,
                "rows": rows,
                "statuses": STATUSES,
            },
        )


@app.post("/games/add")
def add_game(
    title: str = Form(...),
    crossplay: str = Form("Unknown"),
    min_players: int = Form(1),
    max_players: int = Form(4),
    tags: str = Form(""),
    notes: str = Form(""),
):
    with db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO games(title, crossplay, min_players, max_players, tags, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title.strip(), crossplay.strip(), min_players, max_players, tags.strip(), notes.strip()),
        )
        conn.commit()
    return RedirectResponse("/games", status_code=303)


@app.post("/player-game/update")
def update_player_game(
    player_id: int = Form(...),
    game_id: int = Form(...),
    status: str = Form(...),
    platform: str = Form(""),
    notes: str = Form(""),
):
    if status not in STATUSES:
        status = "Unknown"

    with db() as conn:
        conn.execute(
            """
            INSERT INTO player_games(player_id, game_id, status, platform, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(player_id, game_id)
            DO UPDATE SET
                status = excluded.status,
                platform = excluded.platform,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (player_id, game_id, status, platform.strip(), notes.strip()),
        )
        conn.commit()
    return RedirectResponse("/games", status_code=303)


@app.get("/players")
def players(request: Request):
    with db() as conn:
        people = get_players(conn)
        return templates.TemplateResponse(
            "players.html",
            {"request": request, "players": people},
        )


@app.post("/players/add")
def add_player(name: str = Form(...)):
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO players(name) VALUES (?)", (name.strip(),))
        conn.commit()
    return RedirectResponse("/players", status_code=303)
