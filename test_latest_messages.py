import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from latest_messages import LatestMessages, grouped_response


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = {}
        self.sent = 0
        self.deleted = []
        self.manager = LatestMessages(self.state.get, self.save)

    def save(self, chat, batch, ids):
        self.state[chat] = (batch, list(ids))

    async def send(self):
        self.sent += 1
        return SimpleNamespace(message_id=self.sent)

    async def delete(self, **kwargs):
        self.deleted.append(kwargs['message_id'])

    async def emit(self, chat=42):
        return await self.manager.send(chat, self.send, self.delete)

    async def test_restart_keeps_previous_id_and_deletes_after_new_send(self):
        await self.emit()
        self.manager = LatestMessages(self.state.get, self.save)
        await self.emit()
        self.assertEqual(self.deleted, [1])
        self.assertEqual(self.state[42][1], [2])

    async def test_failed_send_preserves_previous(self):
        await self.emit()
        failing = AsyncMock(side_effect=RuntimeError('send failed'))
        with self.assertRaises(RuntimeError):
            await self.manager.send(42, failing, self.delete)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.state[42][1], [1])

    async def test_multipart_response_survives_until_next_response(self):
        @grouped_response
        async def multipart():
            await self.emit()
            await self.emit()
        await multipart()
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.state[42][1], [1, 2])
        await self.emit()
        self.assertEqual(self.deleted, [1, 2])

    async def test_concurrent_sends_leave_only_last(self):
        await asyncio.gather(*(self.emit() for _ in range(5)))
        self.assertEqual(self.deleted, [1, 2, 3, 4])
        self.assertEqual(self.state[42][1], [5])

    async def test_group_posts_are_not_removed(self):
        await self.emit(-42)
        await self.emit(-42)
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.state, {})

    async def test_failed_storage_does_not_delete(self):
        await self.emit()
        self.manager.save = lambda *args: (_ for _ in ()).throw(RuntimeError())
        await self.emit()
        self.assertEqual(self.deleted, [])

    async def test_deleted_or_old_message_does_not_block_new(self):
        await self.emit()
        result = await self.manager.send(42, self.send, AsyncMock(side_effect=RuntimeError()))
        self.assertEqual(result.message_id, 2)
        self.assertEqual(self.state[42][1], [2])

    async def test_ptb_reply_and_direct_send_use_cleanup(self):
        from clean_chat_bot import CleanChatBot
        from telegram import Message
        from telegram.ext import ExtBot, Application
        bot = CleanChatBot('123456:testing', self.manager)
        app = Application.builder().bot(bot).build()
        self.assertIs(app.bot, bot)
        incoming = Message.de_json({'message_id':55,'date':1,'chat':{'id':42,'type':'private'},'text':'/today'}, bot)
        with patch.object(ExtBot, 'send_message', new=AsyncMock(side_effect=self.send_args)), patch.object(ExtBot, 'delete_message', new=AsyncMock(side_effect=self.delete)):
            await incoming.reply_text('reply')
            await bot.send_message(42, 'notification')
        self.assertEqual(self.deleted, [1])

    async def send_args(self, *args, **kwargs):
        return await self.send()

if __name__ == '__main__':
    unittest.main()
