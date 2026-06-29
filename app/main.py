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
MODE_OPTIONS = ["Unknown", "Casual", "Competitive", "Both"]
COMPETITIVE_READY_OPTIONS = ["Unknown", "Yes", "No"]
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
        add_column_if_missing(conn, "games", "archived", "INTEGER DEFAULT 0")
        add_column_if_missing(conn, "games", "squad_min", "INTEGER DEFAULT 1")
        add_column_if_missing(conn, "games", "squad_max", "INTEGER DEFAULT 4")
        add_column_if_missing(conn, "games", "squad_verified", "INTEGER DEFAULT 0")
        add_column_if_missing(conn, "games", "squad_source", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "games", "squad_notes", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "players", "xbox_gamertag", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "players", "discord_username", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "players", "twitch_username", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "players", "preferred_voice", "TEXT DEFAULT 'Either'")
        add_column_if_missing(conn, "players", "notes", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "players", "active_tonight", "INTEGER DEFAULT 1")
        add_column_if_missing(conn, "player_games", "preferred_mode", "TEXT DEFAULT 'Unknown'")
        add_column_if_missing(conn, "player_games", "competitive_ready", "TEXT DEFAULT 'Unknown'")
        add_column_if_missing(conn, "player_games", "mode_notes", "TEXT DEFAULT ''")
        
        conn.commit()


@app.on_event("startup")
def startup():
    init_db()

def get_players(conn):
    return conn.execute("""
        SELECT * FROM players
        ORDER BY active_tonight DESC, name
    """).fetchall() 

def get_games(conn):
    return conn.execute("""
        SELECT * FROM games
        WHERE COALESCE(archived, 0) = 0
        ORDER BY title
    """).fetchall()

