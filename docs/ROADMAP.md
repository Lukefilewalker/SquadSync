# SquadSync Roadmap

## Vision
SquadSync helps gaming groups quickly answer one question:
> **What can we play right now?**

The goal is to eliminate the time spent figuring out:
- Who is available
- Who owns a game
- Who has it installed
- Whether crossplay works
- Whether the game supports the current group size

SquadSync should provide recommendations for the current squad and explain why each recommendation was made.

# Phase 1: Foundation ✅ Completed
## Player Management
- [x] Add players
- [x] Edit players
- [x] Track Xbox gamertags
- [x] Track Discord usernames
- [x] Track Twitch usernames
- [x] Track voice chat preferences
- [x] Track current squad membership

## Game Management
- [x] Add games
- [x] Archive games
- [x] Track crossplay support
- [x] Track verified squad sizes
- [x] Track game notes

## Ownership Tracking
- [x] Own
- [x] Game Pass
- [x] Free-to-play
- [x] Shared Library
- [x] No Access

## Installation Tracking
- [x] Installed
- [x] Not Installed
- [x] Unknown

## Recommendation Engine v1
- [x] Current squad awareness
- [x] Ownership awareness
- [x] Installation awareness
- [x] Crossplay awareness
- [x] Squad-size awareness

## Infrastructure
- [x] FastAPI
- [x] SQLite
- [x] Docker
- [x] Raspberry Pi deployment
- [x] Cloudflare remote access
- [x] GitHub repository

# Phase 2: Recommendation Engine Improvements
## Mode Preferences
Use stored preferences in recommendation scoring:
- Casual
- Competitive
- Both

## Competitive Readiness
Consider:
- Ranked Ready
- Not Ranked Ready

when generating recommendations.

## Recommendation Explanations
Replace opaque scores with human-readable explanations.

Example:
- Everyone owns it
- Everyone has it installed
- Verified squad size
- Crossplay supported
- Competitive preferences align


# Phase 3: Better Session Planning
## Favorites
Allow players to mark favorite games.

## Last Played
Track recent sessions.

Avoid recommending the same game repeatedly.

## Session Length
Support:
- Quick Session
- Medium Session
- Long Session

## New Player Friendly
Allow games to be marked as:
- Easy to Learn
- New Player Friendly
- Requires Experience

# Phase 4: Social Groups
## Gaming Circles
Examples:
- Core Crew
- Lawrence Crew
- Destiny Crew
- Family Group

Players may belong to multiple circles.

## Lobby Suggestions
Recommend:
- Which players should group together
- What games fit that group

# Phase 5: Automation
## Discord Integration
Automatically identify who is online.

## Discord Commands
Example:
`/squadsync`

Returns:
- Current Squad
- Best Games Right Now
- Recommendation Explanations

## Notifications
Optional notifications when a recommended squad is available.

# Future Ideas
- Steam integration
- Xbox integration
- PlayStation integration
- Discord presence integration
- Mobile app
- Hosted SaaS version
- Friend discovery
- Public profiles
- Session history
- Achievement tracking

# Product Principle
Every feature should support the core question:

> **What can we play right now?**
