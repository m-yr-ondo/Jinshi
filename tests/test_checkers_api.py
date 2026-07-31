from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from web.api import create_app
from database.db_manager import DatabaseManager
from pymongo.errors import DuplicateKeyError


GUILD_ID = 123456789012345678
PLAYER_ONE = 111111111111111111
PLAYER_TWO = 222222222222222222


class FakeGuild:
    def __init__(self):
        self.members = {
            PLAYER_ONE: SimpleNamespace(bot=False),
            PLAYER_TWO: SimpleNamespace(bot=False)
        }

    def get_member(self, user_id):
        return self.members.get(user_id)


def make_client(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "test-secret")
    bot = SimpleNamespace(
        config={"modules": {"checkers": {"enabled": True, "win_reward": 150}}},
        db=SimpleNamespace(record_checkers_result=AsyncMock(return_value={
            "status": "ok",
            "winner_reward": 150,
            "winner_streak": 2,
            "winner_total_wins": 3
        })),
        guilds=[],
        user=None,
        get_guild=lambda guild_id: FakeGuild() if guild_id == GUILD_ID else None
    )
    return TestClient(create_app(bot)), bot


def win_payload():
    return {
        "guild_id": str(GUILD_ID),
        "game_id": "room-unique-game-id",
        "outcome": "win",
        "reason": "captured",
        "player_ids": [str(PLAYER_ONE), str(PLAYER_TWO)],
        "winner_id": str(PLAYER_ONE),
        "loser_id": str(PLAYER_TWO)
    }


def test_checkers_result_rejects_bad_secret(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.post(
        "/internal/checkers-result",
        json=win_payload(),
        headers={"X-Internal-Secret": "wrong"}
    )
    assert response.status_code == 401


def test_checkers_result_validates_and_records_win(monkeypatch):
    client, bot = make_client(monkeypatch)
    response = client.post(
        "/internal/checkers-result",
        json=win_payload(),
        headers={"X-Internal-Secret": "test-secret"}
    )
    assert response.status_code == 200
    assert response.json()["winner_reward"] == 150
    bot.db.record_checkers_result.assert_awaited_once_with(
        guild_id=GUILD_ID,
        player_ids=[PLAYER_ONE, PLAYER_TWO],
        outcome="win",
        game_id="room-unique-game-id",
        win_reward=150,
        winner_id=PLAYER_ONE,
        loser_id=PLAYER_TWO
    )


def test_checkers_draw_has_no_winner(monkeypatch):
    client, bot = make_client(monkeypatch)
    payload = win_payload()
    payload.update({"outcome": "draw", "reason": "repetition"})
    payload.pop("winner_id")
    payload.pop("loser_id")

    response = client.post(
        "/internal/checkers-result",
        json=payload,
        headers={"X-Internal-Secret": "test-secret"}
    )
    assert response.status_code == 200
    call = bot.db.record_checkers_result.await_args.kwargs
    assert call["winner_id"] is None
    assert call["loser_id"] is None


def test_checkers_result_rejects_malformed_players(monkeypatch):
    client, _ = make_client(monkeypatch)
    payload = win_payload()
    payload["player_ids"] = [str(PLAYER_ONE), str(PLAYER_ONE)]
    response = client.post(
        "/internal/checkers-result",
        json=payload,
        headers={"X-Internal-Secret": "test-secret"}
    )
    assert response.status_code == 400


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def with_transaction(self, callback):
        return await callback(self)


class FakeClient:
    async def start_session(self):
        return FakeSession()


class DuplicateResults:
    async def insert_one(self, *_args, **_kwargs):
        raise DuplicateKeyError("duplicate game")


async def test_duplicate_game_short_circuits_without_reward():
    manager = DatabaseManager("mongodb://unused", "unused")
    manager.client = FakeClient()
    manager.db = SimpleNamespace(checkers_processed=DuplicateResults())

    result = await manager.record_checkers_result(
        guild_id=GUILD_ID,
        player_ids=[PLAYER_ONE, PLAYER_TWO],
        outcome="win",
        game_id="already-recorded-game",
        win_reward=150,
        winner_id=PLAYER_ONE,
        loser_id=PLAYER_TWO
    )
    assert result == {"status": "already_processed"}
