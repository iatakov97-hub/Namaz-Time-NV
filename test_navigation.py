import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from datetime import datetime
import bot


class NavigationTests(unittest.IsolatedAsyncioTestCase):
    def update(self,text='/next'):
        return SimpleNamespace(message=SimpleNamespace(text=text,reply_text=AsyncMock()),
            effective_chat=SimpleNamespace(id=42,type='private'),effective_user=SimpleNamespace(id=42))

    async def test_four_buttons_with_distinct_roles(self):
        labels=[[b.text for b in row] for row in bot.MAIN_KEYBOARD.keyboard]
        self.assertEqual(labels,[['🗓 Расписание на месяц','⏳ Следующий намаз'],['📅 Намазы сегодня','🕌 Живое расписание']])
        routes={'📅 Намазы сегодня':'cmd_today','⏳ Следующий намаз':'cmd_next',
                '🕌 Живое расписание':'cmd_widget','🗓 Расписание на месяц':'cmd_month',
                '📅 Намазы на сегодня':'cmd_today','🕐 Следующий намаз':'cmd_next',
                '🕌 Время намазов':'cmd_widget','🔔 Уведомления':'cmd_notifications'}
        for label,target in routes.items():
            with self.subTest(label=label),patch.multiple(bot,cmd_today=AsyncMock(),cmd_next=AsyncMock(),cmd_widget=AsyncMock(),cmd_month=AsyncMock(),cmd_notifications=AsyncMock()):
                update=self.update(label)
                await bot.button_handler(update,None)
                getattr(bot,target).assert_awaited_once_with(update,None)
                for other in set(routes.values())-{target}:getattr(bot,other).assert_not_awaited()

    async def test_next_is_text_and_does_not_request_widget(self):
        update=self.update()
        context=SimpleNamespace(bot=SimpleNamespace(send_widget=AsyncMock()))
        now=bot.TZ.localize(datetime(2026,11,6,14,0))
        with patch.object(bot,'now_local',return_value=now):await bot.cmd_next(update,context)
        context.bot.send_widget.assert_not_awaited()
        update.message.reply_text.assert_awaited_once()
        text=update.message.reply_text.call_args.args[0]
        self.assertIn('Магриб',text)
        self.assertIn('15:44',text)

    async def test_next_skips_sunrise(self):
        now=bot.TZ.localize(datetime(2026,11,6,6,30))
        key,time=bot.get_next_prayer(bot.get_day_schedule(11,6),now)
        self.assertEqual(key,'dhuhr')

    async def test_next_after_isha_uses_tomorrow_fajr(self):
        update=self.update()
        now=bot.TZ.localize(datetime(2026,11,6,23,30))
        with patch.object(bot,'now_local',return_value=now):await bot.cmd_next(update,None)
        text=update.message.reply_text.call_args.args[0]
        self.assertIn('завтра',text)
        self.assertIn('Фаджр',text)

    async def test_start_explains_new_version_without_forcing_widget(self):
        update=self.update('/start')
        with patch.object(bot,'load_users',return_value={}),patch.object(bot,'get_user'),patch.object(bot,'cmd_widget',new=AsyncMock()) as widget:
            await bot.cmd_start(update,None)
            widget.assert_not_awaited()
        text=update.message.reply_text.call_args.args[0]
        self.assertIn('новая версия Telegram',text)
        self.assertIn('/notifications',text)
        self.assertIn('Меню',text)

    async def test_notifications_stay_in_telegram_menu(self):
        application=SimpleNamespace(bot=SimpleNamespace(set_my_commands=AsyncMock()))
        await bot.post_init(application)
        commands=application.bot.set_my_commands.call_args.args[0]
        self.assertIn('notifications',[c.command for c in commands])
        self.assertIn('текстом',next(c.description for c in commands if c.command=='next'))

if __name__=='__main__':unittest.main()
