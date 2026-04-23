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
    try:
        with open('index.html', 'r') as f:
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
                await ws.send_json({'type': 'log', 'message': '✅ Подключаюсь...'})
                asyncio.create_task(nekto_spy(ws))
            elif data['action'] == 'disconnect':
                await ws.close()
    return ws

async def nekto_spy(ws):
    global ws1, ws2, token1, token2
    nekto_ws_url = "wss://nekto.me/socket.io/?EIO=4&transport=websocket"
    
    try:
        # Простое подключение
        ws1 = await websockets.connect(nekto_ws_url, timeout=30)
        await ws.send_json({'type': 'log', 'message': '✅ Client 1 connected'})
        await ws1.send("40")
        await asyncio.sleep(0.3)
        await ws1.send(f'42["auth",{{"token":"{token1}"}}]')
        
        ws2 = await websockets.connect(nekto_ws_url, timeout=30)
        await ws.send_json({'type': 'log', 'message': '✅ Client 2 connected'})
        await ws2.send("40")
        await asyncio.sleep(0.3)
        await ws2.send(f'42["auth",{{"token":"{token2}"}}]')
        
        await ws.send_json({'type': 'log', 'message': '🎯 BRIDGE ACTIVE!'})
        
        async def forward(ws_from, ws_to, name):
            async for msg in ws_from:
                await ws.send_json({'type': 'message', 'from': name, 'data': str(msg)[:200]})
                await ws_to.send(msg)
        
        await asyncio.gather(
            forward(ws1, ws2, '→ Client1'),
            forward(ws2, ws1, '→ Client2')
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await ws.send_json({'type': 'log', 'message': f'❌ Error: {str(e)}'})

app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/ws', bridge_handler)

cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True)})
cors.add(app.router.add_resource("/ws"))

if __name__ == '__main__':
    web.run_app(app, port=PORT)
