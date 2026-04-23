import asyncio
import socketio
from aiohttp import web, ClientSession, TCPConnector
import aiohttp_cors
import json
import os
import ssl
import certifi
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

PORT = int(os.environ.get('PORT', 8080))

# Глоб3альные переменные
sio1 = None
sio2 = None
token1 = ""
token2 = ""
websocket_clients = []

# Создаем SSL контекст с сертификатами
ssl_context = ssl.create_default_context(cafile=certifi.where())

# Кастомные заголовки чтобы не банили
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    'Origin': 'https://nekto.me',
    'Referer': 'https://nekto.me/chat'
}

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    websocket_clients.append(ws)
    logger.info("Клиент подключен к WebSocket")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    if data.get('action') == 'connect':
                        global token1, token2
                        token1 = data.get('token1', '')
                        token2 = data.get('token2', '')
                        
                        if not token1 or not token2:
                            await ws.send_json({'type': 'log', 'message': '❌ Токены не могут быть пустыми', 'error': True})
                            continue
                        
                        await ws.send_json({'type': 'log', 'message': '✅ Токены получены, подключаюсь к nekto.me...'})
                        asyncio.create_task(run_bridge(ws))
                        
                    elif data.get('action') == 'disconnect':
                        await stop_bridge()
                        await ws.send_json({'type': 'log', 'message': '⏹️ Мост остановлен'})
                        
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    await ws.send_json({'type': 'log', 'message': f'❌ Ошибка парсинга JSON: {e}', 'error': True})
                    
    except Exception as e:
        logger.error(f"WebSocket handler error: {e}")
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
    sio1 = None
    sio2 = None

async def run_bridge(ws):
    global sio1, sio2, token1, token2
    
    sio1 = socketio.AsyncClient(logger=False, engineio_logger=False)
    sio2 = socketio.AsyncClient(logger=False, engineio_logger=False)
    
    msg_count = 0
    reconnect_attempts = 0
    
    @sio1.on('message')
    async def on_message1(data):
        nonlocal msg_count
        msg_count += 1
        logger.info(f"📨 Client1→Client2: {str(data)[:100]}")
        await ws.send_json({'type': 'message', 'from': 'Client1', 'data': str(data)[:500]})
        if sio2 and sio2.connected:
            await sio2.emit('message', data)
    
    @sio2.on('message')
    async def on_message2(data):
        nonlocal msg_count
        msg_count += 1
        logger.info(f"📨 Client2→Client1: {str(data)[:100]}")
        await ws.send_json({'type': 'message', 'from': 'Client2', 'data': str(data)[:500]})
        if sio1 and sio1.connected:
            await sio1.emit('message', data)
    
    @sio1.on('connect')
    async def on_connect1():
        nonlocal reconnect_attempts
        reconnect_attempts = 0
        logger.info("✅ Клиент #1 подключен к nekto.me")
        await ws.send_json({'type': 'log', 'message': '✅ Клиент #1 подключен к nekto.me'})
        await sio1.emit('auth', {'token': token1})
    
    @sio2.on('connect')
    async def on_connect2():
        nonlocal reconnect_attempts
        reconnect_attempts = 0
        logger.info("✅ Клиент #2 подключен к nekto.me")
        await ws.send_json({'type': 'log', 'message': '✅ Клиент #2 подключен к nekto.me'})
        await sio2.emit('auth', {'token': token2})
    
    @sio1.on('disconnect')
    async def on_disconnect1():
        logger.warning("⚠️ Клиент #1 отключен")
        await ws.send_json({'type': 'log', 'message': '⚠️ Клиент #1 отключен, попытка переподключения...'})
    
    @sio2.on('disconnect')
    async def on_disconnect2():
        logger.warning("⚠️ Клиент #2 отключен")
        await ws.send_json({'type': 'log', 'message': '⚠️ Клиент #2 отключен, попытка переподключения...'})
    
    @sio1.on('error')
    async def on_error1(e):
        logger.error(f"❌ Клиент #1 ошибка: {e}")
        await ws.send_json({'type': 'log', 'message': f'❌ Клиент #1 ошибка: {str(e)}', 'error': True})
    
    @sio2.on('error')
    async def on_error2(e):
        logger.error(f"❌ Клиент #2 ошибка: {e}")
        await ws.send_json({'type': 'log', 'message': f'❌ Клиент #2 ошибка: {str(e)}', 'error': True})
    
    try:
        # Создаем сессию с заголовками
        connector = TCPConnector(ssl=ssl_context)
        session = ClientSession(headers=HEADERS, connector=connector)
        
        # Подключаемся с таймаутом и реконнектом
        await asyncio.gather(
            sio1.connect('https://nekto.me', 
                        transports=['websocket'], 
                        socketio_path='/socket.io/',
                        wait_timeout=10,
                        headers=HEADERS),
            sio2.connect('https://nekto.me', 
                        transports=['websocket'],
                        socketio_path='/socket.io/', 
                        wait_timeout=10,
                        headers=HEADERS)
        )
        
        await ws.send_json({'type': 'log', 'message': '🎯 МОСТ АКТИВЕН! Перехват запущен', 'success': True})
        logger.info("Bridge active, waiting for messages...")
        
        # Держим соединение открытым
        while True:
            await asyncio.sleep(1)
            if not sio1.connected or not sio2.connected:
                logger.warning("Одно из соединений потеряно")
                await ws.send_json({'type': 'log', 'message': '⚠️ Соединение потеряно, переподключение...'})
                break
                
    except asyncio.TimeoutError:
        error_msg = "❌ Таймаут подключения к nekto.me"
        logger.error(error_msg)
        await ws.send_json({'type': 'log', 'message': error_msg, 'error': True})
        
    except Exception as e:
        error_msg = f"❌ Ошибка: {str(e)}"
        logger.error(error_msg)
        await ws.send_json({'type': 'log', 'message': error_msg, 'error': True})
        
    finally:
        await stop_bridge()

async def health_check(request):
    """Health check endpoint для UptimeRobot"""
    status = {
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'websocket_clients': len(websocket_clients)
    }
    return web.json_response(status)

async def index(request):
    """Отдает HTML интерфейс"""
    html_path = os.path.join(os.path.dirname(__file__), 'index.html')
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except FileNotFoundError:
        # HTML прямо в коде на случай отсутствия файла
        fallback_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Nekto Bridge</title><meta charset="UTF-8"></head>
        <body style="background:#000;color:#0f0;font-family:monospace;padding:20px;">
        <h1>🔗 Nekto Bridge</h1>
        <p>Сервер работает, но файл index.html не найден.</p>
        <p>Создайте файл index.html в корне проекта.</p>
        </body>
        </html>
        """
        return web.Response(text=fallback_html, content_type='text/html')

# Создаем приложение
app = web.Application()

# Добавляем роуты
app.router.add_get('/', index)
app.router.add_get('/ws', websocket_handler)
app.router.add_get('/health', health_check)

# Настройка CORS
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
    logger.info(f"🚀 Сервер запущен на порту {PORT}")
    logger.info(f"📡 WebSocket endpoint: ws://localhost:{PORT}/ws")
    logger.info(f"🌐 HTTP endpoint: http://localhost:{PORT}")
    web.run_app(app, port=PORT)
