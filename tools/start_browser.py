# -*- coding: utf-8 -*-
"""启动无头 Edge（CDP 调试端口 9222）供 UI 巡检脚本使用。

浏览器 profile 放在系统临时目录，不写入项目目录——profile 体积可达数百 MB，
留在项目里会污染交付物。已被 UI 巡检脚本自动调用，也可单独运行。
"""
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 9222
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
PROFILE = os.path.join(tempfile.gettempdir(), 'wm_edge_profile')


def cdp_alive(timeout=3):
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=timeout)
        return True
    except Exception:
        return False


def start(wait_seconds=25):
    """确保 CDP 可用：已在运行直接返回 True，否则启动无头 Edge 并等待就绪。"""
    if cdp_alive():
        return True
    if not os.path.isfile(EDGE):
        print(f'未找到 Edge：{EDGE}')
        return False
    os.makedirs(PROFILE, exist_ok=True)
    subprocess.Popen([EDGE, '--headless=new', '--disable-gpu',
                      f'--remote-debugging-port={PORT}',
                      f'--remote-allow-origins=http://127.0.0.1:{PORT}',
                      '--window-size=1280,900', f'--user-data-dir={PROFILE}', 'about:blank'],
                     creationflags=0x00000008 | 0x00000200,   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(wait_seconds * 2):
        if cdp_alive():
            print(f'无头 Edge 已就绪（profile: {PROFILE}）')
            return True
        time.sleep(0.5)
    return False


if __name__ == '__main__':
    ok = start()
    print('CDP 就绪' if ok else '启动失败')
    sys.exit(0 if ok else 1)
