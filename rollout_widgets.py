"""One-time delivery of the approved widget; already-delivered versions are skipped."""
import argparse
import asyncio
import json
import logging

from bot import (TOKEN, ADMIN_ID, MAIN_KEYBOARD, init_db, load_users,
                 load_last_bot_messages, save_last_bot_messages,
                 load_user_widget, save_user_widget, get_db_connection)
from clean_chat_bot import CleanChatBot
from latest_messages import LatestMessages
from widget_delivery import WidgetSender, WidgetError

logging.getLogger('httpx').setLevel(logging.WARNING)


def load_widget_versions():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id, version FROM user_widgets")
            return dict(cur.fetchall())


async def rollout(send=False, admin_test=False):
    init_db()
    users = [int(uid) for uid in load_users() if int(uid) > 0]
    if admin_test:
        users = [ADMIN_ID]
    sender = WidgetSender(TOKEN, load_user_widget, save_user_widget, get_db_connection)
    versions = load_widget_versions()
    pending = [uid for uid in users if versions.get(uid) != sender.version]
    summary = dict(total=len(users), pending=len(pending), skipped=len(users)-len(pending),
                   delivered=0, blocked=0, failed=0)
    if not send:
        print(json.dumps(summary), flush=True)
        return summary
    manager = LatestMessages(load_last_bot_messages, save_last_bot_messages)
    async with CleanChatBot(TOKEN, manager, sender) as bot:
        me = await bot.get_me()
        if me.username != 'namaznv_bot':
            raise RuntimeError('Unexpected bot; nothing sent')
        semaphore = asyncio.Semaphore(4)
        completed = 0
        async def deliver(uid):
            nonlocal completed
            async with semaphore:
                await deliver_one(uid)
                completed += 1
                if completed % 10 == 0 or completed == len(pending):
                    print(json.dumps(dict(progress=completed, pending=len(pending), **{
                        key:summary[key] for key in ('delivered','blocked','failed')})), flush=True)
                await asyncio.sleep(.2)
        async def deliver_one(uid):
            for attempt in range(3):
                try:
                    await bot.send_widget(uid, MAIN_KEYBOARD)
                    summary['delivered'] += 1
                    break
                except WidgetError as error:
                    if error.code == 429 and error.retry_after and attempt < 2:
                        await asyncio.sleep(min(error.retry_after + 1, 60))
                        continue
                    summary['blocked' if error.code == 403 else 'failed'] += 1
                    print(json.dumps({'delivery_error': error.code}), flush=True)
                    break
                except Exception as error:
                    summary['failed'] += 1
                    print(json.dumps({'delivery_error': type(error).__name__}), flush=True)
                    break
        await asyncio.gather(*(deliver(uid) for uid in pending))
    print(json.dumps(summary), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--admin-test', action='store_true')
    args = parser.parse_args()
    asyncio.run(rollout(args.send, args.admin_test))
