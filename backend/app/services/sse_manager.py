"""Server-Sent Events (SSE) manager with Redis Pub/Sub and in-memory fallback.

When Redis is available, uses Redis Pub/Sub for cross-process broadcasting.
When Redis is unavailable (local dev), falls back to asyncio.Queue-based
in-memory broadcasting so SSE notifications still work.
"""
import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional
from fastapi import Request

from app.config import settings

logger = logging.getLogger(__name__)

# Attempt Redis import
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None  # type: ignore
    REDIS_AVAILABLE = False


class InMemoryPubSub:
    """Fallback in-memory pub/sub for when Redis is unavailable."""

    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, message: str) -> None:
        async with self._lock:
            queues = self._subscribers.get(channel, [])
            for q in list(queues):
                try:
                    q.put_nowait(message)
                except asyncio.QueueFull:
                    pass  # Drop oldest if full

    async def subscribe(self, channel: str, queue: Optional[asyncio.Queue] = None) -> asyncio.Queue:
        async with self._lock:
            if queue is None:
                queue = asyncio.Queue(maxsize=256)
            sub_list = self._subscribers.setdefault(channel, [])
            if queue not in sub_list:
                sub_list.append(queue)
            return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            queues = self._subscribers.get(channel, [])
            try:
                queues.remove(queue)
            except ValueError:
                pass
            if not queues:
                self._subscribers.pop(channel, None)


class SSEManager:
    """Manages Server-Sent Events broadcasting using Redis async Pub/Sub with in-memory fallback."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis = None
        self._redis_available = False
        self._fallback = InMemoryPubSub()
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Lazily initialize Redis connection, falling back to in-memory if unavailable."""
        if self._redis is not None:
            self._redis_available = True
            return

        if self._initialized:
            return
        self._initialized = True

        if not REDIS_AVAILABLE:
            logger.info("Redis library not installed; SSE using in-memory pub/sub fallback")
            return

        try:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            self._redis_available = True
            logger.info(f"SSE connected to Redis at {self.redis_url}")
        except Exception as e:
            logger.warning(
                f"Redis unavailable ({e}); SSE falling back to in-memory pub/sub. "
                "Real-time notifications will work within this process only."
            )
            self._redis = None
            self._redis_available = False

    async def publish(self, channel: str, message: dict) -> None:
        """
        Publish a JSON-serializable message dictionary to a channel.
        Uses Redis if available, otherwise falls back to in-memory.
        """
        await self._ensure_initialized()
        payload = json.dumps(message)

        if self._redis_available and self._redis:
            try:
                await self._redis.publish(channel, payload)
                return
            except Exception as e:
                logger.warning(f"Redis publish failed for channel {channel}: {e}; using in-memory fallback")

        await self._fallback.publish(channel, payload)

    async def event_generator(
        self, channel: str | List[str], request: Request
    ) -> AsyncGenerator[str, None]:
        """
        Subscribes to one or more channels and yields formatted SSE messages.
        Includes a 30-second ':ping\\n\\n' keepalive heartbeat.
        """
        await self._ensure_initialized()
        channels = [channel] if isinstance(channel, str) else list(channel)

        if self._redis_available and self._redis:
            async for chunk in self._redis_event_generator(channels, request):
                yield chunk
        else:
            async for chunk in self._memory_event_generator(channels, request):
                yield chunk

    async def _redis_event_generator(
        self, channels: List[str], request: Request
    ) -> AsyncGenerator[str, None]:
        """SSE generator using Redis Pub/Sub."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(*channels)
        last_ping_time = time.monotonic()

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                except Exception as e:
                    logger.warning(f"Error reading message from Redis pubsub on {channels}: {e}")
                    message = None

                now = time.monotonic()

                if message is not None:
                    event_data = message.get("data")
                    if isinstance(event_data, str):
                        try:
                            parsed = json.loads(event_data)
                            event_name = parsed.pop("event", "sighting")
                            yield f"event: {event_name}\ndata: {json.dumps(parsed)}\n\n"
                        except json.JSONDecodeError:
                            yield f"data: {event_data}\n\n"
                    last_ping_time = now

                if now - last_ping_time >= 30.0:
                    yield ":ping\n\n"
                    last_ping_time = now

        except asyncio.CancelledError:
            logger.debug(f"SSE stream cancelled for channels {channels}")
        finally:
            try:
                await pubsub.unsubscribe(*channels)
                await pubsub.close()
            except Exception as e:
                logger.debug(f"Error closing pubsub on channels {channels}: {e}")

    async def _memory_event_generator(
        self, channels: List[str], request: Request
    ) -> AsyncGenerator[str, None]:
        """SSE generator using in-memory pub/sub fallback."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        for ch in channels:
            await self._fallback.subscribe(ch, queue=queue)

        last_ping_time = time.monotonic()

        try:
            while True:
                if await request.is_disconnected():
                    break

                now = time.monotonic()

                try:
                    message = await asyncio.wait_for(queue.get(), timeout=1.0)
                    if isinstance(message, str):
                        try:
                            parsed = json.loads(message)
                            event_name = parsed.pop("event", "sighting")
                            yield f"event: {event_name}\ndata: {json.dumps(parsed)}\n\n"
                        except json.JSONDecodeError:
                            yield f"data: {message}\n\n"
                    last_ping_time = now
                except asyncio.TimeoutError:
                    pass

                now = time.monotonic()
                if now - last_ping_time >= 30.0:
                    yield ":ping\n\n"
                    last_ping_time = now

        except asyncio.CancelledError:
            logger.debug(f"In-memory SSE stream cancelled for channels {channels}")
        finally:
            for ch in channels:
                await self._fallback.unsubscribe(ch, queue)


sse_manager = SSEManager()
