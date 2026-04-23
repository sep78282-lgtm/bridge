import asyncio
import aiohttp
from aiohttp import web, WSMsgType
import aiohttp_cors
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get('PORT', 8080))

async def index(request):
    with open('index.html', 'r') as f:
        return web.Response(text=f.read(), content_type='text/html')

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info("Client connected")
    
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data['action'] == 'connect':
                asyncio.create_task(bridge_nekto(ws, data['token1'], data['token2']))
    
    return ws

async def bridge_nekto(client_ws, token1, token2):
    session = aiohttp.ClientSession()
    
    # Пробуем разные варианты
    urls_to_try = [
        "wss://nekto.me/socket.io/?EIO=3&transport=websocket",
        "wss://nekto.me/socket.io/?EIO=4&transport=websocket",
        "wss://nekto.me/ws",
        "wss://nekto.me/"
    ]
    
    for url in urls_to_try:
        try:
            await client_ws.send_json({'type': 'log', 'message': f'Пробую {url}'})
            ws1 = await session.ws_connect(url, timeout=5)
            await ws1.close()
            await client_ws.send_json({'type': 'log', 'message': f'✅ Работает: {url}'})
            nekto_url = url
            break
        except:
            continue
    else:
        await client_ws.send_json({'type': 'log', 'message': '❌ Не удалось подключиться к nekto.me'})
        return
    
    try:
        # Подключаемся
        ws1 = await session.ws_connect(nekto_url)
        ws2 = await session.ws_connect(nekto_url)
        
        await client_ws.send_json({'type': 'log', 'message': '✅ Подключено к nekto.me'})
        
        # Отправляем приветствие
        await ws1.send_str("40")
        await ws2.send_str("40")
        await asyncio.sleep(0.5)
        
        # Аутентификация
        await ws1.send_str(f'42["auth",{{"token":"{token1}"}}]')
        await ws2.send_str(f'42["auth",{{"token":"{token2}"}}]')
        
        await client_ws.send_json({'type': 'log', 'message': '🎯 МОСТ АКТИВЕН!'})
        
        async def forward(a, b, name):
            async for msg in a:
                if msg.type == WSMsgType.TEXT:
                    await client_ws.send_json({'type': 'message', 'from': name, 'data': msg.data[:200]})
                    await b.send_str(msg.data)
        
        await asyncio.gather(
            forward(ws1, ws2, "Client1 →"),
            forward(ws2, ws1, "Client2 →")
        )
        
    except Exception as e:
        await client_ws.send_json({'type': 'log', 'message': f'❌ Ошибка: {str(e)}'})
    finally:
        await session.close()

app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/ws', websocket_handler)

cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True)})
cors.add(app.router.add_resource("/ws"))

if __name__ == '__main__':
    web.run_app(app, port=PORT)
