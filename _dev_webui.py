"""Persistent WebUI dev server for browser testing."""
import asyncio, sys, os, types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

astrbot_api = types.ModuleType('astrbot')
astrbot_api_mod = types.ModuleType('astrbot.api')
class MockLogger:
    def info(self, msg): print(f'[INFO] {msg}', flush=True)
    def warning(self, msg): print(f'[WARN] {msg}', flush=True)
    def error(self, msg): print(f'[ERROR] {msg}', flush=True)
    def debug(self, msg): pass
astrbot_api_mod.logger = MockLogger()
sys.modules['astrbot'] = astrbot_api
sys.modules['astrbot.api'] = astrbot_api_mod
astrbot_event = types.ModuleType('astrbot.api.event')
astrbot_event.AstrMessageEvent = type('AstrMessageEvent', (), {})
sys.modules['astrbot.api.event'] = astrbot_event

def load_module(name, filepath):
    source = open(filepath, encoding='utf-8').read()
    source = source.replace('from .dglab_client import', 'from dglab_client import')
    source = source.replace('from .dglab_connection_pool import', 'from dglab_connection_pool import')
    source = source.replace('from .dglab_device_store import', 'from dglab_device_store import')
    source = source.replace('from .dglab_commands import', 'from dglab_commands import')
    source = source.replace('from .dglab_user_store import', 'from dglab_user_store import')
    source = source.replace('from .dglab_permission_store import', 'from dglab_permission_store import')
    code = compile(source, filepath, 'exec')
    mod = types.ModuleType(name)
    mod.__file__ = filepath
    sys.modules[name] = mod
    exec(code, mod.__dict__)
    return mod

base = os.path.dirname(os.path.abspath(__file__))
load_module('dglab_client', os.path.join(base, 'dglab_client.py'))
device_store_mod = load_module('dglab_device_store', os.path.join(base, 'dglab_device_store.py'))
connection_pool_mod = load_module('dglab_connection_pool', os.path.join(base, 'dglab_connection_pool.py'))
load_module('dglab_commands', os.path.join(base, 'dglab_commands.py'))
user_store_mod = load_module('dglab_user_store', os.path.join(base, 'dglab_user_store.py'))
permission_store_mod = load_module('dglab_permission_store', os.path.join(base, 'dglab_permission_store.py'))
webui_mod = load_module('dglab_webui', os.path.join(base, 'dglab_webui.py'))

async def main():
    os.makedirs('data', exist_ok=True)
    store = device_store_mod.DeviceStore(data_dir='data')
    pool = connection_pool_mod.DeviceConnectionPool(device_store=store)
    user_store = user_store_mod.UserStore(data_dir='data')
    perm_store = permission_store_mod.PermissionStore(data_dir='data')
    await pool.start()
    webui = webui_mod.DGLabWebUI(
        connection_pool=pool, device_store=store,
        user_store=user_store, permission_store=perm_store,
        host='0.0.0.0', port=9178
    )
    await webui.start()
    print('=== WebUI running at http://0.0.0.0:9178 ===', flush=True)
    print('Press Ctrl+C to stop', flush=True)
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await webui.stop()
        await pool.stop()

if __name__ == '__main__':
    asyncio.run(main())
