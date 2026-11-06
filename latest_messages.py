"""Keep the most recent text response in private chats; widgets are separate."""
import asyncio
import logging
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

logger = logging.getLogger(__name__)
_batch = ContextVar('outgoing_message_batch', default=None)


def grouped_response(callback):
    """Keep all chunks of one command response until the next response arrives."""
    @wraps(callback)
    async def wrapped(*args, **kwargs):
        token = _batch.set(uuid4().hex)
        try:
            return await callback(*args, **kwargs)
        finally:
            _batch.reset(token)
    return wrapped


class LatestMessages:
    def __init__(self, load, save):
        self.load = load
        self.save = save
        self.locks = {}

    async def send(self, chat_id, send, delete):
        # Only positive numeric IDs identify private chats. Do not delete group posts.
        try:
            private_id = int(chat_id)
        except (TypeError, ValueError):
            return await send()
        if private_id <= 0:
            return await send()
        lock = self.locks.setdefault(private_id, asyncio.Lock())
        async with lock:
            batch = _batch.get() or uuid4().hex
            try:
                previous = await asyncio.to_thread(self.load, private_id)
            except Exception:
                logger.warning('Cannot load outgoing state for %s; keeping old messages', private_id)
                return await send()
            # Never delete anything until Telegram confirms the new message was sent.
            message = await send()
            old_batch, old_ids = previous if previous else (None, [])
            same_batch = old_batch == batch
            ids = [*old_ids, message.message_id] if same_batch else [message.message_id]
            try:
                await asyncio.to_thread(self.save, private_id, batch, ids)
            except Exception:
                logger.warning('Cannot save outgoing state for %s; keeping old messages', private_id)
                return message
            if not same_batch:
                for old_id in old_ids:
                    try:
                        await delete(chat_id=private_id, message_id=old_id)
                    except Exception:
                        # Already deleted, older than 48 h, or Telegram temporarily unavailable.
                        logger.info('Could not remove previous bot message %s in %s', old_id, private_id)
            return message
