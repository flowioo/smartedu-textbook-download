#!/usr/bin/env python3
"""一键式下载: 复用或启动 Chrome → 等用户登录 → 抓 token → 下载所有课本

两种模式:
  - reuse: 复用本机已开的 Chrome (默认 9222 端口, 已登录)
  - spawn: 启动一个独立的临时 Chrome 实例 (干净的 user-data-dir,首次登录)

用法:
  python3 download_all.py                     # 默认 reuse 模式
  python3 download_all.py --spawn             # 启动临时 Chrome
  python3 download_all.py --port 9223         # 指定 CDP 端口
"""
import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
]
LOGIN_URL = "https://auth.smartedu.cn/uias/login"
AUTHED_URL = "https://basic.smartedu.cn/"


def find_chrome():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Chrome not found. Set --chrome-path")


def cdp_alive(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, ConnectionRefusedError, socket.timeout):
        return None


def wait_for_cdp(port, timeout=30):
    """Poll CDP until Chrome is ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cdp_alive(port):
            return True
        time.sleep(0.5)
    return False


def http_json(url, port=9222):
    return json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}{url}", timeout=10).read())


def spawn_chrome(port, chrome_path, profile_dir):
    """Launch a fresh Chrome instance with CDP enabled."""
    os.makedirs(profile_dir, exist_ok=True)
    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        AUTHED_URL,
    ]
    print(f"🚀 启动 Chrome: {chrome_path}")
    print(f"   端口: {port}")
    print(f"   profile: {profile_dir}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        preexec_fn=os.setsid,  # new process group for clean kill
    )
    print(f"   PID: {proc.pid}")
    return proc


def wait_for_login(port, timeout=600):
    """Poll until ND_UC_AUTH appears in any tab's localStorage.

    Opens login URL in a new tab so user can authenticate.
    """
    import asyncio
    import websockets

    print(f"\n🔐 等待用户在 Chrome 里登录 basic.smartedu.cn ...")
    print(f"   Chrome CDP: http://127.0.0.1:{port}")
    print(f"   登录地址:   {LOGIN_URL}")
    print(f"   超时:       {timeout}s ({timeout//60}min)")
    print()

    # Ensure there's a tab on the login page
    try:
        new_tab = http_json("/json/new?about:blank", port=port)
        # navigate the about:blank tab to login
        target_id = new_tab["id"]
    except Exception:
        target_id = None

    async def wait_loop():
        ws_url = http_json("/json/version", port=port)["webSocketDebuggerUrl"]
        async with websockets.connect(ws_url, max_size=8 * 1024 * 1024) as ws:
            responses = {}
            ev = asyncio.Event()

            async def pump():
                async for raw in ws:
                    msg = json.loads(raw)
                    if "id" in msg:
                        responses[msg["id"]] = msg
                        ev.set()

            pump_task = asyncio.create_task(pump())

            async def call(mid, method, params=None, session_id=None):
                payload = {"id": mid, "method": method, "params": params or {}}
                if session_id:
                    payload["sessionId"] = session_id
                await ws.send(json.dumps(payload))
                deadline = time.time() + 5
                while mid not in responses:
                    ev.clear()
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        raise TimeoutError()
                    await asyncio.wait_for(ev.wait(), timeout=remaining)
                return responses[mid]

            # Find or open smartedu tab
            targets = http_json("/json/list", port=port)
            smart_tab = next(
                (t for t in targets
                 if t["type"] == "page"
                 and ("basic.smartedu.cn" in t.get("url", "")
                      or "auth.smartedu.cn" in t.get("url", ""))
                 and "devtools://" not in t.get("url", "")),
                None,
            )
            if not smart_tab:
                # Open login in new tab
                new_tab = http_json("/json/new?" + LOGIN_URL, port=port)
                smart_tab = new_tab

            print(f"   监控 tab: {smart_tab['id']}")
            print(f"   当前 URL: {smart_tab['url']}")

            attach = await call(
                1, "Target.attachToTarget",
                {"targetId": smart_tab["id"], "flatten": True})
            session = attach["result"]["sessionId"]

            deadline = time.time() + timeout
            attempt = 0
            while time.time() < deadline:
                attempt += 1
                try:
                    r = await call(
                        1000 + attempt, "Runtime.evaluate",
                        {"expression": (
                            "(() => {"
                            "  const k = Object.keys(localStorage)"
                            "    .find(x => x.startsWith('ND_UC_AUTH'));"
                            "  if (!k) return JSON.stringify({found: false});"
                            "  const td = JSON.parse(localStorage.getItem(k));"
                            "  const inner = JSON.parse(td.value);"
                            "  return JSON.stringify({"
                            "    found: true, key: k,"
                            "    access_token: inner.access_token,"
                            "    expires_at: inner.expires_at,"
                            "    token_type: inner.token_type"
                            "  });"
                            "})()"
                        ), "returnByValue": True},
                        session_id=session)
                    rv = json.loads(r["result"]["result"]["value"])
                    if rv.get("found"):
                        return rv
                except Exception as e:
                    print(f"   [{attempt}] CDP poll error: {e}", file=sys.stderr)

                if attempt % 4 == 0:
                    print(f"   [{attempt}] 仍在等待登录... "
                          f"({int(deadline - time.time())}s left)")
                await asyncio.sleep(2)

            pump_task.cancel()
            return None

    return asyncio.run(wait_loop())


def save_token(token_data, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(token_data, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Token 保存到: {out_path}")
    print(f"  expires_at: {token_data.get('expires_at')}")
    t = token_data["access_token"]
    print(f"  token: {t[:8]}...{t[-4:]} (len={len(t)})")


def build_targets_if_missing(targets_path):
    if os.path.exists(targets_path):
        return
    print(f"\n📋 生成下载清单 (首次运行)...")
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import build_targets
    # 优先用本地 cache (./cache/), 离线 / 网络差也能跑
    cache_dir = os.path.join(here, "cache")
    if not os.path.isdir(cache_dir):
        cache_dir = None
    build_targets.build_targets(
        build_targets.DEFAULT_TARGETS, targets_path, cache_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spawn", action="store_true",
                        help="启动独立 Chrome (默认复用 9222)")
    parser.add_argument("--port", type=int, default=9222,
                        help="CDP 端口 (默认 9222)")
    parser.add_argument("--chrome-path", default=None,
                        help="Chrome 可执行路径")
    parser.add_argument("--profile-dir", default=None,
                        help="Chrome user-data-dir (spawn 模式)")
    parser.add_argument("--timeout", type=int, default=600,
                        help="登录等待超时 (秒)")
    parser.add_argument("--skip-download", action="store_true",
                        help="只抓 token, 不下载")
    parser.add_argument("--keep-chrome", action="store_true",
                        help="spawn 模式下保留 Chrome 不退出")
    args = parser.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    # token / targets 写到脚本同级目录,这样 git clone 后直接能用
    base_dir = here
    token_path = os.environ.get(
        "SMARTEDU_TOKEN_FILE",
        os.path.join(base_dir, "token.json"))
    targets_path = os.environ.get(
        "SMARTEDU_TARGETS_FILE",
        os.path.join(base_dir, "targets.json"))

    chrome_proc = None
    spawned_by_us = False

    # 1. 确保 Chrome + CDP 可用
    if not cdp_alive(args.port):
        if not args.spawn:
            print(f"❌ 端口 {args.port} 上没有 Chrome 在跑, 也未指定 --spawn")
            print(f"   启动方式二选一:")
            print(f"     1) 复用你已有的 Chrome: 重新打开时加 --remote-debugging-port={args.port}")
            print(f"     2) 自动启动: python3 {sys.argv[0]} --spawn")
            sys.exit(1)
        chrome_path = args.chrome_path or find_chrome()
        profile = args.profile_dir or f"/tmp/smartedu-chrome-{int(time.time())}"
        chrome_proc = spawn_chrome(args.port, chrome_path, profile)
        spawned_by_us = True
        if not wait_for_cdp(args.port, timeout=30):
            print("❌ Chrome 启动了但 CDP 端口未就绪")
            sys.exit(1)
    else:
        print(f"✓ 端口 {args.port} 上 Chrome 已在跑")

    # 2. 等登录 + 抓 token
    try:
        token_data = wait_for_login(args.port, timeout=args.timeout)
    finally:
        if chrome_proc and not args.keep_chrome and spawned_by_us:
            print("\n🛑 关闭临时 Chrome...")
            try:
                os.killpg(os.getpgid(chrome_proc.pid), signal.SIGTERM)
                chrome_proc.wait(timeout=5)
            except Exception:
                pass

    if not token_data:
        print("\n❌ 等待登录超时, 没拿到 token")
        sys.exit(2)

    save_token(token_data, token_path)

    if args.skip_download:
        return

    # 3. 生成下载清单
    build_targets_if_missing(targets_path)

    # 4. 下载
    print(f"\n🚀 开始下载...")
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import download_batch
    download_batch.main()

    # 5. 重命名为官方标题
    print(f"\n📝 重命名为官方书名...")
    import rename_to_official_titles
    rename_to_official_titles.rename(
        targets_path,
        os.environ.get("SMARTEDU_OUTPUT_DIR",
                       os.path.expanduser("~/Downloads/textbooks")))


if __name__ == "__main__":
    main()