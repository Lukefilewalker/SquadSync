import csv
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/gamenight.db")

ACCESS_OPTIONS = {"Own", "Game Pass", "Free-to-play", "Shared Library", "No Access", "Unknown"}
INSTALLED_OPTIONS = {"Yes", "No", "Unknown"}

if len(sys.argv) != 2:
    print("Usage: python3 app/import_games.py imports/file.csv")
    sys.exit(1)

csv_path = Path(sys.argv[1])

if not csv_path.exists():
    print(f"CSV not found: {csv_path}")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

added_games = 0
updated_rows = 0

with csv_path.open(newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        player_name = row.get("player", "").strip()
        title = row.get("title", "").strip()
        access = row.get("access", "Unknown").strip() or "Unknown"
        installed = row.get("installed", "Unknown").strip() or "Unknown"
        platform = row.get("platform", "").strip()
        store = row.get("store", "").strip()
        notes = row.get("notes", "").strip()

        if not player_name or not title:
            continue

        if access not in ACCESS_OPTIONS:
            access = "Unknown"

        if installed not in INSTALLED_OPTIONS:
            installed = "Unknown"

        conn.execute("INSERT OR IGNORE INTO players(name) VALUES (?)", (player_name,))
        conn.execute("INSERT OR IGNORE INTO games(title) VALUES (?)", (title,))

        player = conn.execute("SELECT id FROM players WHERE name = ?", (player_name,)).fetchone()
        game = conn.execute("SELECT id FROM games WHERE title = ?", (title,)).fetchone()

        existing_game = conn.execute("SELECT rawg_id FROM games WHERE id = ?", (game["id"],)).fetchone()
        if existing_game and existing_game["rawg_id"] is None:
            added_games += 1

        legacy_status = "Unknown"
        if installed == "Yes":
            legacy_status = "Installed"
        elif access == "Own":
            legacy_status = "Owned"
        elif access == "Game Pass":
            legacy_status = "Game Pass"
        elif access == "No Access":
            legacy_status = "Not Owned"

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
                player["id"],
                game["id"],
                legacy_status,
                access,
                installed,
                platform,
                store,
                notes,
            ),
        )

        updated_rows += 1

conn.commit()
conn.close()

print(f"Imported {updated_rows} player-game rows from {csv_path}")
print("Next: open SquadSync and click Fetch Missing Metadata.")
