# srt-proofread-translate

一个用于 **SRT 字幕校对与翻译** 的 Agent Skill 工作流：输入一份英文 ASR 字幕，产出「英文修正版 + 中文正常版 + 国内自媒体合规版」三份文件，并跑完四轮硬验证。

适用于访谈、vlog、科技评测、探店、旅行等长视频的字幕整理，重点解决 ASR 常见的专名误识、数字错位、断句碎条、幻听整句等问题。

## 产出什么

与视频同目录、同基底名，播放器可直接加载：

| 文件 | 内容 |
|---|---|
| `<视频名>.srt` | 英文修正版，覆盖原文件 |
| `<视频名>_zh.srt` | 中文正常版 |
| `<视频名>_zh_douyin.srt` | 国内自媒体合规版（去平台名、去导流、去推广话术） |

## 特点

- **不猜专名**：内置四层模糊检索（原样 / 归一化 / 辅音骨架 / 相似度），专名被切在两条交界处也能找出来
- **防错位**：修正字典可写成 `(原文, 修正)` 元组做硬断言，key 偏一位立刻报错
- **全量验证**：条数、时间码、BOM、CRLF、条目间空行、标点、纯英文行、内容漂移、禁用词残留一次跑完
- **纯标准库**：只依赖 Python 3.10+，不需要 pip 安装任何第三方包

## 安装

把整个 `srt-proofread-translate` 文件夹放进 skills 目录：

| 系统 | 路径 |
|---|---|
| Windows | `C:\Users\<用户名>\.workbuddy\skills\srt-proofread-translate\` |
| macOS / Linux | `~/.workbuddy/skills/srt-proofread-translate/` |

依赖：Python 3.10+（仅标准库）。

自检：

```bash
python scripts/verify_srt.py --help
python scripts/dump_srt.py --help
python scripts/process_template.py --help
```

## 使用

```
第 0 步  探明规模      python scripts/dump_srt.py "视频.srt" --stats
第 1 步  全量通读建错  python scripts/dump_srt.py "视频.srt"
第 2 步  写 EN 修正字典
第 3 步  写中文翻译字典
第 3.5步 并排复读      python scripts/process_template.py --check
第 4 步  写前断言      python scripts/process_template.py --dry-run
第 5 步  写文件        python scripts/process_template.py
第 6 步  四轮验证      python scripts/verify_srt.py "视频.srt" --resid "..."
```

详细流程、28 条铁律、专名考据方法见 [SKILL.md](SKILL.md)。

## 目录结构

```
srt-proofread-translate/
├── SKILL.md                        # 流程 + 铁律 + 自检清单
├── scripts/
│   ├── dump_srt.py                 # 通读 / 并排复读 / 模糊检索 / 统计
│   ├── verify_srt.py               # 四轮验证
│   └── process_template.py         # 处理脚本模板（复制改名后填写）
└── references/
    ├── asr_patterns.md             # ASR 误识模式库（70+ 类，持续累积）
    └── douyin_compliance.md        # 抖音合规替换表
```

## License

[MIT](LICENSE)
