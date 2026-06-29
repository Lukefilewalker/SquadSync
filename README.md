# SquadSync
SquadSync is a self-hosted multiplayer gaming companion that helps groups of friends decide what to play together.

It tracks game ownership, installation status, platforms, crossplay support, squad sizes, player preferences, and competitive readiness to recommend games that work for the current squad.

Built with:
- FastAPI
- SQLite
- Docker
- RAWG API
- Cloudflare Tunnel (optional)

## Features
### Dashboard
- Active squad tracking
- Recommended games
- Ready-to-play analysis
- Access and install status summaries

### Game Library
- Search games
- RAWG metadata integration
- Cover art and platform data
- Crossplay tracking
- Squad size tracking
- Game detail pages

### Player Profiles
- Display names
- Real names
- Xbox gamertags
- Discord usernames
- Twitch usernames
- Steam usernames
- Avatar URLs
- Preferred voice platform
- Player notes

### Matrix View
View ownership and install status for every player and every game.

## Quick Start
```bash
docker compose up --build -d
```

Open:
```text
http://<your-server>:8099
```

Example:
```text
http://192.168.50.241:8099
```

## Development
Start VS Code Remote SSH:
```bash
code .
```

Build and restart:
```bash
docker compose up -d --build
```

View logs:
```bash
docker compose logs -f
```

Check status:
```bash
docker compose ps
```

## Database
SQLite database:
```text
data/gamenight.db
```

The database stores:
- Players
- Games
- Player-game relationships
- Crossplay metadata
- Squad size metadata
- Profile information

## Roadmap
### Near Term
- Clickable player profile links
- Better recommendation explanations
- Dashboard statistics
- Platform compatibility improvements

### Future
- Discord integration
- Automatic online status detection
- Session planning
- Player avatars and uploads
- Steam/Xbox profile integration
- Availability tracking

## Reset Database
```bash
docker compose down
rm -f data/gamenight.db
docker compose up -d --build
```

Warning: this removes all players, games, and profile data.