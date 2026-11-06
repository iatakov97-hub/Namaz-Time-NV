"""Apply private-chat cleanup to both replies and scheduled text messages."""
from telegram.ext import ExtBot


class CleanChatBot(ExtBot):
    __slots__ = ('_latest_messages',)

    def __init__(self, token, latest_messages):
        super().__init__(token=token)
        object.__setattr__(self, '_latest_messages', latest_messages)

    async def send_message(self, *args, **kwargs):
        chat_id = args[0] if args else kwargs.get('chat_id')
        parent_send = super().send_message
        return await self._latest_messages.send(
            chat_id,
            lambda: parent_send(*args, **kwargs),
            super().delete_message,
        )
