---
name: smartedu-textbook-download
description: Download electronic textbooks (PDFs) from 国家中小学智慧教育平台 (basic.smartedu.cn) by automatically capturing the user's access_token from their already-logged-in Chrome (via CDP) and downloading with the X-ND-AUTH header. Use this skill when the user wants to download smartedu textbooks, 课本, 电子课本, 中小学教材 PDFs, or mentions subjects like 语文/数学/英语 with grades and 册次. Triggers on phrases like "下载课本", "下教材", "下载 PDF 教材", "下载人教版/北师大版/外研社版", "批量下电子课本", or any request for K-12 textbooks from basic.smartedu.cn.
---

# 国家中小学智慧教育平台 电子课本下载器

一键批量下载 [basic.smartedu.cn](https://basic.smartedu.cn/) 上的电子课本 PDF。

支持任意学科、学段(小学/初中/高中)、教材版本(人教/北师/外研社/SL/PEP/...)。

## 一键脚本

仓库里所有脚本都在这个目录下,可以直接执行:

```bash
# 一键完成全部流程
python3 download_all.py

# 仅抓 token (不下载)
python3 download_all.py --skip-download

# 自动启动独立 Chrome (用户登录后自动检测)
python3 download_all.py --spawn

# 仅下载 (假定 token.json + targets.json 已存在)
python3 download_batch.py

# 仅抓 token
python3 get_token_cdp.py
```

## 工作流程

```
┌─────────────────────────────────────────────────────────────────────┐
│ 用户的 Chrome (已登录 basic.smartedu.cn)                            │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          │ CDP attach + Runtime.evaluate
                          │ 读 localStorage.ND_UC_AUTH*
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ token.json  ── 包含 access_token                                    │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          │  X-ND-AUTH: MAC id="<token>",nonce="0",mac="0"
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ requests 直接下载 PDF (r1-ndr-private.ykt.cbern.com.cn)             │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ~/Downloads/textbooks/{学科}/{官方书名}.pdf                          │
└─────────────────────────────────────────────────────────────────────┘
```

## 关键发现

1. **服务端不是 TLS 指纹鉴权**, 而是 `X-ND-AUTH` HTTP header 鉴权:
   ```
   X-ND-AUTH: MAC id="<access_token>",nonce="0",mac="0"
   ```
   `nonce` 和 `mac` 任意非空字符串都行 (服务端只校验 token 有效性)。

2. **access_token 在 localStorage**: 登录后, smartedu.cn 的 SSO 会写
   `ND_UC_AUTH-<tenant>&<app>&token` 这个 key, 里面 `JSON.parse(.value).access_token`
   就是我们要的 token。7 天有效期。

3. **元数据/目录 API 走 `*.ykt.cbern.com.cn`**: 这个 host DNS 解析到百度云 CDN,
   Python urllib3 因 SNI 不匹配会 SSL 报错 (证书是 `*.ykt.cbern.com.cn` 但 SNI 期望 `*.cdn.bcebos.com`)。
   **用 `curl` 命令行绕过**: curl 用请求的 host 做 SNI。

4. **目录和 metadata 可离线缓存**: 首次跑通后, 把 data_version.json + 4 个 part 文件
   + 各书 metadata.json 缓存到本地, 后续运行不再需要联网。

## 文件说明

| 文件 | 用途 |
|------|------|
| `download_all.py` | 一键入口 (抓 token + 下载 + 重命名) |
| `build_targets.py` | 生成下载清单, 优先用本地 cache (cache/part_*.json) |
| `download_batch.py` | 仅下载 (假定 token + targets 已存在) |
| `get_token_cdp.py` | 仅抓 token (CDP 读 localStorage) |
| `rename_to_official_titles.py` | 把 PDF 重命名为 smartedu 官方书名 |
| `cache/` | **(运行时自动生成, 不在 git 里)** 离线缓存 smartedu 教材目录 |
| `SKILL.md` | 本文件 |

## 首次运行

**需要网络**: 首次跑会从 smartedu CDN 下载教材目录 (32MB) 到 `cache/` 目录。
之后所有运行都走本地 cache, 不再需要网络, 也不依赖 CDN 路由。

**CDN 路由抽风怎么办**: smartedu CDN 经常改 DNS / SNI 配置, 详见下方"已知陷阱"。

要重建 cache:

```bash
rm -rf cache/             # 强制下次跑时重新下载
python3 download_all.py
```

## 默认下载清单

`build_targets.py` 的 `DEFAULT_TARGETS`:

```python
DEFAULT_TARGETS = [
    ("语文", "统编版"),                  # 即人教版
    ("数学", "北师大版"),
    ("英语", "外研社版（主编：陈琳）"),  # 三年级起点
]
```

下别的版本时直接改这个列表。

## 前置依赖

```bash
pip install requests websockets
# + 系统有 Chrome + curl 命令行工具
```

## 输出示例

```
~/Downloads/textbooks/
├── 数学/
│   ├── （根据2022年版课程标准修订）义务教育教科书•数学一年级上册.pdf
│   ├── ... (1-6 年级上下册, 12 本)
│   └── 义务教育教科书·数学六年级下册.pdf
├── 语文/  (12 本, 统编版即人教版)
└── 英语/  (8 本, 外研社版三年级起点 3-6 年级)
```

## 性能参考

- 单 PDF 平均 50MB, 5 并发下 32 本 1.7 GB ≈ 33 秒
- 网络瓶颈在 CDN, 8 并发无明显提升

## 关键 API

| 用途 | URL |
|------|-----|
| 学段/学科/版本 tag 树 | `https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json` |
| 所有课本清单 (4 个 part) | `https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json` |
| 单本书元数据 + PDF URL | `https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{cid}.json` |

## tag 命名规律

- `tag_paths[0].split("/")[1]` = 学段: `小学` / `初中` / `高中` / `小学（五•四学制）` / `初中（五•四学制）`
- 学科: `语文` / `数学` / `英语` / ...
- 版本: `统编版` (语文唯一) / `人教版` / `北师大版` / `外研社版（主编：陈琳）` / `译林版` ...

过滤时**必须排除 "五•四学制"**, 因为这些虽然归在 tag_list "小学" 但教材内容不同。

## 已知陷阱

1. **不能用 curl 直接下**: 单独 `curl` (无 X-ND-AUTH) 会被 CDN 401, 必须带 token。
2. **token 7 天过期**: 过期后 401, 重跑 `download_all.py` 重新抓。
3. **macOS 系统 Python 跑 requests 到 cbern CDN 必失败**: 用 curl 子进程代替。
4. **学段 tag 要严格匹配**: 部分 "五•四学制" 教材 tag_list 里写的是 "小学", 容易混入。
5. **macOS 文件名带全角括号**: `（`/`）` 是合法字符, 直接 `os.rename` 即可。