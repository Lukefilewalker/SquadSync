from pathlib import Path
import os
import sqlite3
from datetime import datetime
import requests
from fastapi.staticfiles import StaticFiles

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).parent
DATA_DIR = Path("/app/data")
if not DATA_DIR.exists():
    DATA_DIR = APP_DIR.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "gamenight.db"

app = FastAPI(title="SquadSync")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

ACCESS_OPTIONS = ["Own", "Game Pass", "Free-to-play", "Shared Library", "No Access", "Unknown"]
INSTALLED_OPTIONS = ["Yes", "No", "Unknown"]
CROSSPLAY_OPTIONS = ["Yes", "No", "Partial", "Possible", "Unknown"]
ACCESS_OK = {"Own", "Game Pass", "Free-to-play", "Shared Library"}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_column_if_missing(conn, table, column, definition):
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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

        add_column_if_missing(conn, "player_games", "access", "TEXT DEFAULT 'Unknown'")
        add_column_if_missing(conn, "player_games", "installed", "TEXT DEFAULT 'Unknown'")
        add_column_if_missing(conn, "player_games", "store", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "games", "pc_xbox_crossplay", "TEXT DEFAULT 'Unknown'")
        add_column_if_missing(conn, "games", "crossplay_notes", "TEXT DEFAULT ''")

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
        player_data = {}
        for player in players:
            pg = conn.execute(
                """
                SELECT access, installed, platform, store, notes
                FROM player_games
                WHERE player_id = ? AND game_id = ?
                """,
                (player["id"], game["id"]),
            ).fetchone()

            player_data[player["id"]] = dict(pg) if pg else {
                "access": "Unknown",
                "installed": "Unknown",
                "platform": "",
                "store": "",
                "notes": "",
            }

        rows.append({"game": game, "player_data": player_data})

    return players, rows


def classify_game(player_values, game):
    total = len(player_values)

    access_count = sum(1 for v in player_values if v["access"] in ACCESS_OK)
    installed_count = sum(1 for v in player_values if v["installed"] == "Yes")
    no_access_count = sum(1 for v in player_values if v["access"] == "No Access")
    unknown_count = sum(
        1 for v in player_values
        if v["access"] == "Unknown" or v["installed"] == "Unknown"
    )

    pc_xbox = game["pc_xbox_crossplay"] or game["crossplay"] or "Unknown"

    if pc_xbox == "No":
        return "Blocked by platform"
    if pc_xbox == "Unknown":
        return "Mixed"
    if installed_count == total and access_count == total and pc_xbox in {"Yes", "Partial"}:
        return "Ready tonight"

    if access_count == total and installed_count < total:
        return "Install needed"

    if access_count == total:
        return "Everyone has access"

    if no_access_count > 0:
        return "Needs purchase/access"

    if unknown_count > 0 or pc_xbox == "Unknown":
        return "Mixed"

    return "Mixed"

def get_recommendations(players, rows):
    recommendations = []

    for row in rows:
        game = row["game"]
        player_data = row["player_data"]

        access_count = 0
        installed_count = 0
        no_access_count = 0
        unknown_count = 0

        for player in players:
            pdata = player_data[player["id"]]

            if pdata["access"] in ACCESS_OK:
                access_count += 1

            if pdata["installed"] == "Yes":
                installed_count += 1

            if pdata["access"] == "No Access":
                no_access_count += 1

            if pdata["access"] == "Unknown" or pdata["installed"] == "Unknown":
                unknown_count += 1

        score = (access_count * 2) + installed_count

        pc_xbox = game["pc_xbox_crossplay"] or game["crossplay"] or "Unknown"
        if pc_xbox == "Yes":
            score += 3
        elif pc_xbox == "Partial":
            score += 1
        elif pc_xbox == "Possible":
            score += 1
        elif pc_xbox == "No":
            score -= 5
        elif pc_xbox == "Unknown":
            score -= 1

        recommendations.append({
            "game": game,
            "score": score,
            "access_count": access_count,
            "installed_count": installed_count,
            "no_access_count": no_access_count,
            "unknown_count": unknown_count,
            "total_players": len(players),
            "pc_xbox_crossplay": pc_xbox,
        })

    return sorted(recommendations, key=lambda item: item["score"], reverse=True)

