"""Keep the most recent text response in private chats; widgets are separate."""
import asyncio
import logging
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

logger = logging.getLogger(__name__)
_batch = ContextVar('outgoing_message_batch', default=None)
_sent_chats = ContextVar('response_sent_chats', default=None)


def grouped_response(callback):
    """Keep all chunks of one command response until the next response arrives."""
    @wraps(callback)
    async def wrapped(*args, **kwargs):
        token = _batch.set(uuid4().hex)
        sent_chats = set()
        sent_token = _sent_chats.set(sent_chats)
        try:
            result = await callback(*args, **kwargs)
            # Keep unknown text, ignored commands and failed commands.
            update = args[0] if args else kwargs.get('update')
            message = getattr(update, 'message', None)
            if (message is not None and message.chat.type == 'private'
                    and message.chat.id in sent_chats):
                try:
                    await message.delete()
                except Exception:
                    logger.info('Could not remove command %s in %s', message.message_id, message.chat.id)
            return result
        finally:
            _sent_chats.reset(sent_token)
            _batch.reset(token)
    return wrapped


async def _deliver(send, chat_id):
    message = await send()
    sent_chats = _sent_chats.get()
    if sent_chats is not None:
        try:
            sent_chats.add(int(chat_id))
        except (TypeError, ValueError):
            pass
    return message


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
            return await _deliver(send, chat_id)
        if private_id <= 0:
            return await _deliver(send, chat_id)
        lock = self.locks.setdefault(private_id, asyncio.Lock())
        async with lock:
            batch = _batch.get() or uuid4().hex
            try:
                previous = await asyncio.to_thread(self.load, private_id)
            except Exception:
                logger.warning('Cannot load outgoing state for %s; keeping old messages', private_id)
                return await _deliver(send, chat_id)
            # Never delete anything until Telegram confirms the new message was sent.
            message = await _deliver(send, private_id)
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
