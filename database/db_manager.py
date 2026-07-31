"""
Database Manager for Logiq
Handles async MongoDB operations with connection pooling
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Async MongoDB database manager with connection pooling"""

    def __init__(self, uri: str, database_name: str, pool_size: int = 10):
        """
        Initialize database manager

        Args:
            uri: MongoDB connection URI
            database_name: Name of the database
            pool_size: Maximum connection pool size
        """
        self.uri = uri
        self.database_name = database_name
        self.pool_size = pool_size
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self._connected = False

    async def connect(self) -> None:
        """Establish database connection"""
        try:
            self.client = AsyncIOMotorClient(
                self.uri,
                maxPoolSize=self.pool_size,
                minPoolSize=1,
                serverSelectionTimeoutMS=5000
            )
            self.db = self.client[self.database_name]
            # Test connection
            await self.client.admin.command('ping')
            self._connected = True
            logger.info(f"Connected to MongoDB database: {self.database_name}")

            # TTL index: auto-expire analytics events after 90 days.
            # get_analytics() is only ever queried with a recent time window
            # (the /analytics command defaults to 7 days), so there's no
            # reason to keep raw per-message events forever - this keeps
            # storage bounded on free-tier Atlas clusters.
            await self.db.analytics.create_index(
                "created_at", expireAfterSeconds=90 * 24 * 60 * 60
            )

            # Checkers result processing is transactional and game IDs are unique,
            # so a retry can never pay the same result twice.
            await self.db.checkers_processed.create_index("game_id", unique=True)
            await self.db.checkers_processed.create_index(
                "processed_at", expireAfterSeconds=90 * 24 * 60 * 60
            )
            await self.db.checkers_stats.create_index(
                [("guild_id", 1), ("user_id", 1)], unique=True
            )
            await self.db.checkers_stats.create_index(
                [("guild_id", 1), ("points", -1), ("wins", -1), ("best_win_streak", -1)]
            )
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    async def disconnect(self) -> None:
        """Close database connection"""
        if self.client:
            self.client.close()
            self._connected = False
            logger.info("Disconnected from MongoDB")

    @property
    def is_connected(self) -> bool:
        """Check if database is connected"""
        return self._connected

    # User operations
    async def get_user(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get user document"""
        return await self.db.users.find_one({
            "user_id": user_id,
            "guild_id": guild_id
        })

    async def create_user(self, user_id: int, guild_id: int, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create new user document"""
        user_data = {
            "user_id": user_id,
            "guild_id": guild_id,
            "xp": 0,
            "level": 0,
            "balance": 1000,
            "inventory": [],
            "warnings": [],
            "created_at": asyncio.get_event_loop().time()
        }
        if data:
            user_data.update(data)

        await self.db.users.insert_one(user_data)
        return user_data

    async def update_user(self, user_id: int, guild_id: int, data: Dict[str, Any]) -> bool:
        """Update user document"""
        result = await self.db.users.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {"$set": data}
        )
        return result.modified_count > 0

    async def reset_guild_levels(self, guild_id: int) -> int:
        """Reset xp and level to 0 for every user in a guild. Returns count of documents modified."""
        result = await self.db.users.update_many(
            {"guild_id": guild_id},
            {"$set": {"xp": 0, "level": 0}}
        )
        return result.modified_count

    async def increment_user_field(
        self,
        user_id: int,
        guild_id: int,
        field: str,
        amount: int = 1,
        session=None
    ) -> bool:
        """Increment a numeric field in user document"""
        result = await self.db.users.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {"$inc": {field: amount}},
            session=session
        )
        return result.modified_count > 0

    async def add_activity_seconds(self, guild_id: int, user_id: int, date_str: str,
                                    activity_type: str, activity_name: str, seconds: float) -> None:
        """Add elapsed seconds to a user's daily activity bucket (game name, or 'Spotify')"""
        if seconds <= 0:
            return
        await self.db.activity_daily.update_one(
            {"guild_id": guild_id, "user_id": user_id, "date": date_str,
             "type": activity_type, "name": activity_name},
            {"$inc": {"seconds": seconds}},
            upsert=True
        )

    async def set_activity_seconds(self, guild_id: int, user_id: int, date_str: str,
                                    activity_type: str, activity_name: str, seconds: float) -> None:
        """Set the exact seconds for a daily activity bucket, overwriting any previous value"""
        await self.db.activity_daily.update_one(
            {"guild_id": guild_id, "user_id": user_id, "date": date_str,
             "type": activity_type, "name": activity_name},
            {"$set": {"seconds": seconds}},
            upsert=True
        )

    async def get_daily_activity(self, guild_id: int, date_str: str) -> Dict[int, List[Dict[str, Any]]]:
        """Return today's activity entries grouped by user_id: {user_id: [{type, name, seconds}, ...]}"""
        cursor = self.db.activity_daily.find({"guild_id": guild_id, "date": date_str})
        by_user: Dict[int, List[Dict[str, Any]]] = {}
        async for doc in cursor:
            by_user.setdefault(doc["user_id"], []).append(
                {"type": doc["type"], "name": doc["name"], "seconds": doc["seconds"]}
            )
        return by_user

    # Guild operations
    async def get_guild(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get guild configuration"""
        return await self.db.guilds.find_one({"guild_id": guild_id})

    async def create_guild(self, guild_id: int, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create new guild configuration"""
        guild_data = {
            "guild_id": guild_id,
            "prefix": "/",
            "modules": {},
            "log_channel": None,
            "welcome_channel": None,
            "verified_role": None,
            "created_at": asyncio.get_event_loop().time()
        }
        if data:
            guild_data.update(data)

        await self.db.guilds.insert_one(guild_data)
        return guild_data

    async def update_guild(self, guild_id: int, data: Dict[str, Any]) -> bool:
        """Update guild configuration"""
        result = await self.db.guilds.update_one(
            {"guild_id": guild_id},
            {"$set": data}
        )
        return result.modified_count > 0

    # Leveling operations
    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get XP leaderboard for guild"""
        cursor = self.db.users.find(
            {"guild_id": guild_id}
        ).sort("xp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    # Economy operations
    async def add_balance(self, user_id: int, guild_id: int, amount: int, session=None) -> bool:
        """Add to user balance"""
        return await self.increment_user_field(
            user_id, guild_id, "balance", amount, session=session
        )

    async def remove_balance(self, user_id: int, guild_id: int, amount: int) -> bool:
        """Remove from user balance"""
        user = await self.get_user(user_id, guild_id)
        if user and user.get("balance", 0) >= amount:
            return await self.increment_user_field(user_id, guild_id, "balance", -amount)
        return False

    async def add_item(self, user_id: int, guild_id: int, item: Dict[str, Any]) -> bool:
        """Add item to user inventory"""
        result = await self.db.users.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {"$push": {"inventory": item}}
        )
        return result.modified_count > 0

    # Checkers operations
    async def record_checkers_result(
        self,
        guild_id: int,
        player_ids: List[int],
        outcome: str,
        game_id: str,
        win_reward: int,
        winner_id: Optional[int] = None,
        loser_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Atomically record a checkers result and reward a winner once.

        The unique processed-game insert, stats writes, and economy write share
        one MongoDB transaction. If any write fails, all of them roll back.
        """
        if len(player_ids) != 2 or len(set(player_ids)) != 2:
            raise ValueError("Exactly two distinct players are required")
        if outcome not in {"win", "draw"}:
            raise ValueError("Outcome must be 'win' or 'draw'")
        if outcome == "win":
            if winner_id is None or loser_id is None:
                raise ValueError("A win requires winner_id and loser_id")
            if {winner_id, loser_id} != set(player_ids):
                raise ValueError("Winner and loser must match player_ids")

        now = datetime.now(timezone.utc)

        async def update_winner(session):
            new_streak = {"$add": [{"$ifNull": ["$current_win_streak", 0]}, 1]}
            return await self.db.checkers_stats.find_one_and_update(
                {"guild_id": guild_id, "user_id": winner_id},
                [{
                    "$set": {
                        "guild_id": guild_id,
                        "user_id": winner_id,
                        "wins": {"$add": [{"$ifNull": ["$wins", 0]}, 1]},
                        "losses": {"$ifNull": ["$losses", 0]},
                        "draws": {"$ifNull": ["$draws", 0]},
                        "points": {"$add": [{"$ifNull": ["$points", 0]}, 3]},
                        "current_win_streak": new_streak,
                        "best_win_streak": {
                            "$max": [{"$ifNull": ["$best_win_streak", 0]}, new_streak]
                        },
                        "current_loss_streak": 0,
                        "worst_loss_streak": {"$ifNull": ["$worst_loss_streak", 0]},
                        "last_played": now
                    }
                }],
                upsert=True,
                return_document=ReturnDocument.AFTER,
                session=session
            )

        async def update_loser(session):
            new_streak = {"$add": [{"$ifNull": ["$current_loss_streak", 0]}, 1]}
            return await self.db.checkers_stats.find_one_and_update(
                {"guild_id": guild_id, "user_id": loser_id},
                [{
                    "$set": {
                        "guild_id": guild_id,
                        "user_id": loser_id,
                        "wins": {"$ifNull": ["$wins", 0]},
                        "losses": {"$add": [{"$ifNull": ["$losses", 0]}, 1]},
                        "draws": {"$ifNull": ["$draws", 0]},
                        "points": {"$ifNull": ["$points", 0]},
                        "current_win_streak": 0,
                        "best_win_streak": {"$ifNull": ["$best_win_streak", 0]},
                        "current_loss_streak": new_streak,
                        "worst_loss_streak": {
                            "$max": [{"$ifNull": ["$worst_loss_streak", 0]}, new_streak]
                        },
                        "last_played": now
                    }
                }],
                upsert=True,
                return_document=ReturnDocument.AFTER,
                session=session
            )

        async def update_draw_player(user_id: int, session):
            return await self.db.checkers_stats.find_one_and_update(
                {"guild_id": guild_id, "user_id": user_id},
                [{
                    "$set": {
                        "guild_id": guild_id,
                        "user_id": user_id,
                        "wins": {"$ifNull": ["$wins", 0]},
                        "losses": {"$ifNull": ["$losses", 0]},
                        "draws": {"$add": [{"$ifNull": ["$draws", 0]}, 1]},
                        "points": {"$add": [{"$ifNull": ["$points", 0]}, 1]},
                        "current_win_streak": 0,
                        "best_win_streak": {"$ifNull": ["$best_win_streak", 0]},
                        "current_loss_streak": 0,
                        "worst_loss_streak": {"$ifNull": ["$worst_loss_streak", 0]},
                        "last_played": now
                    }
                }],
                upsert=True,
                return_document=ReturnDocument.AFTER,
                session=session
            )

        async def transaction_body(session):
            await self.db.checkers_processed.insert_one(
                {
                    "game_id": game_id,
                    "guild_id": guild_id,
                    "player_ids": player_ids,
                    "outcome": outcome,
                    "processed_at": now
                },
                session=session
            )

            if outcome == "draw":
                for player_id in player_ids:
                    await update_draw_player(player_id, session)
                return {
                    "status": "ok",
                    "winner_reward": 0
                }

            # Keep using Jinshi's existing economy write path. The setOnInsert
            # only ensures a first-time player has the normal starting balance.
            await self.db.users.update_one(
                {"user_id": winner_id, "guild_id": guild_id},
                {
                    "$setOnInsert": {
                        "user_id": winner_id,
                        "guild_id": guild_id,
                        "xp": 0,
                        "level": 0,
                        "balance": 1000,
                        "inventory": [],
                        "warnings": [],
                        "created_at": now.timestamp()
                    }
                },
                upsert=True,
                session=session
            )
            rewarded = await self.add_balance(
                winner_id, guild_id, win_reward, session=session
            )
            if not rewarded:
                raise RuntimeError("Winner balance could not be credited")

            winner_stats = await update_winner(session)
            await update_loser(session)
            return {
                "status": "ok",
                "winner_reward": win_reward,
                "winner_streak": winner_stats["current_win_streak"],
                "winner_total_wins": winner_stats["wins"]
            }

        try:
            async with await self.client.start_session() as session:
                return await session.with_transaction(transaction_body)
        except DuplicateKeyError:
            logger.info("Ignoring duplicate checkers result for game_id=%s", game_id)
            return {"status": "already_processed"}

    async def get_checkers_leaderboard(
        self, guild_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Return checkers standings ordered by points, wins, then best streak."""
        cursor = self.db.checkers_stats.find(
            {"guild_id": guild_id}
        ).sort([
            ("points", -1),
            ("wins", -1),
            ("best_win_streak", -1),
            ("losses", 1)
        ]).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_checkers_stats(
        self, guild_id: int, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Return one member's checkers statistics."""
        return await self.db.checkers_stats.find_one({
            "guild_id": guild_id,
            "user_id": user_id
        })

    # Moderation operations
    async def add_warning(self, user_id: int, guild_id: int, warning: Dict[str, Any]) -> bool:
        """Add warning to user"""
        result = await self.db.users.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {"$push": {"warnings": warning}}
        )
        return result.modified_count > 0

    async def get_warnings(self, user_id: int, guild_id: int) -> List[Dict[str, Any]]:
        """Get user warnings"""
        user = await self.get_user(user_id, guild_id)
        return user.get("warnings", []) if user else []

    # Tickets operations
    async def create_ticket(self, ticket_data: Dict[str, Any]) -> str:
        """Create support ticket"""
        result = await self.db.tickets.insert_one(ticket_data)
        return str(result.inserted_id)

    async def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Get ticket by ID"""
        from bson import ObjectId
        return await self.db.tickets.find_one({"_id": ObjectId(ticket_id)})

    async def update_ticket(self, ticket_id: str, data: Dict[str, Any]) -> bool:
        """Update ticket"""
        from bson import ObjectId
        result = await self.db.tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": data}
        )
        return result.modified_count > 0

    # Analytics operations
    async def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log analytics event"""
        now = datetime.now(timezone.utc)
        event = {
            "type": event_type,
            "timestamp": now.timestamp(),  # epoch seconds, for existing query filters
            "created_at": now,             # real BSON date, required for the TTL index
            **data
        }
        await self.db.analytics.insert_one(event)

    async def get_analytics(
        self,
        guild_id: int,
        event_type: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Get analytics events with filters"""
        query = {"guild_id": guild_id}
        if event_type:
            query["type"] = event_type
        if start_time or end_time:
            query["timestamp"] = {}
            if start_time:
                query["timestamp"]["$gte"] = start_time
            if end_time:
                query["timestamp"]["$lte"] = end_time

        cursor = self.db.analytics.find(query).sort("timestamp", -1)
        return await cursor.to_list(length=1000)

    # Reminder operations
    async def create_reminder(self, reminder_data: Dict[str, Any]) -> str:
        """Create reminder"""
        result = await self.db.reminders.insert_one(reminder_data)
        return str(result.inserted_id)

    async def get_due_reminders(self, current_time: float) -> List[Dict[str, Any]]:
        """Get reminders that are due"""
        cursor = self.db.reminders.find({
            "remind_at": {"$lte": current_time},
            "completed": False
        })
        return await cursor.to_list(length=100)

    async def complete_reminder(self, reminder_id: str) -> bool:
        """Mark reminder as completed"""
        from bson import ObjectId
        result = await self.db.reminders.update_one(
            {"_id": ObjectId(reminder_id)},
            {"$set": {"completed": True}}
        )
        return result.modified_count > 0

    # Shop operations
    async def get_shop_items(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get shop items for guild"""
        cursor = self.db.shop.find({"guild_id": guild_id})
        return await cursor.to_list(length=100)

    async def create_shop_item(self, item_data: Dict[str, Any]) -> str:
        """Create shop item"""
        result = await self.db.shop.insert_one(item_data)
        return str(result.inserted_id)
