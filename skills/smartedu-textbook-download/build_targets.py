#!/usr/bin/env python3
"""Build download target list by filtering smartedu books.

Output: <output_dir>/targets.json (default: script dir/targets.json)

Data source priority:
  1. Local cache (./cache/part_*.json + data_version.json)
  2. Network fetch (smartedu CDN — may fail due to DNS/cert issues)
"""
import argparse
import glob
import json
import os
import subprocess
import sys

TAG_URL = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json"
DATA_VERSION = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json"

# ----- Default targets (小学语数英) -----
DEFAULT_TARGETS = [
    ("语文", "统编版"),                # 即人教版
    ("数学", "北师大版"),
    ("英语", "外研社版（主编：陈琳）"),  # 三年级起点
]


def fetch_json(url, max_retries=2):
    """Fetch via curl subprocess.

    Why curl (not Python requests/urllib)?
    ---------------------------------------
    s-file-1.ykt.cbern.com.cn DNS resolves to Baidu CDN IP
    (cdn.bcebos.com). That CDN expects SNI = *.cdn.bcebos.com,
    but the cert is wildcard *.ykt.cbern.com.cn. Python's urllib3
    uses the resolved IP's expected SNI → cert mismatch.

    curl does the right thing (uses requested host for SNI).

    Fallback: if s-file-1/2 fails with SSL/connection error, retry
    with the other host (s-file-X.ykt.cbern.com.cn mirrors s-file-Y).
    """
    import tempfile

    # Detect s-file-1/2 fallback
    url_attempts = [url]
    if "s-file-1.ykt.cbern.com.cn" in url:
        url_attempts.append(url.replace("s-file-1.", "s-file-2."))
    elif "s-file-2.ykt.cbern.com.cn" in url:
        url_attempts.append(url.replace("s-file-2.", "s-file-1."))

    last_error = None
    for attempt_url in url_attempts:
        with tempfile.NamedTemporaryFile(mode="r", suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            r = subprocess.run(
                ["curl", "-sSL", "--fail", attempt_url, "-o", tmp_path],
                capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                with open(tmp_path) as f:
                    return json.load(f)
            last_error = RuntimeError(
                f"curl failed for {attempt_url}: {r.stderr.strip()}")
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    raise last_error


def load_cache(cache_dir):
    """Load from local cache if available."""
    if not cache_dir:
        return None
    cache_dir = os.path.abspath(cache_dir)
    data_version_path = os.path.join(cache_dir, "data_version.json")
    if not os.path.exists(data_version_path):
        return None

    with open(data_version_path) as f:
        dv = json.load(f)
    urls = dv["urls"].split(",")

    books = []
    for u in urls:
        # Extract filename from URL
        fname = u.split("/")[-1]
        local = os.path.join(cache_dir, fname)
        if not os.path.exists(local):
            return None  # Cache incomplete
        with open(local) as f:
            books.extend(json.load(f))
    return books


def load_network(cache_dir=None):
    """Fetch from smartedu CDN (may fail on individual parts).

    If cache_dir is provided, also save the fetched data to cache so the
    next run is offline. Saves:
      - cache/data_version.json (on success)
      - cache/part_<n>.json (per part, even if others fail)

    CDN 路由经常抽风 (s-file-1/2 DNS 漂到百度云), 所以单 part 失败时
    不抛异常 — 把它从返回里剔除, 但继续保存成功的 part。
    """
    print("📡 从 CDN 拉目录 (首次或 cache 失效)...")
    try:
        dv = fetch_json(DATA_VERSION)
    except Exception as e:
        raise RuntimeError(
            f"无法拉取 data_version.json (smartedu CDN 不可达): {e}\n"
            f"  重试, 或参考 SKILL.md 已知陷阱。")

    urls = dv["urls"].split(",")
    seen = set()
    books = []
    part_files = {}  # url → (filename, data)
    failed = []

    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        fname = u.split("/")[-1]
        try:
            data = fetch_json(u)
        except Exception as e:
            failed.append((fname, str(e)))
            continue
        books.extend(data)
        part_files[u] = (fname, data)

    if failed:
        print(f"⚠️  {len(failed)} part 拉取失败 (CDN 路由抽风), 已跳过:")
        for fname, err in failed:
            print(f"     {fname}: {err[:80]}")

    if not books:
        raise RuntimeError(
            f"所有 part 都拉取失败, 无法继续。\n"
            f"  smartedu CDN 路由可能完全不可用, 稍后重试。")

    # Save to cache if path given
    if cache_dir:
        cache_dir = os.path.abspath(cache_dir)
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, "data_version.json"), "w") as f:
            json.dump(dv, f, ensure_ascii=False, indent=2)
        for url, (fname, data) in part_files.items():
            with open(os.path.join(cache_dir, fname), "w") as f:
                json.dump(data, f, ensure_ascii=False)
        print(f"💾 已保存到 cache: {cache_dir} "
              f"({len(part_files)}/{len(urls)} part 文件, {len(books)} 本书)")

    return books


