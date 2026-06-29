# SquadSync Architecture

## Purpose

This document explains how SquadSync is structured so future maintainers can quickly understand where things live and how the app works.

SquadSync is a FastAPI web application that helps gaming groups answer:

> **What can we play right now?**

---

# High-Level Overview

```text
Browser
    ↓
Cloudflare Tunnel
    ↓
Raspberry Pi 5
    ↓
Docker Container
    ↓
FastAPI Application
    ↓
SQLite Database
```

---

# Main Components

## FastAPI Application

**File**

```text
app/main.py
```

This is the primary application file.

Current responsibilities:

- FastAPI setup
- Database initialization
- Route handlers
- Recommendation engine
- RAWG integration
- Player management
- Game management
- Matrix generation

At the current project size, a single file is acceptable. Future growth will likely require splitting responsibilities into separate modules.

---

## Templates

**Folder**

```text
app/templates/
```

Current templates:

| File | Purpose |
|--------|--------|
| base.html | Shared layout, navigation, branding |
| dashboard.html | Main recommendation dashboard |
| games.html | Game management page |
| matrix.html | Full ownership/access matrix |
| players.html | Player management page |

Templates are rendered using Jinja2.

---

## Static Assets

**Folder**

```text
app/static/
```

Current files:

| File | Purpose |
|--------|--------|
| styles.css | Site styling |
| logo.png | Main logo |
| logo.svg | Vector logo source |

---

## Database

**File**

```text
data/gamenight.db
```

Database engine:

```text
SQLite
```

The database is stored outside the application code so data survives Docker rebuilds.

Primary tables:

### players

Stores:

- Player identity
- Gamertags
- Discord usernames
- Twitch usernames
- Voice preferences
- Current squad status

### games

Stores:

- Game metadata
- Crossplay information
- Squad size information
- Notes
- RAWG metadata

### player_games

Stores:

- Ownership status
- Install status
- Platform
- Store
- Mode preferences
- Competitive readiness

This is the most important table in the system because it connects players and games.

---

## Bulk Import

**File**

```text
app/import_games.py
```

Purpose:

Import CSV data into SquadSync.

Import files live in:

```text
imports/
```

This folder is ignored by Git.

---

## Docker

Files:

```text
Dockerfile
docker-compose.yml
```

Current deployment:

```text
Host Port: 8099
Container Port: 8000
```

---

# Request Flow

Example:

Dashboard Load

```text
User opens dashboard
    ↓
GET /
    ↓
get_matrix()
    ↓
Load players
Load games
Load player_game records
    ↓
Filter Current Squad
    ↓
Generate recommendations
    ↓
Render dashboard.html
```

---

# Recommendation Engine

Current recommendation factors:

- Current Squad membership
- Ownership status
- Install status
- Crossplay support
- Verified squad size
- Ready player count

Current scoring is intentionally simple.

Future versions will incorporate:

- Casual vs Competitive preferences
- Competitive readiness
- Favorites
- Session history
- Last played data

---

# Important Design Decisions

## Current Squad

Database field:

```text
active_tonight
```

UI terminology:

```text
Current Squad
```

The database field name remains unchanged to avoid unnecessary migrations.

Future migration candidate:

```text
current_squad
```

---

## Verified Squad Sizes

SquadSync stores manually verified squad sizes separately from RAWG metadata.

Reason:

Many public game databases provide incomplete or inaccurate multiplayer information.

Recommendation quality depends heavily on accurate squad sizes.

---

## Recommendation Philosophy

SquadSync does not attempt to predict what players want.

SquadSync attempts to identify:

> What this group can successfully play together right now.

This distinction should guide future feature development.

---

# Deployment

Current Environment

```text
Raspberry Pi 5
Docker Compose
SQLite
Cloudflare Tunnel
GitHub
```

Suitable for:

- Personal use
- Friend groups
- Small communities

---

# Potential Future Deployment

```text
VPS
Docker Compose
PostgreSQL
Cloudflare
```

or

```text
Managed Cloud Platform
PostgreSQL
Object Storage
CDN
```

Only pursue this if public adoption occurs.

---

# Future Refactor Targets

Possible future structure:

```text
app/
├── main.py
├── db.py
├── recommendations.py
├── rawg.py
├── models.py
├── routes/
│   ├── dashboard.py
│   ├── games.py
│   ├── players.py
│   └── matrix.py
├── templates/
└── static/
```

Do not refactor prematurely.

Feature development currently provides more value than architectural cleanup.
