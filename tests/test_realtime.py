import pytest
import asyncio
from app.routers.realtime import ConnectionManager

def test_version_check_drops_older_out_of_order_events():
    """
    Test Phase 8 Requirement:
    Version check on the consumer side must drop/ignore an event older than the currently stored version.
    """
    manager = ConnectionManager()
    show_id = 101
    item_id = 5

    # Event 1: Version 1 arrives -> should NOT be stale
    assert manager.is_event_stale(show_id, item_id, incoming_version=1) is False

    # Event 2: Version 3 arrives -> should NOT be stale
    assert manager.is_event_stale(show_id, item_id, incoming_version=3) is False

    # Event 3: Out-of-order delayed Event (Version 2 arrives late) -> MUST BE STALE (DROPPED)
    assert manager.is_event_stale(show_id, item_id, incoming_version=2) is True

    # Event 4: Duplicate Event (Version 3 arrives again) -> MUST BE STALE (DROPPED)
    assert manager.is_event_stale(show_id, item_id, incoming_version=3) is True

    # Event 5: Version 4 arrives -> valid newer event
    assert manager.is_event_stale(show_id, item_id, incoming_version=4) is False

@pytest.mark.asyncio
async def test_connection_manager_broadcast_and_disconnect():
    """Verify WebSocket connection tracking and broadcast dispatch."""
    manager = ConnectionManager()
    show_id = 202

    class MockWebSocket:
        def __init__(self):
            self.sent_messages = []
            self.is_accepted = False

        async def accept(self):
            self.is_accepted = True

        async def send_json(self, data):
            self.sent_messages.append(data)

    ws1 = MockWebSocket()
    ws2 = MockWebSocket()

    await manager.connect(show_id, ws1)
    await manager.connect(show_id, ws2)

    assert len(manager.active_rooms[show_id]) == 2

    # Broadcast stock update
    msg = {"type": "STOCK_UPDATE", "menu_item_id": 1, "quantity": 0}
    await manager.broadcast_to_show(show_id, msg)

    assert len(ws1.sent_messages) == 1
    assert ws1.sent_messages[0]["quantity"] == 0
    assert len(ws2.sent_messages) == 1

    # Disconnect ws1
    manager.disconnect(show_id, ws1)
    assert len(manager.active_rooms[show_id]) == 1

    # Disconnect ws2 -> room deleted
    manager.disconnect(show_id, ws2)
    assert show_id not in manager.active_rooms