@app.get("/")
def dashboard(request: Request):
    with db() as conn:
        players, rows = get_matrix(conn)

        buckets = {
            "Ready tonight": [],
            "Install needed": [],
            "Everyone has access": [],
            "Blocked by platform": [],
            "Needs purchase/access": [],
            "Mixed": [],
        }

        for row in rows:
            values = [row["player_data"][p["id"]] for p in players]
            bucket = classify_game(values, row["game"])
            buckets[bucket].append(row)

        recommendations = get_recommendations(players, rows)

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "players": players,
                "rows": rows,
                "buckets": buckets,
                "recommendations": recommendations,
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
                "access_options": ACCESS_OPTIONS,
                "installed_options": INSTALLED_OPTIONS,
                "crossplay_options": CROSSPLAY_OPTIONS,
            },
        )

@app.get("/matrix")
def matrix(request: Request):
    with db() as conn:
        players, rows = get_matrix(conn)

        return templates.TemplateResponse(
            "matrix.html",
            {
                "request": request,
                "players": players,
                "rows": rows,
            },
        )

@app.post("/games/add")
def add_game(
    title: str = Form(...),
    pc_xbox_crossplay: str = Form("Unknown"),
    min_players: int = Form(1),
    max_players: int = Form(4),
    tags: str = Form(""),
    notes: str = Form(""),
    crossplay_notes: str = Form(""),
):
    clean_title = title.strip()

    if pc_xbox_crossplay not in CROSSPLAY_OPTIONS:
        pc_xbox_crossplay = "Unknown"

    metadata = fetch_rawg_metadata(clean_title)

    with db() as conn:
        if metadata:
            conn.execute(
                """
                INSERT OR IGNORE INTO games(
                    title, crossplay, pc_xbox_crossplay, min_players, max_players,
                    tags, notes, crossplay_notes,
                    rawg_id, released, genres, platforms,
                    background_image, description, metadata_synced_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata["title"],
                    pc_xbox_crossplay,
                    pc_xbox_crossplay,
                    min_players,
                    max_players,
                    tags.strip(),
                    notes.strip(),
                    crossplay_notes.strip(),
                    metadata["rawg_id"],
                    metadata["released"],
                    metadata["genres"],
                    metadata["platforms"],
                    metadata["background_image"],
                    metadata["description"],
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        else:
            conn.execute(
                """
                INSERT OR IGNORE INTO games(
                    title, crossplay, pc_xbox_crossplay, min_players, max_players,
                    tags, notes, crossplay_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_title,
                    pc_xbox_crossplay,
                    pc_xbox_crossplay,
                    min_players,
                    max_players,
                    tags.strip(),
                    notes.strip(),
                    crossplay_notes.strip(),
                ),
            )

        conn.commit()

    return RedirectResponse("/games", status_code=303)

@app.post("/game-crossplay/update")
def update_game_crossplay(
    game_id: int = Form(...),
    pc_xbox_crossplay: str = Form("Unknown"),
    crossplay_notes: str = Form(""),
):
    if pc_xbox_crossplay not in CROSSPLAY_OPTIONS:
        pc_xbox_crossplay = "Unknown"

    with db() as conn:
        conn.execute(
            """
            UPDATE games
            SET pc_xbox_crossplay = ?,
                crossplay_notes = ?
            WHERE id = ?
            """,
            (pc_xbox_crossplay, crossplay_notes.strip(), game_id),
        )
        conn.commit()

    return RedirectResponse("/games", status_code=303)

