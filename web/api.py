"""
FastAPI Web Dashboard for Logiq
REST API endpoints for bot statistics and management
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import os
import hmac
import re

logger = logging.getLogger(__name__)
SNOWFLAKE_RE = re.compile(r"^\d{17,20}$")


def create_app(bot) -> FastAPI:
    """Create FastAPI application"""

    app = FastAPI(
        title="Logiq API",
        description="REST API for Logiq Discord Bot",
        version="1.0.0"
    )

    # CORS middleware
    cors_origins = bot.config.get('web', {}).get('cors_origins', ['http://localhost:3000'])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Admin Dashboard Homepage"""
        html_file = os.path.join(os.path.dirname(__file__), "templates", "index.html")
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                return f.read()
        return """
        <html>
            <head><title>Logiq Admin Dashboard</title></head>
            <body>
                <h1>Logiq API</h1>
                <p>Version: 1.0.0</p>
                <p>Status: Online</p>
                <p>Bot User: {}</p>
                <p><a href="/admin">Go to Admin Dashboard</a></p>
            </body>
        </html>
        """.format(str(bot.user) if bot.user else "Loading...")

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_dashboard():
        """Admin Dashboard"""
        html_file = os.path.join(os.path.dirname(__file__), "templates", "admin.html")
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                return f.read()
        # Return fallback if template doesn't exist
        return "<h1>Admin Dashboard - Template not found</h1>"

    @app.get("/stats")
    async def get_stats():
        """Get bot statistics"""
        return {
            "guilds": len(bot.guilds),
            "users": sum(g.member_count for g in bot.guilds),
            "channels": sum(len(g.channels) for g in bot.guilds),
            "uptime": str(datetime.utcnow() - bot.start_time).split('.')[0] if hasattr(bot, 'start_time') else "Unknown",
            "latency": round(bot.latency * 1000)
        }

    @app.get("/guilds")
    async def get_guilds():
        """Get list of guilds"""
        return {
            "guilds": [
                {
                    "id": guild.id,
                    "name": guild.name,
                    "member_count": guild.member_count,
                    "icon_url": str(guild.icon.url) if guild.icon else None
                }
                for guild in bot.guilds
            ]
        }

    @app.get("/guilds/{guild_id}")
    async def get_guild(guild_id: int):
        """Get guild details"""
        guild = bot.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")

        guild_config = await bot.db.get_guild(guild_id)

        return {
            "id": guild.id,
            "name": guild.name,
            "member_count": guild.member_count,
            "icon_url": str(guild.icon.url) if guild.icon else None,
            "owner_id": guild.owner_id,
            "created_at": guild.created_at.isoformat(),
            "config": guild_config
        }

    @app.get("/guilds/{guild_id}/leaderboard")
    async def get_guild_leaderboard(guild_id: int, limit: int = 10):
        """Get guild XP leaderboard"""
        guild = bot.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")

        leaderboard = await bot.db.get_leaderboard(guild_id, limit=limit)

        return {
            "guild_id": guild_id,
            "leaderboard": [
                {
                    "rank": i + 1,
                    "user_id": entry['user_id'],
                    "xp": entry.get('xp', 0),
                    "level": entry.get('level', 0)
                }
                for i, entry in enumerate(leaderboard)
            ]
        }

    @app.get("/guilds/{guild_id}/analytics")
    async def get_guild_analytics(guild_id: int, days: int = 7):
        """Get guild analytics"""
        guild = bot.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")

        end_time = datetime.utcnow().timestamp()
        start_time = (datetime.utcnow() - timedelta(days=days)).timestamp()

        # Get analytics data
        messages = await bot.db.get_analytics(
            guild_id,
            event_type='message',
            start_time=start_time,
            end_time=end_time
        )

        joins = await bot.db.get_analytics(
            guild_id,
            event_type='member_join',
            start_time=start_time,
            end_time=end_time
        )

        leaves = await bot.db.get_analytics(
            guild_id,
            event_type='member_leave',
            start_time=start_time,
            end_time=end_time
        )

        return {
            "guild_id": guild_id,
            "period_days": days,
            "total_messages": len(messages),
            "member_joins": len(joins),
            "member_leaves": len(leaves),
            "net_growth": len(joins) - len(leaves)
        }

    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        db_connected = bot.db.is_connected if hasattr(bot.db, 'is_connected') else False

        return {
            "status": "healthy" if bot.is_ready() and db_connected else "unhealthy",
            "bot_ready": bot.is_ready(),
            "database_connected": db_connected,
            "timestamp": datetime.utcnow().isoformat()
        }

    @app.get("/modules")
    async def get_modules():
        """Get module status"""
        modules = bot.config.get('modules', {})
        return {
            "modules": {
                name: config.get('enabled', True)
                for name, config in modules.items()
            }
        }

    @app.post("/internal/checkers-result")
    async def record_checkers_result(request: Request):
        """Record one authenticated, idempotent result from the Activity server."""
        expected_secret = os.getenv("INTERNAL_API_SECRET")
        provided_secret = request.headers.get("X-Internal-Secret")
        if not expected_secret:
            logger.error("INTERNAL_API_SECRET is not configured")
            raise HTTPException(status_code=503, detail="Internal API is not configured")
        if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
            raise HTTPException(status_code=401, detail="Unauthorized")

        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Body must be valid JSON")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")

        required = {"guild_id", "game_id", "outcome", "reason", "player_ids"}
        if not required.issubset(payload):
            raise HTTPException(status_code=400, detail="Missing required result fields")

        guild_id = payload["guild_id"]
        game_id = payload["game_id"]
        outcome = payload["outcome"]
        reason = payload["reason"]
        player_ids = payload["player_ids"]
        valid_reasons = {"captured", "blocked", "repetition", "forfeit", "resignation"}

        if not isinstance(guild_id, str) or not SNOWFLAKE_RE.fullmatch(guild_id):
            raise HTTPException(status_code=400, detail="Invalid guild_id")
        if not isinstance(game_id, str) or not 8 <= len(game_id) <= 200:
            raise HTTPException(status_code=400, detail="Invalid game_id")
        if outcome not in {"win", "draw"} or reason not in valid_reasons:
            raise HTTPException(status_code=400, detail="Invalid outcome or reason")
        if (
            not isinstance(player_ids, list)
            or len(player_ids) != 2
            or len(set(player_ids)) != 2
            or any(not isinstance(value, str) or not SNOWFLAKE_RE.fullmatch(value)
                   for value in player_ids)
        ):
            raise HTTPException(status_code=400, detail="player_ids must contain two Discord IDs")

        winner_id = payload.get("winner_id")
        loser_id = payload.get("loser_id")
        if outcome == "win":
            if (
                not isinstance(winner_id, str)
                or not isinstance(loser_id, str)
                or {winner_id, loser_id} != set(player_ids)
            ):
                raise HTTPException(
                    status_code=400,
                    detail="A win requires matching winner_id and loser_id"
                )
        elif winner_id is not None or loser_id is not None:
            raise HTTPException(status_code=400, detail="A draw cannot have a winner or loser")

        guild = bot.get_guild(int(guild_id))
        if not guild:
            raise HTTPException(status_code=400, detail="Jinshi is not connected to this guild")
        for player_id in player_ids:
            member = guild.get_member(int(player_id))
            if not member or member.bot:
                raise HTTPException(status_code=400, detail="Every player must be a guild member")

        checkers_config = bot.config.get("modules", {}).get("checkers", {})
        if not checkers_config.get("enabled", True):
            raise HTTPException(status_code=503, detail="Checkers integration is disabled")

        try:
            return await bot.db.record_checkers_result(
                guild_id=int(guild_id),
                player_ids=[int(value) for value in player_ids],
                outcome=outcome,
                game_id=game_id,
                win_reward=int(checkers_config.get("win_reward", 150)),
                winner_id=int(winner_id) if winner_id else None,
                loser_id=int(loser_id) if loser_id else None
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        except Exception:
            logger.exception("Failed to record checkers result game_id=%s", game_id)
            raise HTTPException(status_code=500, detail="Result could not be recorded")

    return app
