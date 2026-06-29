# 国家中小学智慧教育平台 电子课本下载器

一键批量下载 [basic.smartedu.cn](https://basic.smartedu.cn/) 上的电子课本 PDF。

**支持任意 agent 一键安装**: Claude Code / Codex / OpenCode / Cursor / Hermes Agent / 等 70+ agents。

```bash
# 一行安装 (在任意 agent 中运行)
npx skills add flowioo/smartedu-textbook-download
```

详见 [`skills/smartedu-textbook-download/SKILL.md`](skills/smartedu-textbook-download/SKILL.md)。

## ✨ 特点

- 🚀 **一键流程**: 自动检测/启动 Chrome → 等用户登录 → 抓 token → 批量下载
- 📚 **任意组合**: 学科 + 学段(小学/初中/高中) + 教材版本(人教/北师/外研社/SL/PEP/...)
- ⚡ **并发下载**: 5 并发,32 本 1.7 GB ≈ 33 秒
- 🔁 **断点续传**: 已下载自动跳过
- 🏷️ **官方命名**: 用 smartedu 列表里的官方书名
- 🔐 **Token 7 天有效期**: 过期后自动重新登录抓取
- 📦 **离线 cache**: 首次跑通后缓存到本地,后续运行不再依赖 CDN

## 🚀 三种安装方式

### 1. 通用安装 (推荐,支持所有 agent)

```bash
npx skills add flowioo/smartedu-textbook-download
```

安装后,在 Claude Code / Codex / OpenCode / Hermes Agent / Cursor 等里说:
> "帮我下载小学 1-6 年级 语文/数学/英语 课本"

agent 会自动加载这个 skill 并运行。

### 2. Hermes 用户

```bash
hermes skills install flowioo/smartedu-textbook-download
```

### 3. 手动 clone

```bash
git clone https://github.com/flowioo/smartedu-textbook-download.git
cd smartedu-textbook-download/skills/smartedu-textbook-download
pip install requests websockets
python3 download_all.py
```

## 📋 使用方法

### 方式 A: 复用你已有的 Chrome (推荐)

启动 Chrome 时带 CDP 端口:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --remote-allow-origins=*
```

正常登录 `https://basic.smartedu.cn/`,然后:

```bash
python3 download_all.py
```

脚本会自动: 抓 token → 准备清单 → 批量下载 → 官方书名重命名。整个过程 ~30 秒搞定。

### 方式 B: 自动启动临时 Chrome

```bash
python3 download_all.py --spawn
```

会自动:
1. 启动一个临时 Chrome (端口 9333, profile 在 `/tmp/smartedu-chrome-*`)
2. 打开登录页
3. 你在那个 Chrome 窗口里扫码登录
4. 脚本检测到 `localStorage.ND_UC_AUTH` 出现 → 抓 token → 下载
5. 下载完成后临时 Chrome 自动关闭

## 🗂 输出结构

```
~/Downloads/textbooks/
├── 数学/  (12 本)
│   ├── （根据2022年版课程标准修订）义务教育教科书•数学一年级上册.pdf
│   ├── ... (1-6 年级上下册)
│   └── 义务教育教科书·数学六年级下册.pdf
├── 语文/  (12 本, 统编版即人教版)
└── 英语/  (8 本, 外研社版三年级起点 3-6 年级)
```

## 📜 协议

MIT License. 课本版权归人民教育出版社等所有,本工具仅供个人学习使用。

## 🙏 致谢

- [happycola233/tchMaterial-parser](https://github.com/happycola233/tchMaterial-parser) — 揭示了 `X-ND-AUTH` 鉴权机制
- [ChinaTextbook](https://github.com/TapXWorld/ChinaTextbook) — 镜像归档项目
- [vercel-labs/skills](https://github.com/vercel-labs/skills) — Skill 分发协议 (Skills CLI)