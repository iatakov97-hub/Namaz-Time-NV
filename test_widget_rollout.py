import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import rollout_widgets as rollout
from widget_delivery import WidgetError


class FakeBot:
    def __init__(self,*args):
        self.send_widget=AsyncMock(side_effect=self.send)
        self.calls=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def get_me(self):return SimpleNamespace(username='namaznv_bot')
    async def send(self,uid,keyboard):
        self.calls.append(uid)
        if uid==3:raise WidgetError(403)
        if uid==4:raise WidgetError(400)


class RolloutTests(unittest.IsolatedAsyncioTestCase):
    async def test_skip_delivered_and_continue_past_blocked_users(self):
        fake=FakeBot()
        with patch.multiple(rollout,init_db=lambda:None,load_users=lambda:{'1':{},'2':{},'3':{},'4':{}},
                load_user_widget=lambda uid:(100,'v1') if uid==1 else None,
                WidgetSender=lambda *args:SimpleNamespace(version='v1'),CleanChatBot=lambda *args:fake), \
                patch.object(rollout.asyncio,'sleep',new=AsyncMock()):
            result=await rollout.rollout(send=True)
        self.assertEqual(fake.calls,[2,3,4])
        self.assertEqual(result,dict(total=4,pending=3,skipped=1,delivered=1,blocked=1,failed=1))

    async def test_preview_does_not_send(self):
        fake=FakeBot()
        with patch.multiple(rollout,init_db=lambda:None,load_users=lambda:{'1':{}},
                load_user_widget=lambda uid:None,WidgetSender=lambda *args:SimpleNamespace(version='v1'),
                CleanChatBot=lambda *args:fake):
            result=await rollout.rollout(send=False)
        self.assertEqual(result['pending'],1)
        self.assertEqual(fake.calls,[])

if __name__=='__main__':unittest.main()
