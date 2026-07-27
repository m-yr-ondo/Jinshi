"""
FastAPI Web Dashboard for Logiq
REST API endpoints for bot statistics and management
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)


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

    return app
