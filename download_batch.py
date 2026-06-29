#!/usr/bin/env python3
"""
国家中小学智慧教育平台 电子课本 批量下载器

输入: /tmp/smartedu/targets.json (32 本书)
鉴权: /tmp/smartedu/token.json (从 Chrome localStorage 抓的 access_token)
输出: ~/Downloads/textbooks/{学科}/{年级}{册次}.pdf
"""
import json
import os
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------- 配置 ----------
# 默认从脚本同级目录的 token.json / targets.json 读取。
# 也支持通过环境变量覆盖。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.environ.get("SMARTEDU_TOKEN_FILE",
                            os.path.join(BASE_DIR, "token.json"))
TARGETS_FILE = os.environ.get("SMARTEDU_TARGETS_FILE",
                              os.path.join(BASE_DIR, "targets.json"))
OUTPUT_DIR = os.environ.get("SMARTEDU_OUTPUT_DIR",
                            os.path.expanduser("~/Downloads/textbooks"))
META_URL = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{content_id}.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
PARALLEL = int(os.environ.get("SMARTEDU_PARALLEL", "5"))  # 并发数


def load_token():
    if not os.path.exists(TOKEN_FILE):
        sys.exit(f"❌ Token 文件不存在: {TOKEN_FILE}\n"
                 "   先通过 CDP 从 Chrome localStorage 抓 token")
    with open(TOKEN_FILE) as f:
        data = json.load(f)
    token = data.get("access_token")
    if not token:
        sys.exit(f"❌ Token 文件格式不对")
    return token


def auth_headers(token):
    return {
        "X-ND-AUTH": f'MAC id="{token}",nonce="0",mac="0"',
        "Origin": "https://basic.smartedu.cn",
        "Referer": "https://basic.smartedu.cn/",
        "User-Agent": UA,
    }


def fetch_pdf_url(content_id, session, headers):
    """从 content_id 拿 PDF CDN URL"""
    url = META_URL.format(content_id=content_id)
    r = session.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    for item in data.get("ti_items", []):
        if item.get("ti_is_source_file"):
            storages = item.get("ti_storages") or []
            if storages:
                return storages[0]  # 用 r1-ndr-private 节点 (带 token)
            storage = item.get("ti_storage")
            if storage:
                return storage.replace("cs_path:${ref-path}",
                                        "https://r1-ndr-private.ykt.cbern.com.cn")
    raise RuntimeError(f"No PDF URL in metadata for {content_id}")


def safe_filename(s):
    """替换文件系统不安全字符"""
    return (s.replace("/", "_").replace(":", "_").replace(" ", "_")
             .replace("（", "(").replace("）", ")")
             .replace("·", "-"))


def download_one(target, token):
    """下载一本书, 返回 (subject, grade, sem, status, size, message)"""
    subject = target["subject"]
    grade = target["grade"]
    sem = target["semester"]
    cid = target["id"]

    subject_dir = os.path.join(OUTPUT_DIR, subject)
    os.makedirs(subject_dir, exist_ok=True)
    filename = f"{grade}_{sem}.pdf"
    out_path = os.path.join(subject_dir, filename)

    # 断点续传: 已存在且大小匹配则跳过
    if os.path.exists(out_path) and os.path.getsize(out_path) > 100000:
        return (subject, grade, sem, "skip", os.path.getsize(out_path), "exists")

    headers = auth_headers(token)
    sess = requests.Session()

    # 优先用 targets.json 里缓存的 pdf_url (避免 metadata API 调用)
    pdf_url = target.get("pdf_url")
    if not pdf_url:
        try:
            pdf_url = fetch_pdf_url(cid, sess, headers)
        except Exception as e:
            return (subject, grade, sem, "error", 0, f"metadata: {e}")

    try:
        with sess.get(pdf_url, headers=headers, stream=True, timeout=120) as r:
            if not r.ok:
                msg = ("token 可能过期" if r.status_code in (401, 403)
                       else f"HTTP {r.status_code}")
                return (subject, grade, sem, "error", 0, msg)

            total = int(r.headers.get("Content-Length", 0))
            tmp_path = out_path + ".tmp"
            written = 0
            # 按文件大小动态 chunk
            chunk = 524288 if total > 52428800 else 262144 if total > 20971520 else 131072

            with open(tmp_path, "wb") as f:
                for chunk_data in r.iter_content(chunk_size=chunk):
                    if chunk_data:
                        f.write(chunk_data)
                        written += len(chunk_data)

            os.replace(tmp_path, out_path)
            return (subject, grade, sem, "ok", written, "")
    except Exception as e:
        if os.path.exists(out_path + ".tmp"):
            os.remove(out_path + ".tmp")
        return (subject, grade, sem, "error", 0, str(e))


def main():
    token = load_token()
    with open(TARGETS_FILE) as f:
        targets = json.load(f)
    # 去掉 _sort 字段
    targets = [{k: v for k, v in t.items() if k != "_sort"} for t in targets]

    print(f"🚀 批量下载 {len(targets)} 本电子课本")
    print(f"   输出目录: {OUTPUT_DIR}")
    print(f"   并发数:   {PARALLEL}")
    print(f"   Token:    {token[:8]}...{token[-4:]} (len={len(token)})")
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        futures = {pool.submit(download_one, t, token): t for t in targets}
        for fut in as_completed(futures):
            t = futures[fut]
            res = fut.result()
            results.append(res)
            subj, grade, sem, status, size, msg = res
            if status == "ok":
                print(f"  ✅ {subj:4s} {grade} {sem} → {size/1024/1024:.1f} MB")
            elif status == "skip":
                print(f"  ⏭️  {subj:4s} {grade} {sem} (已存在, 跳过)")
            else:
                print(f"  ❌ {subj:4s} {grade} {sem} → {msg}")

    elapsed = time.time() - t0
    ok = sum(1 for r in results if r[3] == "ok")
    skip = sum(1 for r in results if r[3] == "skip")
    err = sum(1 for r in results if r[3] == "error")
    total_size = sum(r[4] for r in results if r[3] in ("ok", "skip"))

    print()
    print(f"📊 完成: ✅ {ok}  ⏭️ {skip}  ❌ {err}")
    print(f"   总大小: {total_size/1024/1024:.1f} MB")
    print(f"   耗时:   {elapsed:.1f}s")

    # 失败的列出来
    fails = [r for r in results if r[3] == "error"]
    if fails:
        print("\n失败列表:")
        for r in fails:
            print(f"  - {r[0]} {r[1]} {r[2]}: {r[5]}")


if __name__ == "__main__":
    main()