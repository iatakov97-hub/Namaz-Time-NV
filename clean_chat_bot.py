"""Apply private-chat cleanup to both replies and scheduled text messages."""
from telegram.ext import ExtBot


class CleanChatBot(ExtBot):
    __slots__ = ('_latest_messages', '_widget_sender')

    def __init__(self, token, latest_messages, widget_sender=None):
        super().__init__(token=token)
        object.__setattr__(self, '_latest_messages', latest_messages)
        object.__setattr__(self, '_widget_sender', widget_sender)

    async def send_message(self, *args, **kwargs):
        chat_id = args[0] if args else kwargs.get('chat_id')
        parent_send = super().send_message
        return await self._latest_messages.send(
            chat_id,
            lambda: parent_send(*args, **kwargs),
            super().delete_message,
        )

    async def send_widget(self, chat_id, keyboard=None):
        if self._widget_sender is None:
            raise RuntimeError('Widget sender not configured')
        return await self._latest_messages.send(
            chat_id,
            lambda: self._widget_sender.send(chat_id, keyboard, super(CleanChatBot, self).delete_message),
            super().delete_message,
            persistent=True,
        )
