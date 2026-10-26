"""Actual pinned Telegram SDK lifecycle/dispatch with an in-memory HTTP transport."""
import asyncio,json
from telegram import Update
from telegram.ext import Application,MessageHandler,filters
from telegram.request import BaseRequest

class OfflineRequest(BaseRequest):
    def __init__(self):self.calls=[]
    @property
    def read_timeout(self):return 5
    async def initialize(self):pass
    async def shutdown(self):pass
    async def do_request(self,url,method,request_data=None,**kwargs):
        self.calls.append(url.rsplit('/',1)[-1])
        assert url.endswith('/getMe'),'unexpected Telegram method; no outbound transport implemented'
        return 200,json.dumps({'ok':True,'result':{'id':1234,'is_bot':True,'first_name':'offline','username':'offline_fixture_bot'}}).encode()

def test_actual_sdk_initialise_dispatch_shutdown_without_polling():
    async def run():
        normal,poll=OfflineRequest(),OfflineRequest();received=[]
        app=Application.builder().token('1234:synthetic-fixture-only').request(normal).get_updates_request(poll).build()
        async def on_message(update,context):received.append((update.effective_chat.id,update.effective_user.id,update.message.text))
        app.add_handler(MessageHandler(filters.TEXT,on_message))
        await app.initialize()
        try:
            update=Update.de_json({'update_id':1,'message':{'message_id':1,'date':1700000000,'chat':{'id':9876,'type':'private'},'from':{'id':7654,'is_bot':False,'first_name':'fixture'},'text':'offline routing marker'}},app.bot)
            await app.process_update(update)
            assert received==[(9876,7654,'offline routing marker')]
            assert normal.calls==['getMe'] and poll.calls==[]
        finally:await app.shutdown()
    asyncio.run(run())
