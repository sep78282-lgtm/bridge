import asyncio
import websockets
import json
import os
from aiohttp import web
import aiohttp_cors
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get('PORT', 8080))
websocket_clients = []
ws1 = None
ws2 = None
token1 = ""
token2 = ""

async def index(request):
    html_path = os.path.join(os.path.dirname(__file__), 'index.html')
    try:
        with open(html_path, 'r') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except:
        return web.Response(text="<h1>Nekto Bridge</h1>", content_type='text/html')

async def bridge_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    websocket_clients.append(ws)
    logger.info("Client connected")
    
    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data['action'] == 'connect':
                global token1, token2
                token1 = data['token1']
                token2 = data['token2']
                await ws.send_json({'type': 'log', 'message': '✅ Подключаюсь к nekto.me...'})
                asyncio.create_task(nekto_spy(ws))
            elif data['action'] == 'disconnect':
                await ws.send_json({'type': 'log', 'message': '⏹️ Остановлено'})
    return ws

async def nekto_spy(ws):
    global ws1, ws2, token1, token2
    
    # Подключаемся к WebSocket серверу nekto.me напрямую
    nekto_ws_url = "wss://nekto.me/socket.io/?EIO=4&transport=websocket"
    
    try:
        # Клиент 1
        ws1 = await websockets.connect(
            nekto_ws_url,
            extra_headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Origin': 'https://nekto.me',
                'Referer': 'https://nekto.me/chat'
            },
            ping_interval=20,
            ping_timeout=60
        )
        await ws.send_json({'type': 'log', 'message': '✅ Клиент #1 подключен'})
        
        # Отправляем приветствие Socket.IO
        await ws1.send("40")
        await asyncio.sleep(0.5)
        # Аутентификация
        await ws1.send(f'42["auth",{{"token":"{token1}"}}]')
        
        # Клиент 2
        ws2 = await websockets.connect(
            nekto_ws_url,
            extra_headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Origin': 'https://nekto.me',
                'Referer': 'https://nekto.me/chat'
            },
            ping_interval=20,
            ping_timeout=60
        )
        await ws.send_json({'type': 'log', 'message': '✅ Клиент #2 подключен'})
        await ws2.send("40")
        await asyncio.sleep(0.5)
        await ws2.send(f'42["auth",{{"token":"{token2}"}}]')
        
        await ws.send_json({'type': 'log', 'message': '🎯 МОСТ АКТИВЕН! Жду сообщения...'})
        
        # Запускаем релей
        async def forward1to2():
            async for msg in ws1:
                await ws.send_json({'type': 'message', 'from': '→ Клиент1', 'data': str(msg)[:200]})
                if ws2.open:
                    await ws2.send(msg)
        
        async def forward2to1():
            async for msg in ws2:
                await ws.send_json({'type': 'message', 'from': '→ Клиент2', 'data': str(msg)[:200]})
                if ws1.open:
                    await ws1.send(msg)
        
        await asyncio.gather(forward1to2(), forward2to1())
        
    except Exception as e:
        logger.error(f"Connection error: {e}")
        await ws.send_json({'type': 'log', 'message': f'❌ Ошибка: {str(e)}'})

app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/ws', bridge_handler)

cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*")})
cors.add(app.router.add_resource("/ws"))

if __name__ == '__main__':
    web.run_app(app, port=PORT)