@app.post("/player-game/update")
def update_player_game(
    player_id: int = Form(...),
    game_id: int = Form(...),
    access: str = Form("Unknown"),
    installed: str = Form("Unknown"),
    platform: str = Form(""),
    store: str = Form(""),
    notes: str = Form(""),
):
    if access not in ACCESS_OPTIONS:
        access = "Unknown"

    if installed not in INSTALLED_OPTIONS:
        installed = "Unknown"

    legacy_status = "Unknown"
    if installed == "Yes":
        legacy_status = "Installed"
    elif access == "Own":
        legacy_status = "Owned"
    elif access == "Game Pass":
        legacy_status = "Game Pass"
    elif access == "No Access":
        legacy_status = "Not Owned"

    with db() as conn:
        conn.execute(
            """
            INSERT INTO player_games(
                player_id, game_id, status, access, installed,
                platform, store, notes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(player_id, game_id)
            DO UPDATE SET
                status = excluded.status,
                access = excluded.access,
                installed = excluded.installed,
                platform = excluded.platform,
                store = excluded.store,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                player_id,
                game_id,
                legacy_status,
                access,
                installed,
                platform.strip(),
                store.strip(),
                notes.strip(),
            ),
        )
        conn.commit()

    return RedirectResponse("/games", status_code=303)

def fetch_rawg_metadata(title: str):
    api_key = os.getenv("RAWG_API_KEY")
    if not api_key:
        return None

    search_url = "https://api.rawg.io/api/games"
    search_params = {
        "key": api_key,
        "search": title,
        "page_size": 1,
    }

    search_response = requests.get(search_url, params=search_params, timeout=10)
    search_response.raise_for_status()
    search_data = search_response.json()

    results = search_data.get("results", [])
    if not results:
        return None

    match = results[0]
    rawg_id = match.get("id")

    detail_url = f"https://api.rawg.io/api/games/{rawg_id}"
    detail_response = requests.get(detail_url, params={"key": api_key}, timeout=10)
    detail_response.raise_for_status()
    detail = detail_response.json()

    genres = ",".join([g.get("name", "") for g in detail.get("genres", []) if g.get("name")])
    platforms = ",".join([
        p.get("platform", {}).get("name", "")
        for p in detail.get("platforms", [])
        if p.get("platform", {}).get("name")
    ])

    description = detail.get("description_raw") or detail.get("description") or ""

    return {
        "rawg_id": rawg_id,
        "title": detail.get("name") or match.get("name") or title,
        "released": detail.get("released") or "",
        "genres": genres,
        "platforms": platforms,
        "background_image": detail.get("background_image") or "",
        "description": description,
    }


@app.post("/games/{game_id}/fetch-metadata")
def fetch_game_metadata(game_id: int):
    with db() as conn:
        game = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()

        if not game:
            return RedirectResponse("/games", status_code=303)

        metadata = fetch_rawg_metadata(game["title"])

        if metadata:
            conn.execute(
                """
                UPDATE games
                SET rawg_id = ?,
                    title = ?,
                    released = ?,
                    genres = ?,
                    platforms = ?,
                    background_image = ?,
                    description = ?,
                    metadata_synced_at = ?
                WHERE id = ?
                """,
                (
                    metadata["rawg_id"],
                    metadata["title"],
                    metadata["released"],
                    metadata["genres"],
                    metadata["platforms"],
                    metadata["background_image"],
                    metadata["description"],
                    datetime.now().isoformat(timespec="seconds"),
                    game_id,
                ),
            )
            conn.commit()

    return RedirectResponse("/games", status_code=303)

@app.post("/games/fetch-missing-metadata")
def fetch_missing_metadata():
    with db() as conn:
        games = conn.execute(
            """
            SELECT * FROM games
            WHERE rawg_id IS NULL
               OR rawg_id = ''
               OR metadata_synced_at = ''
            ORDER BY title
            """
        ).fetchall()

        for game in games:
            metadata = fetch_rawg_metadata(game["title"])

            if metadata:
                conn.execute(
                    """
                    UPDATE games
                    SET rawg_id = ?,
                        title = ?,
                        released = ?,
                        genres = ?,
                        platforms = ?,
                        background_image = ?,
                        description = ?,
                        metadata_synced_at = ?
                    WHERE id = ?
                    """,
                    (
                        metadata["rawg_id"],
                        metadata["title"],
                        metadata["released"],
                        metadata["genres"],
                        metadata["platforms"],
                        metadata["background_image"],
                        metadata["description"],
                        datetime.now().isoformat(timespec="seconds"),
                        game["id"],
                    ),
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