def load_all_books(cache_dir):
    """Try cache first, fall back to network."""
    cached = load_cache(cache_dir)
    if cached:
        print(f"📦 使用本地 cache ({len(cached)} 本书) from {cache_dir}")
        return cached
    return load_network(cache_dir)


def parse_tags(book):
    """Return (subject, version, grade, semester) or None if 五•四学制 / 非小学."""
    tags = {t["tag_name"]: t["tag_id"] for t in book.get("tag_list", [])}
    if any("五•四学制" in k for k in tags):
        return None
    if "小学" not in tags:
        return None
    subject = next((k for k in ("语文", "数学", "英语") if k in tags), None)
    if not subject:
        return None
    skip = {subject, "电子教材", "教材", "上册", "下册", "全一册",
            "一年级", "二年级", "三年级", "四年级", "五年级", "六年级",
            "七年级", "八年级", "九年级", "小学"}
    version = next((k for k in tags if k not in skip), None)
    grade = next((k for k in ("一年级", "二年级", "三年级", "四年级",
                              "五年级", "六年级") if k in tags), None)
    sem = next((k for k in ("上册", "下册", "全一册") if k in tags), None)
    return subject, version, grade, sem


def build_targets(target_spec, out_path, cache_dir):
    all_books = load_all_books(cache_dir)
    g_order = {"一年级": 1, "二年级": 2, "三年级": 3, "四年级": 4,
               "五年级": 5, "六年级": 6}
    s_order = {"上册": 1, "下册": 2, "全一册": 3}

    def extract_pdf_url(book, cache_dir=None):
        """Get PDF URL from book metadata (avoid extra network call later).

        Priority:
          1. ti_storages[0] in the part-file book itself (some have it)
          2. Local metadata cache file (cache/metadata/{content_id}.json)
          3. None — caller will fetch from network if needed
        """
        for item in book.get("ti_items", []):
            if item.get("ti_is_source_file"):
                storages = item.get("ti_storages") or []
                if storages:
                    return storages[0]
                storage = item.get("ti_storage")
                if storage:
                    return storage.replace("cs_path:${ref-path}",
                                            "https://r1-ndr-private.ykt.cbern.com.cn")

        # Try local metadata cache
        if cache_dir:
            meta_path = os.path.join(cache_dir, "metadata",
                                     f"{book['id']}.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                    for item in meta.get("ti_items", []):
                        if item.get("ti_is_source_file"):
                            storages = item.get("ti_storages") or []
                            if storages:
                                return storages[0]
                            storage = item.get("ti_storage")
                            if storage:
                                return storage.replace(
                                    "cs_path:${ref-path}",
                                    "https://r1-ndr-private.ykt.cbern.com.cn")
                except Exception:
                    pass
        return None

    found = []
    for b in all_books:
        p = parse_tags(b)
        if not p:
            continue
        subject, version, grade, sem = p
        if (subject, version) in target_spec and grade:
            entry = {
                "subject": subject, "grade": grade, "semester": sem,
                "title": b["title"], "id": b["id"],
                "_sort": (g_order[grade], s_order.get(sem, 99)),
            }
            pdf_url = extract_pdf_url(b, cache_dir)
            if pdf_url:
                entry["pdf_url"] = pdf_url
            found.append(entry)

    found.sort(key=lambda x: (x["subject"], x["_sort"]))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(found, f, ensure_ascii=False, indent=2)

    from collections import defaultdict
    by_sub = defaultdict(list)
    for x in found:
        by_sub[x["subject"]].append(x)
    print(f"Total: {len(found)}")
    for sub in sorted(by_sub):
        print(f"  {sub}: {len(by_sub[sub])} 本")
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", default=None,
                        help="本地 cache 目录 (默认 ./cache/)")
    parser.add_argument("--no-cache", action="store_true",
                        help="强制从网络拉")
    parser.add_argument("--subject", action="append", default=[],
                        help="学科 (可多次指定: --subject=语文)")
    parser.add_argument("--version", action="append", default=[],
                        help="版本 (与 --subject 配对)")
    parser.add_argument("output", nargs="?",
                        default=os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            "targets.json"),
                        help="输出 targets.json 路径")
    args = parser.parse_args()

    cache_dir = args.cache_dir
    if cache_dir is None and not args.no_cache:
        cache_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "cache")
        # 不检查 isdir — 让 load_network 自己创建, 这样首次运行也能用
        # (如果 --no-cache 显式指定, 则完全不写 cache)

    # Build target spec
    spec = DEFAULT_TARGETS
    if args.subject or args.version:
        spec = list(zip(args.subject, args.version))

    print(f"Targets: {spec}")
    print(f"Cache:   {cache_dir or '(disabled)'}")
    build_targets(spec, args.output, cache_dir)


if __name__ == "__main__":
    main()