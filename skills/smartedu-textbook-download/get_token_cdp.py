#!/usr/bin/env python3
"""Get access_token from Chrome localStorage via CDP.

Usage:
  1. Start Chrome with CDP enabled:
       "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
         --remote-debugging-port=9222
  2. Open basic.smartedu.cn and log in (SSO).
  3. Run this script. Token saved to /tmp/smartedu/token.json.
"""
import asyncio
import json
import os
import sys
import urllib.request
import websockets


def http_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=10).read())


async def main():
    version = http_json("http://127.0.0.1:9222/json/version")
    ws_url = version["webSocketDebuggerUrl"]
    targets = http_json("http://127.0.0.1:9222/json/list")

    target = next(
        (t for t in targets
         if t["type"] == "page"
         and "basic.smartedu.cn" in t.get("url", "")
         and "devtools://" not in t.get("url", "")),
        None,
    )
    if not target:
        print("❌ No smartedu tab found. Open basic.smartedu.cn in Chrome first.",
              file=sys.stderr)
        sys.exit(1)
    print(f"Target: {target['id']}  url={target['url'][:80]}")

    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
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
            while mid not in responses:
                ev.clear()
                await ev.wait()
            return responses[mid]

        attach = await call(1, "Target.attachToTarget",
                            {"targetId": target["id"], "flatten": True})
        session = attach["result"]["sessionId"]

        result = await call(
            2, "Runtime.evaluate",
            {"expression": (
                "(() => {"
                "  const k = Object.keys(localStorage)"
                "    .find(x => x.startsWith('ND_UC_AUTH'));"
                "  if (!k) return JSON.stringify({found: false});"
                "  const td = JSON.parse(localStorage.getItem(k));"
                "  const inner = JSON.parse(td.value);"
                "  return JSON.stringify({"
                "    found: true,"
                "    key: k,"
                "    access_token: inner.access_token,"
                "    expires_in: inner.expires_in,"
                "    expires_at: inner.expires_at,"
                "    token_type: inner.token_type"
                "  });"
                "})()"
            ), "returnByValue": True},
            session_id=session,
        )
        rv_str = result.get("result", {}).get("result", {}).get("value", "{}")
        rv = json.loads(rv_str)

        pump_task.cancel()

        if not rv.get("found"):
            print(f"❌ Token not found. localStorage keys: {rv.get('keys')}",
                  file=sys.stderr)
            sys.exit(1)

        out_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "token.json",
        )
        out_path = os.path.normpath(out_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({
                "access_token": rv["access_token"],
                "expires_at": rv.get("expires_at"),
                "token_type": rv.get("token_type"),
                "key": rv["key"],
            }, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Saved token to: {out_path}")
        print(f"  expires_at: {rv.get('expires_at')}")
        print(f"  token: {rv['access_token'][:8]}...{rv['access_token'][-4:]}"
              f"  (len={len(rv['access_token'])})")


if __name__ == "__main__":
    asyncio.run(main())