def get_matrix(conn):
    players = get_players(conn)
    games = get_games(conn)

    rows = []
    for game in games:
        player_data = {}
        for player in players:
            pg = conn.execute(
                """
                SELECT access, installed, platform, store, notes,
                       preferred_mode, competitive_ready, mode_notes
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
                "preferred_mode": "Unknown",
                "competitive_ready": "Unknown",
                "mode_notes": "",
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
        return "Ready Now"

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
        total_players = len(players)

        access_count = 0
        installed_count = 0
        ready_count = 0
        no_access_count = 0
        unknown_count = 0

        casual_count = 0
        competitive_count = 0
        both_count = 0
        mode_unknown_count = 0
        comp_ready_count = 0
        comp_not_ready_count = 0

        reasons = []
        warnings = []

        for player in players:
            pdata = player_data[player["id"]]

            has_access = pdata["access"] in ACCESS_OK
            is_installed = pdata["installed"] == "Yes"

            if has_access:
                access_count += 1

            if is_installed:
                installed_count += 1

            if has_access and is_installed:
                ready_count += 1

            if pdata["access"] == "No Access":
                no_access_count += 1

            if pdata["access"] == "Unknown" or pdata["installed"] == "Unknown":
                unknown_count += 1

            preferred_mode = pdata.get("preferred_mode", "Unknown")
            if preferred_mode == "Casual":
                casual_count += 1
            elif preferred_mode == "Competitive":
                competitive_count += 1
            elif preferred_mode == "Both":
                both_count += 1
            else:
                mode_unknown_count += 1

            competitive_ready = pdata.get("competitive_ready", "Unknown")
            if competitive_ready == "Yes":
                comp_ready_count += 1
            elif competitive_ready == "No":
                comp_not_ready_count += 1

        if game["squad_verified"]:
            min_players = game["squad_min"] or 1
            max_players = game["squad_max"] or 99
            squad_label = f"Squad: {min_players}-{max_players} verified"
            reasons.append("Verified squad size")
        else:
            min_players = game["min_players"] or 1
            max_players = game["max_players"] or 99
            squad_label = f"Players: {min_players}-{max_players} unverified"
            warnings.append("Squad size is unverified")

        score = (ready_count * 8) + (installed_count * 4) + (access_count * 2)

        if total_players > 0:
            if ready_count == total_players:
                reasons.append("Everyone in the current squad is ready")
            elif ready_count > 0:
                reasons.append(f"{ready_count}/{total_players} current squad members are ready")

            if access_count == total_players:
                reasons.append("Everyone has access")
            elif access_count > 0:
                warnings.append(f"{total_players - access_count} current squad member(s) may need access")

            if installed_count == total_players:
                reasons.append("Everyone has it installed")
            elif installed_count > 0:
                warnings.append(f"{total_players - installed_count} current squad member(s) may need to install")

            if unknown_count > 0:
                warnings.append(f"{unknown_count} current squad member(s) have unknown access or install status")

        pc_xbox = game["pc_xbox_crossplay"] or game["crossplay"] or "Unknown"
        if pc_xbox == "Yes":
            score += 4
            reasons.append("PC/Xbox crossplay supported")
        elif pc_xbox == "Partial":
            score += 1
            warnings.append("Crossplay is partial")
        elif pc_xbox == "Possible":
            score += 1
            warnings.append("Crossplay may be possible")
        elif pc_xbox == "No":
            score -= 10
            warnings.append("PC/Xbox crossplay is not supported")
        elif pc_xbox == "Unknown":
            score -= 2
            warnings.append("Crossplay status is unknown")

        squad_fit = "Fits group"
        if ready_count < min_players:
            score -= 8
            squad_fit = "Not enough ready players"
            warnings.append("Not enough ready players for this squad size")
        elif ready_count > max_players:
            score -= 12
            squad_fit = "Too many ready players"
            warnings.append("Too many ready players for this squad size")
        else:
            reasons.append("Fits the current squad size")

        mode_fit = "Unknown"
        if competitive_count > 0 and casual_count == 0:
            mode_fit = "Competitive fit"
            score += 3
            reasons.append("Competitive preferences line up")
        elif casual_count > 0 and competitive_count == 0:
            mode_fit = "Casual fit"
            score += 2
            reasons.append("Casual preferences line up")
        elif both_count > 0 and casual_count == 0 and competitive_count == 0:
            mode_fit = "Flexible"
            score += 1
            reasons.append("Mode preferences are flexible")
        elif casual_count > 0 and competitive_count > 0:
            mode_fit = "Mixed preferences"
            score -= 2
            warnings.append("Current squad has mixed casual and competitive preferences")

        if competitive_count > 0:
            if comp_not_ready_count > 0:
                score -= 3
                mode_fit = f"{mode_fit}, some not comp ready"
                warnings.append("Some competitive players are not marked competitive-ready")
            elif comp_ready_count >= competitive_count:
                score += 2
                mode_fit = f"{mode_fit}, comp ready"
                reasons.append("Competitive players are marked ready")

        recommendations.append({
            "game": game,
            "score": score,
            "access_count": access_count,
            "installed_count": installed_count,
            "ready_count": ready_count,
            "no_access_count": no_access_count,
            "unknown_count": unknown_count,
            "total_players": total_players,
            "min_players": min_players,
            "max_players": max_players,
            "squad_fit": squad_fit,
            "squad_label": squad_label,
            "pc_xbox_crossplay": pc_xbox,
            "casual_count": casual_count,
            "competitive_count": competitive_count,
            "both_count": both_count,
            "mode_unknown_count": mode_unknown_count,
            "comp_ready_count": comp_ready_count,
            "comp_not_ready_count": comp_not_ready_count,
            "mode_fit": mode_fit,
            "reasons": reasons,
            "warnings": warnings,
        })

    return sorted(recommendations, key=lambda item: item["score"], reverse=True)

@app.get("/")
def dashboard(request: Request):
    with db() as conn:
        players, rows = get_matrix(conn)
        players = [p for p in players if p["active_tonight"]]

        buckets = {
            "Ready Now": [],
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
        active_player_names = [p["name"] for p in players]

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "players": players,
                "active_player_names": active_player_names,
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
                "mode_options": MODE_OPTIONS,
                "competitive_ready_options": COMPETITIVE_READY_OPTIONS,
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
                    clean_title,
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

@app.post("/games/{game_id}/archive")
def archive_game(game_id: int):
    with db() as conn:
        conn.execute(
            "UPDATE games SET archived = 1 WHERE id = ?",
            (game_id,)
        )
        conn.commit()

    return RedirectResponse("/games", status_code=303)

@app.post("/games/{game_id}/unarchive")
def unarchive_game(game_id: int):
    with db() as conn:
        conn.execute(
            "UPDATE games SET archived = 0 WHERE id = ?",
            (game_id,)
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

@app.post("/game-squad/update")
def update_game_squad(
    game_id: int = Form(...),
    squad_min: int = Form(1),
    squad_max: int = Form(4),
    squad_verified: int = Form(0),
    squad_source: str = Form(""),
    squad_notes: str = Form(""),
):
    if squad_min < 1:
        squad_min = 1

    if squad_max < squad_min:
        squad_max = squad_min

    squad_verified = 1 if squad_verified else 0

    with db() as conn:
        conn.execute(
            """
            UPDATE games
            SET squad_min = ?,
                squad_max = ?,
                squad_verified = ?,
                squad_source = ?,
                squad_notes = ?
            WHERE id = ?
            """,
            (
                squad_min,
                squad_max,
                squad_verified,
                squad_source.strip(),
                squad_notes.strip(),
                game_id,
            ),
        )
        conn.commit()

    return RedirectResponse("/games", status_code=303)

@app.post("/player-game/update")
def update_player_game(
    player_id: int = Form(...),
    game_id: int = Form(...),
    access: str = Form("Unknown"),
    installed: str = Form("Unknown"),
    preferred_mode: str = Form("Unknown"),
    competitive_ready: str = Form("Unknown"),
    platform: str = Form(""),
    store: str = Form(""),
    notes: str = Form(""),
):
    if access not in ACCESS_OPTIONS:
        access = "Unknown"

    if installed not in INSTALLED_OPTIONS:
        installed = "Unknown"

    if preferred_mode not in MODE_OPTIONS:
        preferred_mode = "Unknown"

    if competitive_ready not in COMPETITIVE_READY_OPTIONS:
        competitive_ready = "Unknown"

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
                preferred_mode, competitive_ready,
                platform, store, notes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(player_id, game_id)
            DO UPDATE SET
                status = excluded.status,
                access = excluded.access,
                installed = excluded.installed,
                preferred_mode = excluded.preferred_mode,
                competitive_ready = excluded.competitive_ready,
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
                preferred_mode,
                competitive_ready,
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
            {
                "request": request,
                "players": people,
                "voice_options": VOICE_OPTIONS,
            },
        )


@app.post("/players/add")
def add_player(name: str = Form(...)):
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO players(name) VALUES (?)", (name.strip(),))
        conn.commit()

    return RedirectResponse("/players", status_code=303)

VOICE_OPTIONS = ["Discord", "Xbox Party", "In-game", "Either", "Unknown"]

@app.post("/players/update")
def update_player(
    player_id: int = Form(...),
    name: str = Form(...),
    xbox_gamertag: str = Form(""),
    discord_username: str = Form(""),
    twitch_username: str = Form(""),
    preferred_voice: str = Form("Either"),
    notes: str = Form(""),
):
    if preferred_voice not in VOICE_OPTIONS:
        preferred_voice = "Either"

    with db() as conn:
        conn.execute(
            """
            UPDATE players
            SET name = ?,
                xbox_gamertag = ?,
                discord_username = ?,
                twitch_username = ?,
                preferred_voice = ?,
                notes = ?
            WHERE id = ?
            """,
            (
                name.strip(),
                xbox_gamertag.strip(),
                discord_username.strip(),
                twitch_username.strip(),
                preferred_voice,
                notes.strip(),
                player_id,
            ),
        )
        conn.commit()

    return RedirectResponse("/players", status_code=303)

@app.post("/players/set-active")
def set_player_active(
    player_id: int = Form(...),
    active_tonight: int = Form(...),
):
    with db() as conn:
        conn.execute(
            "UPDATE players SET active_tonight = ? WHERE id = ?",
            (active_tonight, player_id),
        )
        conn.commit()

    return RedirectResponse("/players", status_code=303)
