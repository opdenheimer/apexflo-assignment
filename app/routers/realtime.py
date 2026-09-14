import asyncio
import json
import logging
from typing import Dict, Set, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import redis.asyncio as aioredis

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Realtime & Stock Sync"])

class ConnectionManager:
    """Manages active patron WebSocket connections partitioned by show_id."""
    def __init__(self):
        # show_id -> set of active WebSockets
        self.active_rooms: Dict[int, Set[WebSocket]] = {}
        # Stores the latest processed version per show_id:menu_item_id to discard older out-of-order events
        self.latest_versions: Dict[str, int] = {}

    async def connect(self, show_id: int, websocket: WebSocket):
        await websocket.accept()
        if show_id not in self.active_rooms:
            self.active_rooms[show_id] = set()
        self.active_rooms[show_id].add(websocket)
        logger.info(f"Patron connected to show {show_id}. Active count: {len(self.active_rooms[show_id])}")

    def disconnect(self, show_id: int, websocket: WebSocket):
        if show_id in self.active_rooms:
            self.active_rooms[show_id].discard(websocket)
            if not self.active_rooms[show_id]:
                del self.active_rooms[show_id]
        logger.info(f"Patron disconnected from show {show_id}")

    async def broadcast_to_show(self, show_id: int, message: dict):
        if show_id not in self.active_rooms:
            return
        dead_sockets = set()
        for ws in self.active_rooms[show_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.add(ws)
        for ws in dead_sockets:
            self.active_rooms[show_id].discard(ws)

    def is_event_stale(self, show_id: int, menu_item_id: int, incoming_version: int) -> bool:
        """
        Version Check (Architecture Requirement):
        Ignore/drop events whose version is <= currently recorded version for this item/show.
        This prevents race conditions or out-of-order event delivery from corrupting display projections.
        """
        key = f"{show_id}:{menu_item_id}"
        current_version = self.latest_versions.get(key, -1)
        if incoming_version <= current_version:
            return True  # Out-of-order or duplicate, drop it
        self.latest_versions[key] = incoming_version
        return False

manager = ConnectionManager()

# -------------------------------------------------------------
# WebSocket Endpoint for Patrons: /ws/stock/{show_id}
# -------------------------------------------------------------
@router.websocket("/ws/stock/{show_id}")
async def stock_websocket_endpoint(websocket: WebSocket, show_id: int):
    await manager.connect(show_id, websocket)
    try:
        while True:
            # Keepalive / heartbeat
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(show_id, websocket)
    except Exception as e:
        logger.warning(f"WebSocket error for show {show_id}: {e}")
        manager.disconnect(show_id, websocket)

# -------------------------------------------------------------
# Background Worker: Redis Streams Event Consumer
# -------------------------------------------------------------
async def start_stock_event_consumer(redis_client: aioredis.Redis):
    """
    Background worker that continuously consumes from `stock-events` Redis Stream.
    - Reads new StockChanged events.
    - Applies version check (drops old/out-of-order events).
    - Updates local projections.
    - Pushes live updates over WebSockets to patrons.
    """
    stream_name = "stock-events"
    group_name = "stock-sync-group"
    consumer_name = "stock-worker-1"

    # Ensure stream and consumer group exist
    try:
        await redis_client.xgroup_create(stream_name, group_name, id="$", mkstream=True)
    except Exception:
        # Group already exists
        pass

    logger.info("Starting Redis Streams stock event consumer...")

    while True:
        try:
            # Read from group
            entries = await redis_client.xreadgroup(
                groupname=group_name,
                consumername=consumer_name,
                streams={stream_name: ">"},
                count=10,
                block=2000,
            )

            if not entries:
                await asyncio.sleep(0.05)
                continue

            for stream, messages in entries:
                for msg_id, payload in messages:
                    event_type = payload.get("event_type")
                    if event_type == "StockChanged":
                        show_id = int(payload.get("show_id"))
                        menu_item_id = int(payload.get("menu_item_id"))
                        new_quantity = int(payload.get("new_quantity"))
                        version = int(payload.get("version"))

                        # Check version ordering
                        if manager.is_event_stale(show_id, menu_item_id, version):
                            logger.info(f"Dropped out-of-order event for item {menu_item_id} (version {version})")
                        else:
                            # Push via WebSocket
                            broadcast_msg = {
                                "type": "STOCK_UPDATE",
                                "show_id": show_id,
                                "menu_item_id": menu_item_id,
                                "quantity": new_quantity,
                                "version": version,
                                "is_available": new_quantity > 0,
                            }
                            await manager.broadcast_to_show(show_id, broadcast_msg)

                    # Acknowledge processed message
                    await redis_client.xack(stream_name, group_name, msg_id)

        except asyncio.CancelledError:
            logger.info("Stock event consumer cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in stock event consumer loop: {e}")
            await asyncio.sleep(1)
