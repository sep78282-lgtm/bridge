import asyncio
import socketio
from aiohttp import web, ClientSession
import aiohttp_cors
import json
import os
import ssl
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

PORT = int(os.environ.get('PORT', 8080))

sio1 = None
sio2 = None
token1 = ""
token2 = ""
websocket_clients = []

# Простой SSL контекст (без certifi)
ssl_context = ssl.create_default_context()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
    'Origin': 'https://nekto.me',
    'Referer': 'https://nekto.me/chat'
}

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    websocket_clients.append(ws)
    logger.info("Client connected")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get('action') == 'connect':
                    global token1, token2
                    token1 = data.get('token1', '')
                    token2 = data.get('token2', '')
                    await ws.send_json({'type': 'log', 'message': '✅ Tokens received'})
                    asyncio.create_task(run_bridge(ws))
                elif data.get('action') == 'disconnect':
                    await stop_bridge()
                    await ws.send_json({'type': 'log', 'message': '⏹️ Bridge stopped'})
    finally:
        if ws in websocket_clients:
            websocket_clients.remove(ws)
    return ws

async def stop_bridge():
    global sio1, sio2
    if sio1:
        await sio1.disconnect()
    if sio2:
        await sio2.disconnect()
    sio1 = sio2 = None

async def run_bridge(ws):
    global sio1, sio2, token1, token2
    sio1 = socketio.AsyncClient(logger=False, engineio_logger=False)
    sio2 = socketio.AsyncClient(logger=False, engineio_logger=False)
    
    @sio1.on('message')
    async def on_message1(data):
        await ws.send_json({'type': 'message', 'from': 'Client1', 'data': str(data)[:200]})
        if sio2 and sio2.connected:
            await sio2.emit('message', data)
    
    @sio2.on('message')
    async def on_message2(data):
        await ws.send_json({'type': 'message', 'from': 'Client2', 'data': str(data)[:200]})
        if sio1 and sio1.connected:
            await sio1.emit('message', data)
    
    @sio1.on('connect')
    async def on_connect1():
        await ws.send_json({'type': 'log', 'message': '✅ Client 1 connected'})
        await sio1.emit('auth', {'token': token1})
    
    @sio2.on('connect')
    async def on_connect2():
        await ws.send_json({'type': 'log', 'message': '✅ Client 2 connected'})
        await sio2.emit('auth', {'token': token2})
    
    try:
        await asyncio.gather(
            sio1.connect('https://nekto.me', transports=['websocket'], headers=HEADERS),
            sio2.connect('https://nekto.me', transports=['websocket'], headers=HEADERS)
        )
        await ws.send_json({'type': 'log', 'message': '🎯 BRIDGE ACTIVE!'})
        await asyncio.Event().wait()
    except Exception as e:
        await ws.send_json({'type': 'log', 'message': f'❌ Error: {str(e)}'})

async def health_check(request):
    return web.json_response({'status': 'ok', 'timestamp': datetime.now().isoformat()})

async def index(request):
    html_path = os.path.join(os.path.dirname(__file__), 'index.html')
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="<h1>Nekto Bridge</h1><p>index.html not found</p>", content_type='text/html')

app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/ws', websocket_handler)
app.router.add_get('/health', health_check)

cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*")})
cors.add(app.router.add_resource("/ws"))

if __name__ == '__main__':
    logger.info(f"Server running on port {PORT}")
    web.run_app(app, port=PORT)
