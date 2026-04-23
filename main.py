import asyncio
import aiohttp
from aiohttp import web, ClientWebSocketResponse, WSMsgType
import aiohttp_cors
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get('PORT', 8080))
clients = []
ws1 = None
ws2 = None
token1 = ""
token2 = ""

async def index(request):
    try:
        with open('index.html', 'r') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except:
        return web.Response(text="<h1>Nekto Bridge</h1><script>alert('index.html not found')</script>", content_type='text/html')

async def ws_bridge(request):
    client_ws = web.WebSocketResponse()
    await client_ws.prepare(request)
    clients.append(client_ws)
    logger.info("Client connected")
    
    async for msg in client_ws:
        if msg.type == WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data['action'] == 'connect':
                global token1, token2
                token1 = data['token1']
                token2 = data['token2']
                await client_ws.send_json({'type': 'log', 'message': '✅ Connecting...'})
                asyncio.create_task(run_bridge(client_ws))
            elif data['action'] == 'disconnect':
                await client_ws.close()
    return client_ws

async def run_bridge(client_ws):
    global ws1, ws2, token1, token2
    
    session = aiohttp.ClientSession()
    nekto_url = "wss://nekto.me/socket.io/?EIO=4&transport=websocket"
    
    try:
        # Клиент 1
        ws1 = await session.ws_connect(nekto_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        await client_ws.send_json({'type': 'log', 'message': '✅ Client 1 connected'})
        await ws1.send_str("40")
        await asyncio.sleep(0.3)
        await ws1.send_str(f'42["auth",{{"token":"{token1}"}}]')
        
        # Клиент 2
        ws2 = await session.ws_connect(nekto_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        await client_ws.send_json({'type': 'log', 'message': '✅ Client 2 connected'})
        await ws2.send_str("40")
        await asyncio.sleep(0.3)
        await ws2.send_str(f'42["auth",{{"token":"{token2}"}}]')
        
        await client_ws.send_json({'type': 'log', 'message': '🎯 BRIDGE ACTIVE!'})
        
        async def forward1():
            async for msg in ws1:
                if msg.type == WSMsgType.TEXT:
                    await client_ws.send_json({'type': 'message', 'from': 'Client1', 'data': msg.data[:200]})
                    await ws2.send_str(msg.data)
        
        async def forward2():
            async for msg in ws2:
                if msg.type == WSMsgType.TEXT:
                    await client_ws.send_json({'type': 'message', 'from': 'Client2', 'data': msg.data[:200]})
                    await ws1.send_str(msg.data)
        
        await asyncio.gather(forward1(), forward2())
        
    except Exception as e:
        logger.error(f"Bridge error: {e}")
        await client_ws.send_json({'type': 'log', 'message': f'❌ Error: {str(e)}'})
    finally:
        await session.close()

app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/bridge', ws_bridge)

cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*")})
cors.add(app.router.add_resource("/bridge"))

if __name__ == '__main__':
    logger.info(f"Server on http://localhost:{PORT}")
    web.run_app(app, port=PORT)
