"""Send the approved self-contained widget through Telegram's widget API."""
import asyncio
import hashlib
import logging
from pathlib import Path
from types import SimpleNamespace
import zlib

import httpx

logger = logging.getLogger(__name__)
WIDGET_HTML = Path(__file__).with_name('prayer_widget.html').read_text(encoding='utf-8')
WIDGET_VERSION = hashlib.sha256(WIDGET_HTML.encode()).hexdigest()[:16]
UPDATE_URL = 'https://telegram.org/dl'
CAPTION = ('Не видно живого расписания? <a href="' + UPDATE_URL + '">Обновите Telegram</a>. '
           'Текстовое расписание: /today')


class WidgetError(Exception):
    def __init__(self, code, retry_after=None):
        super().__init__(f'Widget delivery failed ({code})')
        self.code = code
        self.retry_after = retry_after


class WidgetSender:
    def __init__(self, token, load, save, html=WIDGET_HTML, client_factory=httpx.AsyncClient):
        raw = html.encode('utf-8')
        if len(raw) > 32768 or len(zlib.compress(raw, 9)) > 3900:
            raise ValueError('Widget exceeds Telegram size limit')
        self.html = html
        self.version = hashlib.sha256(raw).hexdigest()[:16]
        self.load = load
        self.save = save
        self.client_factory = client_factory
        self.url = f'https://api.telegram.org/beta/bot{token}/sendWidget'

    async def send(self, chat_id, keyboard, delete):
        if int(chat_id) <= 0:
            raise WidgetError('private_chat_required')
        # Do not send if we cannot read the prior widget ID from storage.
        previous = await asyncio.to_thread(self.load, chat_id)
        payload = dict(chat_id=chat_id, html=self.html, width=0, height=0, caption=CAPTION, parse_mode='HTML')
        if keyboard is not None:
            payload['reply_markup'] = keyboard.to_dict()
        try:
            async with self.client_factory(timeout=30) as client:
                response = await client.post(self.url, json=payload)
                body = response.json()
        except (httpx.RequestError, ValueError):
            raise WidgetError('connection_or_response') from None
        if not body.get('ok'):
            raise WidgetError(body.get('error_code', response.status_code),
                              body.get('parameters', {}).get('retry_after'))
        result = body.get('result', {})
        message_id = result.get('message_id')
        if not isinstance(message_id, int) or 'widget' not in result:
            raise WidgetError('invalid_widget_response')
        try:
            await asyncio.to_thread(self.save, chat_id, message_id, self.version)
        except Exception:
            # The new widget exists: do not send a second copy or remove the old one.
            logger.warning('Widget sent but its ID could not be saved for %s', chat_id)
            return SimpleNamespace(message_id=message_id)
        if previous and previous[0] != message_id:
            try:
                await delete(chat_id=chat_id, message_id=previous[0])
            except Exception:
                logger.info('Could not remove previous widget in %s', chat_id)
        return SimpleNamespace(message_id=message_id)
