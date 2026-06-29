# 国家中小学智慧教育平台 电子课本下载器

一键批量下载 [basic.smartedu.cn](https://basic.smartedu.cn/) 上的电子课本 PDF。支持小学/初中/高中 全学科、全年级、全教材版本(人教/北师/外研社/SL/PEP/...等)。

## ✨ 特点

- 🚀 **一键流程**: 自动开 Chrome → 等用户登录 → 抓 token → 批量下载
- 📚 **任意组合**: 通过 `build_targets.py` 自定义学科+学段+版本+年级
- ⚡ **并发下载**: 默认 5 并发,32 本 1.7 GB ≈ 33 秒
- 🔁 **断点续传**: 已下载文件自动跳过,支持中断后再跑
- 🏷️ **官方命名**: 自动用 smartedu 列表里的官方书名(带"根据 2022 年版课程标准修订"等前缀)
- 🔐 **Token 7 天有效期**: 过期后重跑自动重新登录抓取

## 📦 安装

```bash
git clone https://github.com/flowioo/smartedu-textbook-download.git
cd smartedu-textbook-download
pip install requests websockets
```

依赖:
- Python 3.9+
- `requests`, `websockets`
- macOS / Linux / Windows(任意带 Chrome 的系统)
- `curl` 命令行工具 (用于拉 smartedu 目录,绕过 Python SSL 兼容问题)

## 🗂 数据来源(自动离线优先)

`build_targets.py` 拉教材目录的链路:

```
1. 本地 cache (./cache/part_*.json + data_version.json + metadata/*.json)
2. 网络: smartedu CDN (curl, 因 Python urllib3 在 macOS 系统 Python 上 SSL 不兼容)
```

首次运行建议把 cache 准备好,这样即使 CDN 路由抽风也能用。本 repo 已经包含了当前 smartedu 全部 3637 本教材的目录 cache,加 32 本 metadata cache (语文/数学/英语 小学)。

## 🚀 快速开始

### 方式 1: 复用你已有的 Chrome (推荐)

如果你平时就用 Chrome 上网,加一个启动参数让 Chrome 暴露 CDP 端口:

**macOS**:
```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --remote-allow-origins=*
```

之后正常登录 `https://basic.smartedu.cn/`,然后:

```bash
python3 download_all.py
```

脚本会自动检测到 9222 端口已开的 Chrome,抓 token,开始下载。整个过程 ~30 秒搞定。

### 方式 2: 自动启动临时 Chrome

不想改 Chrome 启动参数?直接 `--spawn` 让脚本自己开一个独立的 Chrome 实例:

```bash
python3 download_all.py --spawn
```

会自动:
1. 启动一个临时 Chrome (端口 9333, profile 在 `/tmp/smartedu-chrome-*`)
2. 打开登录页
3. 你在那个 Chrome 窗口里扫码登录
4. 脚本检测到 `localStorage.ND_UC_AUTH` 出现 → 抓 token → 下载
5. 下载完成后临时 Chrome 自动关闭 (除非加 `--keep-chrome`)

## 📋 下载自定义清单

默认下小学 1-6 年级:语文(统编版)+ 数学(北师大版) + 英语(外研社版三年级起点)。想下别的?改 `build_targets.py` 里的 `DEFAULT_TARGETS`,或者直接传参:

```python
# build_targets.py 里 DEFAULT_TARGETS:
DEFAULT_TARGETS = [
    ("语文", "统编版"),                          # 小学
    ("数学", "北师大版"),
    ("英语", "外研社版（主编：陈琳）"),          # 三年级起点
    ("英语", "人教版（PEP）（主编：吴欣）"),    # 三年级起点 PEP
    ("物理", "人教版"),                          # 初中
    ("化学", "人教版"),
    # ... 任意 (学科, 版本) 组合
]
```

要查 smartedu 上某个学科有哪些版本,先跑:

```bash
python3 build_targets.py 2>&1 | head -50
# 找到想要版本的精确字符串,加到 DEFAULT_TARGETS
```

版本字符串(常见):
| 学科 | 版本 |
|------|------|
| 语文 | `统编版` (即人教版,小学唯一统编) |
| 数学 | `人教版` / `北师大版` / `苏教版` / `冀教版` / `青岛版` / `北京版` / `西南大学版` |
| 英语 | `人教版（PEP）（主编：吴欣）` / `外研社版（主编：陈琳）` / `译林版` / `北师大版` / `冀教版` / `湘少版` / `粤教粤人版` ... |

完整列表 = smartedu 全部,跑 `build_targets.py` 时会打印。

## 🗂 输出结构

```
~/Downloads/textbooks/
├── 数学/
│   ├── （根据2022年版课程标准修订）义务教育教科书·数学一年级上册.pdf
│   ├── （根据2022年版课程标准修订）义务教育教科书·数学一年级下册.pdf
│   ├── ... (1-6 年级上下册, 12 本)
│   └── 义务教育教科书·数学六年级下册.pdf
├── 语文/
│   └── ... (12 本)
└── 英语/
    └── ... (8 本, 3-6 年级, 三年级起点)
```

## 🔧 高级选项

```bash
# 指定 CDP 端口 (默认 9222)
python3 download_all.py --port 9333

# 只抓 token, 不下载
python3 download_all.py --skip-download

# 改输出目录
SMARTEDU_OUTPUT_DIR=/path/to/textbooks python3 download_all.py

# 改并发数
SMARTEDU_PARALLEL=10 python3 download_all.py

# spawn 模式 + 保留 Chrome
python3 download_all.py --spawn --keep-chrome
```

## 📜 子脚本

| 脚本 | 用途 |
|------|------|
| `download_all.py` | 一键 (登录+抓 token+下载+重命名) |
| `build_targets.py` | 生成下载清单 (按学科/版本筛) |
| `download_batch.py` | 仅下载 (假定 token + targets 已存在) |
| `get_token_cdp.py` | 仅抓 token |
| `rename_to_official_titles.py` | 仅重命名已下载文件 |

## ❓ 常见问题

### Token 401 怎么办?

token 7 天过期。直接重跑 `download_all.py`,会自动重新登录抓 token。

### Chrome 提示"需要登录"但其实我已经登录了?

你的常驻 Chrome 可能用了不同 user-data-dir。`download_all.py` 默认接 9222 端口,如果你的 Chrome 不在这个端口,加 `--port <你的端口>`。

### 下载到一半中断了怎么办?

重跑 `download_all.py`,已下载的会自动跳过(按文件大小判断)。

### 想下初中/高中课本?

改 `build_targets.py` 里 `DEFAULT_TARGETS`,把 `"小学"` 那段 filter 改成 `"初中"` 或 `"高中"`,然后重新跑。或者直接在脚本里搜更通用的 tag 解析函数。

### macOS 上 Chrome 提示"已损坏"?

不是这个项目的问题: `xattr -cr /Applications/Google\ Chrome.app`

## 📝 协议

MIT License. 课本版权归人民教育出版社等所有,本工具仅供个人学习使用。

## 🙏 致谢

- [happycola233/tchMaterial-parser](https://github.com/happycola233/tchMaterial-parser) — 揭示了 `X-ND-AUTH` 鉴权机制
- [ChinaTextbook](https://github.com/TapXWorld/ChinaTextbook) — 镜像归档项目