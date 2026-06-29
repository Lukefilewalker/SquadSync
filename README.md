# SquadSync

A self-hosted multiplayer game library tracker that helps groups of friends find games they can play together across platforms.

## Quick start with Docker

```bash
cd game-night-finder
docker compose up --build -d
```

Then open:

```text
http://<your-pi-ip>:8099
```

Example:

```text
http://192.168.50.60:8099
```

## First login / usage

There is no login yet. This is the first private LAN version.

Preloaded players:

- Steven
- Nick
- Anthony
- Ray
- Derek
- Kenny

## What it tracks

Each player-game record has:

- status: Installed, Owned, Game Pass, Not Owned, Unknown
- platform: PC, Xbox, Steam Deck, Handheld, etc.
- notes

The dashboard shows:

- Ready now
- One download away
- Everyone has access
- Needs purchase
- Unknown

## Useful commands

Start:

```bash
docker compose up --build -d
```

Stop:

```bash
docker compose down
```

View logs:

```bash
docker compose logs -f
```

Reset database:

```bash
docker compose down
rm -f data/gamenight.db
docker compose up --build -d
```
