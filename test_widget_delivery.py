import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx

from widget_delivery import WidgetSender, WidgetError
from latest_messages import LatestMessages, grouped_response
from clean_chat_bot import CleanChatBot


class WidgetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rows = {}
        self.deleted = AsyncMock()
        self.state = {}
        self.last = LatestMessages(self.state.get, lambda uid, batch, ids:self.state.update({uid:(batch,ids)}))
        self.requests = []

    def factory(self, body, status=200):
        def handler(request):
            self.requests.append(request)
            return httpx.Response(status, json=body)
        return lambda **kwargs:httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    def sender(self, body=None, status=200):
        if body is None:
            body={'ok':True,'result':{'message_id':100,'widget':{}}}
        return WidgetSender('123:fake', self.rows.get,
                            lambda uid, mid, ver:self.rows.update({uid:(mid,ver)}),
                            client_factory=self.factory(body,status))

    async def test_persistent_widget_survives_notification(self):
        self.state[42]=('old',[9])
        widget=AsyncMock(return_value=SimpleNamespace(message_id=100))
        await self.last.send(42,widget,self.deleted,persistent=True)
        self.deleted.assert_awaited_once_with(chat_id=42,message_id=9)
        self.deleted.reset_mock()
        await self.last.send(42,AsyncMock(return_value=SimpleNamespace(message_id=101)),self.deleted)
        self.deleted.assert_not_awaited()
        self.assertEqual(self.state[42][1],[101])

    async def test_widget_replacement_saved_before_old_deleted(self):
        self.rows[42]=(99,'old')
        sender=self.sender()
        async def delete(**kwargs):
            self.assertEqual(self.rows[42][0],100)
            self.assertEqual(kwargs['message_id'],99)
        result=await sender.send(42,None,delete)
        self.assertEqual(result.message_id,100)
        self.assertEqual(self.rows[42][1],sender.version)

    async def test_failed_widget_preserves_previous(self):
        self.rows[42]=(99,'old')
        sender=self.sender({'ok':False,'error_code':400},400)
        with self.assertRaises(WidgetError):await sender.send(42,None,self.deleted)
        self.assertEqual(self.rows[42],(99,'old'))
        self.deleted.assert_not_awaited()

    async def test_storage_failure_after_delivery_does_not_delete(self):
        sender=self.sender()
        sender.save=lambda *args:(_ for _ in ()).throw(RuntimeError())
        result=await sender.send(42,None,self.deleted)
        self.assertEqual(result.message_id,100)
        self.deleted.assert_not_awaited()

    async def test_old_widget_delete_failure_does_not_fail_delivery(self):
        self.rows[42]=(99,'old')
        self.deleted.side_effect=RuntimeError()
        result=await self.sender().send(42,None,self.deleted)
        self.assertEqual(result.message_id,100)

    async def test_widget_reply_triggers_command_cleanup(self):
        sender=self.sender()
        bot=CleanChatBot('123:fake',self.last,sender)
        message=SimpleNamespace(chat=SimpleNamespace(id=42,type='private'),message_id=4,delete=AsyncMock())
        @grouped_response
        async def command(update,context):await bot.send_widget(42)
        await command(SimpleNamespace(message=message),None)
        message.delete.assert_awaited_once()
        self.assertEqual(self.state[42][1],[])

    async def test_keyboard_and_caption_are_sent(self):
        import json
        keyboard=SimpleNamespace(to_dict=lambda:{'keyboard':[['widget','text']]})
        await self.sender().send(42,keyboard,self.deleted)
        payload=json.loads(self.requests[0].content)
        self.assertIn('/today',payload['caption'])
        self.assertEqual(payload['reply_markup']['keyboard'][0][0],'widget')

    async def test_rate_limit_is_reported_without_duplicate_send(self):
        sender=self.sender({'ok':False,'error_code':429,'parameters':{'retry_after':2}},429)
        with self.assertRaises(WidgetError) as error:await sender.send(42,None,self.deleted)
        self.assertEqual(error.exception.retry_after,2)
        self.assertEqual(len(self.requests),1)

    async def test_widget_failure_falls_back_to_text(self):
        import bot
        update=SimpleNamespace(effective_chat=SimpleNamespace(id=42,type='private'))
        context=SimpleNamespace(bot=SimpleNamespace(send_widget=AsyncMock(side_effect=WidgetError(404))))
        with patch.object(bot,'cmd_today',new=AsyncMock()) as text:
            await bot.cmd_widget(update,context)
            text.assert_awaited_once_with(update,context)

    async def test_legacy_button_still_opens_widget(self):
        import bot
        for label in ['🕐 Следующий намаз','🕌 Время намазов']:
            update=SimpleNamespace(message=SimpleNamespace(text=label))
            with patch.object(bot,'cmd_next',new=AsyncMock()) as handler:
                await bot.button_handler(update,None)
                handler.assert_awaited_once()

if __name__=='__main__':unittest.main()
