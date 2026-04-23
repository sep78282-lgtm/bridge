import asyncio
import socketio
from aiohttp import web
import aiohttp_cors
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get('PORT', 8080))
sio1 = None
sio2 = None
token1 = ""
token2 = ""
websocket_clients = []

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    websocket_clients.append(ws)
    logger.info("Клиент подключен")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data['action'] == 'connect':
                    global token1, token2
                    token1 = data['token1']
                    token2 = data['token2']
                    await ws.send_json({'type': 'log', 'message': '✅ Токены получены'})
                    asyncio.create_task(run_bridge(ws))
                elif data['action'] == 'disconnect':
                    if sio1:
                        await sio1.disconnect()
                    if sio2:
                        await sio2.disconnect()
                    await ws.send_json({'type': 'log', 'message': '⏹️ Мост остановлен'})
    finally:
        websocket_clients.remove(ws)
    return ws

async def run_bridge(ws):
    global sio1, sio2, token1, token2
    sio1 = socketio.AsyncClient(logger=False, engineio_logger=False)
    sio2 = socketio.AsyncClient(logger=False, engineio_logger=False)
    msg_count = 0
    
    @sio1.on('message')
    async def on_message1(data):
        nonlocal msg_count
        msg_count += 1
        await ws.send_json({'type': 'message', 'from': 'Client1', 'data': str(data)[:200]})
        if sio2 and sio2.connected:
            await sio2.emit('message', data)
    
    @sio2.on('message')
    async def on_message2(data):
        nonlocal msg_count
        msg_count += 1
        await ws.send_json({'type': 'message', 'from': 'Client2', 'data': str(data)[:200]})
        if sio1 and sio1.connected:
            await sio1.emit('message', data)
    
    @sio1.on('connect')
    async def on_connect1():
        await ws.send_json({'type': 'log', 'message': '✅ Клиент #1 подключен'})
        await sio1.emit('auth', {'token': token1})
    
    @sio2.on('connect')
    async def on_connect2():
        await ws.send_json({'type': 'log', 'message': '✅ Клиент #2 подключен'})
        await sio2.emit('auth', {'token': token2})
    
    try:
        await asyncio.gather(
            sio1.connect('https://nekto.me', transports=['websocket']),
            sio2.connect('https://nekto.me', transports=['websocket'])
        )
        await ws.send_json({'type': 'log', 'message': '🎯 МОСТ АКТИВЕН!'})
        await asyncio.Event().wait()
    except Exception as e:
        await ws.send_json({'type': 'log', 'message': f'❌ Ошибка: {e}'})

async def health_check(request):
    return web.Response(text='OK')

async def index(request):
    with open('index.html', 'r') as f:
        return web.Response(text=f.read(), content_type='text/html')

app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/ws', websocket_handler)
app.router.add_get('/health', health_check)

cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
        allow_methods="*"
    )
})
cors.add(app.router.add_resource("/ws"))

if __name__ == '__main__':
    web.run_app(app, port=PORT)
