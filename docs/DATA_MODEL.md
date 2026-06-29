# SquadSync Data Model

## Purpose

This document describes the SquadSync database structure and explains the purpose of each table and major field.

Database:

```text
SQLite
```

Database file:

```text
data/gamenight.db
```

---

# Entity Relationship Overview

```text
players
    │
    │ 1-to-many
    │
    ▼
player_games
    ▲
    │
    │ many-to-1
    │
games
```

The `player_games` table is the bridge between players and games.

---

# Table: players

Purpose:

Stores information about each player.

## Core Fields

| Field | Purpose |
|---------|---------|
| id | Primary key |
| name | Display name |

---

## Identity Fields

| Field | Purpose |
|---------|---------|
| xbox_gamertag | Xbox username |
| discord_username | Discord username |
| twitch_username | Twitch username |

---

## Communication Fields

| Field | Purpose |
|---------|---------|
| preferred_voice | Preferred voice chat platform |

Values:

```text
Discord
Xbox Party
In-game
Either
Unknown
```

---

## Squad Fields

| Field | Purpose |
|---------|---------|
| active_tonight | Current Squad membership |

Despite the field name, the UI refers to this as:

```text
Current Squad
```

Future migration candidate:

```text
current_squad
```

---

## Notes

| Field | Purpose |
|---------|---------|
| notes | Free-form player notes |

---

# Table: games

Purpose:

Stores information about games.

## Core Fields

| Field | Purpose |
|---------|---------|
| id | Primary key |
| title | Game title |

---

## Crossplay Fields

| Field | Purpose |
|---------|---------|
| crossplay | Legacy crossplay field |
| pc_xbox_crossplay | Primary crossplay field |
| crossplay_notes | Crossplay notes |

Values:

```text
Yes
No
Partial
Possible
Unknown
```

---

## Squad Size Fields

| Field | Purpose |
|---------|---------|
| min_players | Generic player count |
| max_players | Generic player count |
| squad_min | Verified minimum squad size |
| squad_max | Verified maximum squad size |
| squad_verified | Indicates verified values |
| squad_source | Source of verification |
| squad_notes | Additional notes |

Verified values are preferred by the recommendation engine.

---

## Metadata Fields

| Field | Purpose |
|---------|---------|
| tags | Tags |
| notes | Notes |
| archived | Archive status |

---

## RAWG Metadata

| Field | Purpose |
|---------|---------|
| rawg_id | RAWG identifier |
| released | Release date |
| genres | Genre list |
| platforms | Platform list |
| background_image | Image URL |
| description | Description |
| metadata_synced_at | Last sync timestamp |

---

# Table: player_games

Purpose:

Stores per-player information for a specific game.

This table powers recommendations.

---

## Relationship Fields

| Field | Purpose |
|---------|---------|
| player_id | Linked player |
| game_id | Linked game |

Unique constraint:

```text
(player_id, game_id)
```

A player can only have one record per game.

---

## Access Fields

| Field | Purpose |
|---------|---------|
| access | Ownership/access status |

Values:

```text
Own
Game Pass
Free-to-play
Shared Library
No Access
Unknown
```

---

## Installation Fields

| Field | Purpose |
|---------|---------|
| installed | Installation status |

Values:

```text
Yes
No
Unknown
```

---

## Platform Fields

| Field | Purpose |
|---------|---------|
| platform | Platform information |
| store | Store information |

Examples:

```text
PC
Xbox
Steam Deck
```

Stores:

```text
Steam
Xbox
Epic
Battle.net
```

---

## Preference Fields

| Field | Purpose |
|---------|---------|
| preferred_mode | Casual vs Competitive preference |
| competitive_ready | Ranked readiness |
| mode_notes | Additional notes |

Current values:

```text
Casual
Competitive
Both
Unknown
```

Competitive readiness:

```text
Yes
No
Unknown
```

These fields currently exist but are not yet used in recommendation scoring.

---

## Audit Fields

| Field | Purpose |
|---------|---------|
| updated_at | Last modification timestamp |

---

# Recommendation Engine Dependencies

Current recommendation engine uses:

- active_tonight
- access
- installed
- pc_xbox_crossplay
- squad_min
- squad_max
- squad_verified

Future recommendation versions may also use:

- preferred_mode
- competitive_ready
- favorites
- session history

---

# Migration Notes

Future database changes should:

1. Use `add_column_if_missing()`
2. Preserve existing data
3. Avoid destructive migrations
4. Prefer additive schema changes

This approach allows painless upgrades for existing installations.
