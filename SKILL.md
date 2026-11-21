---
name: srt-proofread-translate
description: "通用版 SRT 字幕校对与翻译工作流。触发词：老规矩、校对 srt、翻译字幕、srt 校对翻译。输入英文 ASR 字幕，产出「英文修正版（覆盖原文件）+ 中文正常版 _zh.srt + 国内自媒体合规版 _zh_douyin.srt」三份文件，并完成四轮验证。跨平台可移植，仅依赖 Python 3 标准库。"
version: "2.3-generic"
agent_created: true
---

# SRT 字幕校对·翻译通用工作流（老规矩 v2.3）

> 本文件是**可移植通用版**：不含任何本机专属路径、不含任何具体项目信息。整套文件夹复制到别的电脑即可使用。
>
> **v2.3 更新（2026-11，纽约步行化 106 / MSI EdgeMesa 285 / GTA6 迈阿密 330 三单沉淀）**
> - 新增 `scripts/dump_srt.py`：**通读 / 并排复读 / 四层模糊检索 / 概况统计** 四合一，替代每个项目临时手写的小脚本（那些脚本反复出"漏最后一条""正则被 shell 吞"的事故）。
> - `scripts/process_template.py` 升到 v2：`EN_FIX` 支持 `(原文, 修正)` **元组硬断言**、自动备份 + 幂等重跑、**漏词审计**、**resid 预检**、写盘字节自检。
> - `scripts/verify_srt.py` 升到 v3：新增 **「条目间空行 = N−1」硬检查**（历史上 VideoSubtitleTool 把整份当 1 条的直接防线）、双 BOM / 重复标点 / 条目内换行、**解析残留尾块告警**、`--stats`。
> - 新增 **铁律 23–28**：第二路 ASR 三结局、中间产物治理、命令行写正则的坑、数字单位粘连、幻听整句、产品名反查库。
> - 第 1 节「收尾」改为硬规则：**视频目录最终只留三份成品**。
>
> **v2.2 更新（2026-09，NZ 447 / 米兰 Bartolini 684 / 英国牛排馆 455）** —— 铁律 17「check 文件全量逐条复读」、铁律 18「动手前硬解析核实条数」、铁律 11 补强「断言词选公共前缀 + untouched 大小写敏感」、第 5 节「DY_OVR 按禁用词实际落点覆盖」、第 8 步「resid 必须写 ASR 原始错误形态」。
>
> **v2.1 更新（2026-09）** —— 铁律 15「同一专名多种错拼必须逐点全改」、铁律 16「碎条与跨条目承接」、铁律 2 / 第 5 节「合规版禁用词扫描不看语境」、第 6.8 节「动手前先 WebSearch」、铁律 10「纯数字/年份行的漂移处理」、铁律 11「EN_FIX 的 key 必须回 dump 逐条核对」。

---

## 0. 安装与跨机器使用

**安装位置**（把整个 `srt-proofread-translate` 文件夹放进去）：

| 系统 | 路径 |
|---|---|
| Windows | `C:\Users\<用户名>\.workbuddy\skills\srt-proofread-translate\` |
| macOS / Linux | `~/.workbuddy/skills/srt-proofread-translate/` |

**依赖**：仅需 Python 3.10+，脚本只用标准库（`re` / `os` / `sys` / `io` / `shutil` / `subprocess` / `argparse` / `difflib`），**不需要 pip 安装任何第三方包**。

**找不到 `python` 命令时**，用绝对路径调用。Windows 上常见形式：
```
"C:\Users\<用户名>\.workbuddy\binaries\python\versions\3.13.12\python.exe"
```

**folder 结构**
```
srt-proofread-translate/
├── SKILL.md                        ← 本文件（流程 + 铁律 + 清单）
├── scripts/
│   ├── dump_srt.py                 ← 通读 / 并排复读 / 模糊检索 / 统计
│   ├── verify_srt.py               ← 四轮验证（直接运行）
│   └── process_template.py         ← 处理脚本模板（复制改名后填写）
└── references/
    ├── asr_patterns.md             ← ASR 误识模式库（持续累积，70+ 类）
    └── douyin_compliance.md        ← 抖音合规替换表
```

**上手先自检三条**：
```
python scripts/verify_srt.py --help
python scripts/dump_srt.py --help
python scripts/process_template.py --help
```

---

## 1. 输入输出契约（固定，不用问用户）

**输入**：任意英文 ASR 字幕 `<视频名>.srt`（用户直接给路径）。

**输出三份**，与视频同目录、同基底名，保证播放器能自动加载：

| 文件 | 内容 |
|---|---|
| `<视频名>.srt` | 英文修正后**覆盖原文件** |
| `<视频名>_zh.srt` | 中文正常版 |
| `<视频名>_zh_douyin.srt` | 国内自媒体合规版 |

**编码铁律**：UTF-8、**恰好一个 BOM**、CRLF 换行。解析前先剥掉所有 BOM，写回时只加一个。

**解析兼容性**（脚本已内置，无需自己写正则）：
- 兼容「条目间有空行」（标准）与「条目间无空行」（部分工具产出）两种变体
- 兼容毫秒分隔符 `,` 与 `.`；时间码行尾带 `align:start` 之类附加设置也能解析
- 条目文本用 `.strip()` 去掉分隔空行残留
- 输出统一规范化：**单 BOM + CRLF + 条目间空行**
- ⚠️ 自己手写正则时，`(?=\n\n|\n?\Z)` 这类写法**遇到无空行的文件会把整篇当成 1 条**（曾实测：5 条被解析成 1 条）。改用「向后看下一个 `\n<序号>\n<时间码>`」的写法，或直接用 `dump_srt.py`。
- 🚨 **下游事故案例（2026-09-12）**：`process_template.py` 的 `write_srt()` 曾漏写"条目间空行"（`'\n'.join('%d\n%s\n%s')`），产出的是 `序号/时间码/文本` 紧挨着的非标准 SRT。本 skill 的 `verify_srt.py` 能解析所以没报错，但 **VideoSubtitleTool 的双语字幕页按空行分块**，把整份 628 条的字幕解析成 1 条 → 合并出的双语 SRT 变成两行巨无霸文本 → **嵌入后视频完全没有字幕**。已修复为 `'\n\n'.join(...)`，并在 **verify v3 里加了「条目间空行 = N−1」硬检查**。
- 反查同类问题的快速判据：`b'\r\n\r\n'` 计数为 0 而 `.srt` 条目数 >1 → 该文件缺条目间空行。

**收尾（硬规则，用户明确要求）**：
视频目录最终**只保留**：原视频 + 用户原有素材（图片/封面等）+ **三份 SRT**。
其余一切中间产物——原文备份 `_en_original.srt`、`fix.py`、`zh_part*.py`、`proc.py`、`check.txt`、`ref.*.vtt`、`bilingual_merged_debug.srt` 之类——**全部放进 `_tmp_<项目>/`，交付时整目录 `shutil.rmtree`**。详见铁律 24。

---

## 2. 工作流（第 0 步 + 第 1–8 步）

### 第 0 步　探明规模
```
python scripts/dump_srt.py "<视频名>.srt" --stats
```
一次拿到：条数（正则硬解析）、时长、平均长度、BOM/CRLF/空行组数、最短 5 条、最长 1 条、**尾块是否有残留**。
- **条数以正则结果为准**，后续所有断言都以这个 N 为基准（铁律 18）
- 尾块告警 = 末条可能没被正确解析，必须人工看

**先确认正文字幕到底是哪种语言——文件名/标题的语言不等于字幕语言。**
实例：`Harmony OS 7 es OFICIAL ｜ CHINA está a otro NIVEL.srt` 标题是西语，正文其实是英文。
若正文不是原声语言而是**自动翻译轨**，处理重点会变（见第 6.7 节「机翻轨」）。

### 第 1 步　全量通读原文，建错误清单
```
python scripts/dump_srt.py "<视频名>.srt"          # 全部条目
python scripts/dump_srt.py "<视频名>.srt" 1 120    # 分段读
```
- 逐条读完（大文件分 3–4 段），**不要只扫"眼熟"的**
- **重点扫描以下 ASR 错误类型**：
  - **人名**：RhineWalker→RyanWalker、Thunka→Duncan、Quinn→Qwen
  - **地名**：Langkawi←Lang Cawie、Kampung←Campong、Harold→Herald
  - **品牌/产品**：Saily←Sally、Marriott←Mary out、Ritz-Carlton←Ritzkelt、Fontainebleau←fountain blue、Loews←Lowes
  - **断词/连读**：let's see←some cures to see、hollandaise has←holidays has、`Tri-Linator`→trying Linux
  - **同音近词（最难）**：wine list←wireless、truffle←traffic、porcini←porcina、foie gras←fogra、hare←hair、borscht←the Bosch、beets←bits、curbs←curves、seedy←C.D.
  - **口语吞音/th-fronting/GPT→PT**：Pro Freeze←Pro 3s、Chatty PT←ChatGPT
  - **专业术语**：Omarchy←Olmarky、DHH←BCH、Codex←codecs、Tailscale←tail scale、woonerf←vonrf
  - **数字/单位/型号粘连**：`3.1 8B`→`3.18B`、`140-watt`→`40-Watt`（铁律 26）
- **专有名词贯穿全文**：同一名称常有**多种不同错拼**（铁律 15），逐一记录
- **不确定的专有名词先查，不要猜**（见第 6 节；餐饮/科技类先做一次 WebSearch，见 6.8）

**专名检索别靠肉眼翻**，用四层模糊检索（铁律 15 的落地工具）：
```
python scripts/dump_srt.py "<视频名>.srt" --find "Fontainebleau"
#   L1 原样子串 → L2 归一化（忽略大小写/空格/连字符）
#   L3 辅音骨架（fountain blue ↔ Fontainebleau、Lowes ↔ Loews）
#   L4 相似度兜底（--thresh 0.78，可降）
#   另外自动对 k 与 k+1 拼接后再搜：专名被切在两条交界处才找得到
```

### 第 2 步　写 EN 修正字典 `EN_FIX`
```python
EN_FIX = {
    2: ("the three Michelin star Uliassi. Beautiful.",
        "the three-Michelin-star Uliassi. Beautiful."),
}
```
- **推荐写成 `(原文整条, 修正后整条)` 元组**：`old` 会成为硬断言，key 写偏一位立刻报「原文不符」。这是防偏移最硬的一道闸门，比任何事后复查都可靠。
- **整条替换**：值必须是该条的**全部**文本（只写半句会被漏词审计拦下，见铁律 13）
- **不跨条目**：不得把相邻条目的内容拼进来（见铁律 7）
- **key 必须回 dump 逐条核对**：`python scripts/process_template.py --keys` 或 `dump_srt.py` 对着念一遍（见铁律 11）
- 条目号必须是连续整数，不跳号

### 第 3 步　写中文翻译字典 `ZH`
- 大文件分片写：`zh_part1.py`（1–350）、`zh_part2.py`（351–700）……
- 最后 `ZH = {}; ZH.update(ZH1); ZH.update(ZH2); ...`（`process_template.py` 自动合并）
- 覆盖 **1..N 全部条目**，**禁止空值**（见铁律 1）
- 标点规范见第 3 节
- 合规版处理在**翻译时同步完成**（见第 5 节）
- 写完先做一次**抽查对齐预检**：抽首部、25%、50%、75%、尾部各 1 条，比对 EN 与 ZH 语义是否对应；不对应就是有偏移，立即回溯

### 第 3.5 步　并排复读（不许跳过）
```
python scripts/process_template.py --check     # 生成 check.txt（EN| / ZH| / DY|）
python scripts/dump_srt.py "<视频名>.srt" --zh 1 120    # 或直接分段看
```
**从头读到尾，宁可分 3–4 次读完**（铁律 17）。漂移检测只能抓量级失衡，抓不到"短句互撞"和"半条错位"。

### 第 4 步　写文件前先断言（铁律 8）
`process_template.py` 会自动跑：原文断言 → 漏词审计 → 专名断言 → untouched 断言 → resid 预检 → 中文完整性 → 标点 → 漂移。
```
python scripts/process_template.py --dry-run   # 全绿才继续
```

### 第 5 步　写文件
```
python scripts/process_template.py            # 写三份 + 字节自检 + 自动调 verify
```
模板内部：首次运行把原文备份到脚本同目录（即 `_tmp_<项目>/`），之后永远从备份读 → **可反复重跑、结果字节一致**。
```python
def write_srt(path, tc, texts):
    body = '\n\n'.join('%d\n%s\n%s' % (k, tc[k], texts[k]) for k in sorted(texts))
    data = ('\ufeff' + body + '\n').replace('\n', '\r\n').encode('utf-8')
    open(path, 'wb').write(data)
```
（注意 `'\n\n'.join` —— 条目间必须有空行；`replace('\n','\r\n')` —— 不是 `replace('\r\n','\r\n')`，那是一次空操作。）

### 第 6 步　四轮验证（必须全绿）
```
python scripts/verify_srt.py "D:\path\to\视频名.srt" --resid "Sally,mission star"
```
详见第 4 节。

### 第 7 步　交付
- `present_files` 呈现三份输出（中文正常版 → 合规版 → 英文修正版）
- 回复里带**结果表**（模板见第 7 节）+ **存疑项与推断项**
- 清理临时目录；把新发现的 ASR 误识模式追加进 `references/asr_patterns.md`

### 第 8 步　跨条目漏网之鱼复查
ASR 错误常跨条目分界（错误词组被切在相邻两条的首尾）。
- 用残留词表再扫一遍（`verify_srt.py --resid ...`），确认清零
- 跨条目承接的词组必须**两条同时改**（见铁律 16）
- ⚠️ `Edit` 后必须复读验证：Edit 有时返回 success 但文件实际未变更（EBUSY 资源锁定）
- **resid 词表必须写 ASR 的「原始错误形态」**：写修正后文本里仍会出现的子串必然自造假告警。
  > 实例：原文 `let's get out of here one's way` 修正为 `this one's way`，resid 若写 `one's way` 会命中修正后的正确句子；应写 `here one's way`。
  > 反向铁律：**存疑保留的词绝不进 resid**（见第 6 节第 0 条），否则必 FAIL。
- **Edit 大字典时的连带删除**：用锚点行做 Edit 插入新条目时，确认没有把锚点行本身替换掉（曾把 `167:` 行误删，靠复读字典全文发现并补回）。改完字典**通读一遍**再跑脚本。

---

## 3. 铁律（逐条遵守，违反即事故）

### 铁律1　翻译字典禁止空值
任何条目值为 `""` 都会让该条在 SRT 里塌陷，导致后续整段错位。校验：`len(ZH) == N` 且每条 `.strip()` 非空。

### 铁律2　翻译阶段同步生成合规版
翻译时就写好合规文本，**不事后补救**。一次产出 `_zh.srt` 和 `_zh_douyin.srt`；后者只改需要改的条目，**时间码与条数完全不变**。

> ⚠️ **合规版的禁用词扫描不看语境**：`verify_srt.py` 第 5 节对 `订阅 / 频道 / 赞助 / 广告 / 链接` 做**全文匹配**，正文里**描述性、非推广**的用词同样会被判 FAIL。
> 例：`本期视频的赞助商` → 须改「本期视频的**合作伙伴**」；泛泛谈「广告收入」→ 改「**推广**收入」；「订阅制」→ 「**按月收费**」；描述性的「闪烁的广告牌」→「闪烁的**灯箱屏幕**」。
> 原则：合规版里这些词**一个都不能留**，用同义中性词替换（不是删句子），时间码与条目号不动。

### 铁律3　输出后立即验证
脚本跑完不算结束，必须在**同一轮对话**内完成：条数、时间码、`——`=0、`：`=0、纯英文行=0、全量漂移=0、条目间空行=N−1。

### 铁律4　字典 key 必须与条目号严格 1:1
- **禁止合并**（把两条英文塞进一条中文）
- **禁止跳号**
- 断言 `set(zh.keys()) == set(range(1, N+1))`

### 铁律5　先剥离全部 BOM，写回只加一个
原文件可能是双 BOM（`EF BB BF EF BB BF`），会让条目 1 被解析器吞掉。
```python
while raw.startswith('\ufeff'): raw = raw[1:]
```

### 铁律6　短句也必须翻译，不许"省略可接受"
`Okay.` / `Thank you.` / `Yeah.` / `Oh.` 这类一律要中文（好。／谢谢。／是啊。／哦。）。
**纯英文行扫描结果必须为 0**，不得以「不影响理解」为由放过任何一行。

### 铁律7　EN 修正禁止跨条目合并
每条修正只改自己条目的词；想统一改一个通用词（如 `Sally`→`Saily`），就逐条独立写修正文本，不要重写整条、更不要带上邻条内容。

### 铁律8　先验证后写文件
**写文件之前**先跑断言与漂移检测。英文原文件一旦被覆盖就无法恢复（所以模板会自动备份），验证失败就回去改字典，循环到通过为止。

### 铁律9　纯拉丁行 = 0，用"中文括注"解决而不是改英文
字幕里出现**整行没有任何中文字符**的情况，必须处理，但**不要动英文原词**：
| 情境 | 处理 |
|---|---|
| 条目本身是外文专名（菜名/酒名/当地语） | 英文保留，中文加括注：`"Tagliolini。"` → `"Tagliolini（细扁面）。"` |
| 条目是 ASR 乱码的当地语 | 先按邻条译文还原成最可能的原文，再处理中文：`"Acorimare。"` → `"Acqua di mare（海水）。"` |
| 赞助商/品牌独占一条（`Holafly eSIM.`） | 中文补括注：`Holafly eSIM（旅行联网服务）。`；合规版整体泛化为「一款 eSIM。」 |
| 型号/芯片独占一条（`N1X.`） | 补品类词：`N1X 芯片。` / `就是这颗 N1X。` |

### 铁律10　全量内容漂移检测（不是抽检）
```python
for i in range(1, N + 1):
    en_w, zh_cn = len(EN[i].split()), count_cn(ZH[i])
    if (en_w > 8 and zh_cn <= 4) or (en_w <= 3 and zh_cn > 12) or zh_cn == 0:
        report_mismatch(i)
```
**必须为 0 条。** 必须用 SRT 的**条目号**做 key 比较，不能用数组下标（一方丢条目时下标仍对齐、内容已错位）。

**常见误报与对应处理（人工确认后再决定是否改）**
- **中文数字 vs 阿拉伯数字**：EN `10 years` / ZH `十多年前`；EN `33, 45, 60` / ZH `三十三、四十五、六十` → 正常
- **关键词族无对应词**：EN 有 `wine`，ZH 用具体酒名（`黑皮诺`）而没出现「酒」→ 正常
- **大小写不敏感的残留扫描命中"正确写法"**：把 `four seasons` 放进残留词表，会命中自己写对的 `Four Seasons`（8 处），误报。**残留词一律用大小写敏感匹配**
- **纯数字 / 年份列表行（真问题，须补中文）**：整条只有数字或年份（如 `"61, 62, 63, … 73."`），`.split()` 出十几个 token，但中文若只写数字则 CJK 计数为 0 或极小 → 被判 `en>8 词配 zh≤4 字`。解法：中文补一个描述词，如 `"这些年份。"` / `"六十年代到七十年代。"`。**别改阈值，补中文即可**
- **专名密集行中文 CJK 过少（真问题，靠补中文虚词解决）**：EN 词多但几乎全是拉丁专名时，中文 CJK 会偏小而被判漂移。实例：`There is Apple Pencil support on the iPhone Duo.` → `iPhone Duo 这台机器支持 Apple Pencil。`；`Took a look at the iPhone 18 Pro and the 18 Pro Max.` → `我也看了看 iPhone 18 Pro 和 18 Pro Max。`
- **反向触发（中文太长）**：EN 只有 2–3 词、中文却塞了 13 字以上，同样会告警。实例：`Out of the box, Windows 11.` 译成「开箱预装的就是 Windows 11。」就超了 → 压到「开箱就是 Windows 11。」
- 反之，若同一条 EN 与 ZH **语义完全无关**，就是真错位或整条叠加，必查
- **原则：验证器报 FAIL 先分辨真假，再动文件。** 真问题照改，误报就修正词表 / 阈值，并把这个误报记进本节
- **专名/酒名/年份独占一条（纯拉丁，真问题，补中文描述词）**：`Albariño.` → `酒是Albariño。`；`Mouton 1928.` → `Mouton 1928这一瓶。`；`1945.` → `还有1945年的那一瓶。`。别改阈值，补中文虚词即可

### 铁律11　专名断言 + 未修正条目原文断言（防 key 偏移一位）
漂移检测**查不出整段平移**。必须对专名出现点做硬断言：
```python
assert "Uliassi" in t[2] and "Uliassi" in t[223]
assert "Mattia" in t[896] and "spaccasassi" in t[624].lower()     # 注意大小写
assert "Oh, this is the salt." in t[610]                          # 未修正条目须保持原文
assert "The anchovies give it" in t[500]                          # 防相邻条目被覆盖
```
- 贯穿全文的专名，至少选 2–3 个出现点断言
- **断言必须考虑大小写**：句首大写的词用 `.lower()` 比较
- **驼峰专名不能用「忽略大小写」的子串断言**：`"FaceTime" in "FaceTiming my dog".lower()` 结果是 **False** —— `Face`+`Timing` 小写后拼成 `facetiming`，第 8 位是 `i` 而不是 `e`，`facetime` 根本不是它的子串。断言里要用实际词形（`FaceTiming`），或换一个不含内部大写的锚点（如 `my dog`）。同理警惕 `Wi-Fi`、`YouTube`。
- 再加残留关键词扫描（修正前的错误拼写应全部清零）
- **写完 EN_FIX 必须回原 dump 逐条核对 key**：一句话可能跨条目，凭记忆填号极易错一位。
  > 实例：`Assiette Champenoise` 该写 **#514**，曾误写成 #513；`Baroque population`→`Barolo production` 该改 **#620（一整句）+ #622**，而 **#621 是另一句**。
  > **v2.3 起更省事**：EN_FIX 直接写 `(原文, 修正)` 元组，key 一偏就当场报错，不必靠人眼比对。
- **先搜全出现点再动笔（配合铁律 15）**：用 `dump_srt.py --find` 把**全部**出现点列成清单再逐点写。
  > 实例：`#130 Kalishan blonde`（Galician blonde 的第 2 种错拼）首版漏改、`#224 Pinoblanc` 漏改，均被 `--resid` 当场拦截；MUDEC 一个餐厅名有 **3 种错拼**（Udech / Moudek / mood up），Galician 有 2 种。
- **断言词选「公共前缀」避开词尾差异**：要同时断言 `Carpionis` 和 `Carpione` 时用 `Carpion`——`carpioni` 匹配不到 `carpione`（结尾 i≠e），`carpione` 也匹配不到 `Carpionis`。
- **untouched 断言是大小写敏感的**：`frag in t[k]` 直接比较，句首大写的原文要按实际词形写。
- 若确认错位：**从原始备份重建原文字典**再重跑，不能用已覆盖的文件反推

### 铁律12　中文标点规范
- **禁止全角冒号 `：`**：改写为句号衔接（`另一个事实：你可以在…` → `另一个事实。你可以在…`）
- **禁止破折号 `——`**：按上下文补逗号或句号
- 写文件前统一断言：`all('：' not in v and '——' not in v for v in ZH.values())`
- 允许保留：外文专名的括注、书名号《》、引号「」

### 铁律13　EN_FIX 是整条替换，改写时切勿只写半句
`EN_FIX[k]` 会覆盖该条**全部**文本。只写前半句会丢句尾——一旦丢句尾，漂移告警（`en<=3词配zh>12字`）会立刻报警，**这是有效兜底，一出现就必须回溯**。
v2.3 起模板还会做**漏词审计**：修正后比原文少 3 词以上直接拦下（确实该变短的条目号写进 `CONFIG["shrink_ok"]`）。

### 铁律14　政治地理表述（固定规则，直接执行，无需询问）
| 英文 | 中文 |
|---|---|
| Hong Kong | Hong Kong, China |
| Macao / Macau | Macao, China |
| Taiwan | Taiwan, China |
| 香港 | 中国香港 |
| 澳门 | 中国澳门 |
| 台湾 | 中国台湾 |

### 铁律15　同一专名多种错拼，必须逐点全改
同一个正确名称往往被 ASR 拼成**好几个不同的错法**，只改其中一两种就会漏。
> 实例：`Omarchy`（DHH 的 Arch 系发行版）在 292 条里出现 10 处，错拼有 **4 种**——`Olmarky` / `O-Markey` / `O-Marky` / `Omarky`。
> 极端案例（2026-11 三单）：`Fontainebleau` 被拆成 **`fountain blue` / `fountain Blue`** 两种写法共 **15 处**；`Herald Square` 在同一部片里 **7 处拼成 `Harold`、2 处拼对**；`MSI EdgeMesa N AI+` 出现 **`Edge Mesa NAI Plus` / `Mesa Edge Plus AI` / `N1`+`X` 拆条** 四种形态。

**做法（强制）**：
1. 先对正确名做**四层模糊搜索**：`python scripts/dump_srt.py "<视频名>.srt" --find "正确名"`
2. 逐点写进 `EN_FIX`（同一个正确名 → 多个 key）
3. 把**每一种错误拼法**都放进 `--resid` 残留词表做二次兜底
4. 再把该正确名放进 `proper_nouns` 断言
> 同类案例：`HyperOS`（错拼 `Hyper OS` / `hyper S4`）、`Loews`（`Lowes` / `the lowest hotel`）、`Barbaresco` / `Barolo` / `wine list` / `truffle` 均属同音多拼家族。

### 铁律16　碎条、跨条目承接、专名被切成两半
部分视频（尤其酒店测评 vlog）的 ASR 是**1–2 秒一条的碎条**，一句话常被切在**相邻两条**上。
- **改 EN 必须按条目保留断句、不得合并**。例：#51 `…curtain` / #52 `controls.`
- **跨条目承接的词组必须两条同改**，否则修不干净、也不触发漂移告警。
  > #164 `while I` / #165 `opened the soap.`；Pura X View #145 `knows how` + #146 `battery is work` → 一起改成 `knows how` + `batteries work`
- **专名骑在条界上**（2026-11 高频）：
  | 跨条 | 原样 | 改法 |
  |---|---|---|
  | #8 + #9 | `…including New` / `and Square,` | `Union` + `Square`（Union 被听成 New + and） |
  | #124 + #125 | `…that same art` / `deco feel` | `Art` / `Deco` |
  | #151 + #152 | `…that is the cafe's` / `a metacano` | `Café Americano`（#151 收全专名，#152 从 so 起） |
  | #231 + #232 | `…with the fountain` / `blue signature logo` | `Fontainebleau` |
  | #221 + #222 | `…onto your nightly` / `raid` | `rate` |
  这类只有 `--find` 的**跨条拼接检索**才找得到，单看每一条都对不上。
- 碎条场景下中文也容易"一段话拆两半"，逐条对应翻译、不要强凑通顺而挪用邻条内容

### 铁律17　check 文件全量逐条复读，等差移位只是第一步
中文手写字典的漂移修完**不等于**对齐了：
- **整段等差移位（ZH[k]=trans(EN k+N)）用脚本移位修复后，流水句区域仍会残留「半条错位」**——原作者在某处把两句合并成一条（少写一条译文），等差只在段内成立。实例：NZ #75-79、米兰 #422-439。
- **漂移告警（ew/zc 比例失衡）只能暴露部分错位**，短句互撞、语义通顺的错位它查不出来。
- **唯一可靠闭环：生成并排 check 文件，从头到尾逐条读到最后一行**（宁可分 3-4 次读完）。
  ```
  python scripts/process_template.py --check     # → check.txt
  ```
- 发现残留错位就用「小补丁脚本 + 硬断言（修复后关键条目的期望译文写进 assert）」修，再重新生成 check 复读。
- 补丁脚本里的断言也要**先算准移位后的期望值**再写——断言本身写错会假报成功。

### 铁律18　动手前先用硬解析脚本核实条数
- dump 导出工具**可能漏掉最后一条**（实例：684 条的 SRT 只 dump 出 683 条，末条 `You can say I can't see.` 差点整条漏翻）。
- 条数必须以**正则硬解析**的结果为准（`len(PAT.finditer(raw))`）。`dump_srt.py --stats` 已内置「尾块残留」检查：末尾若有没被解析的内容会直接告警。
- 末条常是时间码短、文本怪异的孤条，翻译时按「存疑不臆造」处理，中文用中性表述带过。

### 铁律19　DY_OVR 的 key 必须逐条核对原文
- 合规落点 key **不能凭印象写**：实例 SteamOS 项目 DY_OVR 初版整体偏移 -11（写成 61/85/86，实为 72/107/108），verify 的「合规版无禁用词残留」直接报出真实落点 72/107/108。
- 正确做法：`python scripts/process_template.py --keys` 把每条 EN + ZH 打出来，确认禁用词真的落在那一行；跨条句（一句拆成 2-3 条）尤其容易错行。
- verify 报禁用词残留时，输出的就是**真实落点 key**，直接按它改，不要再去猜。
- 反向自检：合规版与正常版差异条目数应 = DY_OVR 设计的条数；多出来的说明有落点没覆盖到。

### 铁律20　resid 里绝不能出现专名的「修正后形态」
`resid` 是「ASR 原始错误形态」的黑名单，必须能被修正后文本躲开。凡是专名修正后形态本身是合法文本的，写进 resid 就会假告警。
**v2.3 起 `process_template.py` 会在写盘前自动做一次预检**（在修正后正文上扫一遍），命中即报「以下 resid 会命中修正后的正文」并要求改。大小写敏感、不含逗号这两条铁律继续有效。

### 铁律21　处理脚本必须从原始备份读取（幂等可重复）
run 重跑时若直接读源文件，而源文件已被上一轮 run 覆盖成修正版，`EN_FIX` 的 old 断言会全量失配、并报出大量「new 与原文相同」假错误。
**做法：脚本开头固定 `src = 备份 if exists else 源路径`，修正后写回主路径。** `process_template.py` v2 已内置：首次运行自动备份到**脚本同目录**（即 `_tmp_<项目>/`），之后永远读备份。原始备份随临时目录一起删，视频目录不留。

### 铁律22　非英文主文件（日文等）的适配要点
1. **漂移公式失效**：`ew=len(EN.split())` 对无空格语言全量误报。改用 `jlen=非ASCII字符数`（拉丁专名不计）+ `zc=中文字符数`，阈值 `(jlen>=10 and zc<=3) or (jlen<=3 and zc>=15) or zc==0`；专名占主体的短条人工核对后进白名单。
2. **old 断言写法**：叠字形态不定（頃々/頃頃）用单字断言；活用形差异（挟み込む vs 挟み込んで）取公共前缀断言。
3. **碎条重复开头**：口语 ASR 大量「前条重复开头」碎条，整条替换的 new 最易把相邻条内容并进来——预检 old 未命中是唯一的暴露窗口。
4. **翻译按正确语义翻**：源文件中的同音字错误（証明→照明）中文直接翻对，不翻错字；纯型号条中文必须补描述词防纯拉丁行。
5. **verify 需本地适配版**：主验证脚本按英文设计，非英文项目另写本地 verify（保留全部检查项 + 新公式）。

### 铁律23　第二路 ASR 先判「同源 / 互补 / 主轨缺词」，拉不到就止损
拿到另一份字幕不等于拿到答案，**先判它属于哪种**：

| 结局 | 特征 | 怎么用 |
|---|---|---|
| **同源** | 与主轨**逐字相同**，连错误都一样 | 不能当独立证据，只能用来补断句、标点 |
| **互补** | 独立转写，错处不同 | 价值最高，两路一致处直接定案 |
| **主轨缺词** | 官方轨专名准，主轨漏词/断句更碎 | 用官方轨校专名，**不新增条目** |

> 实例：Versace 大宅那期两份逐字相同（同源），只能补标点；Rules 那期是独立 ASR（互补），一次定案 6 处；香港环球资源展主轨缺词但官方轨专名准，只借专名。

**止损规则**：代理 502 / SSL 中断 / ytsearch 返回的片长接近但内容不符（见 6.9），**试三次即停**，改走 6.8 的 WebSearch 考据，并在交付时明说「本片未取得第二路 ASR」。不要因为"已经花了很多时间"就硬套一份不相干的字幕。

### 铁律24　中间产物统一关进 `_tmp_<项目>/`，交付后整体删除
用户明确要求：**视频目录最终只有「原视频 + 用户原有素材 + 三份 SRT」**。
- 开工就在项目根建 `_tmp_<项目>/`，所有中间产物都放里面：
  `<视频名>_en_original.srt`、`fix.py`、`zh_part*.py`、`proc.py`、`check.txt`、`ref.*.vtt`、`dump.txt`
- 交付前 `shutil.rmtree('_tmp_<项目>')`，然后 `os.listdir` 复核目录
- 判据：跑一遍目录列表，**任何不认识的 `.srt` / `.py` / `.txt` / `.vtt` 都是漏删**
- 历史踩坑：把 `_en_original.srt` 留在视频目录，视觉上与成品混在一起，用户要求清理时容易误删成品或漏删备份
- 提醒：用户自己的工具可能生成过 `bilingual_merged_debug.srt` 这类文件，**不是本流程产生的不要擅自删**

### 铁律25　不要在命令行里写带正则的 Python
`python -c "...\d..."` 或 heredoc 里，`\d`、`\.`、`\s` 的反斜杠会被 shell 吃掉一层，正则退化成 `d`、`.`、`s`，**解析出 0 条却不报错**。
> 症状：`len(ms) == 0`；或"解析出 3 个词"但整条有 30 个词；或 dump 出来全是碎片。
> 做法：**一律用 Write 落成 `.py` 文件再 `python xxx.py`**。只要命令里出现 `\d`、`\.`，立刻改成写文件。
> 另一条：`python -c` 里打印中文，Windows 上要先 `sys.stdout.reconfigure(encoding='utf-8')`，否则 GBK 编码报 `UnicodeEncodeError`。

### 铁律26　数字、单位、型号的粘连必须逐条拆开核对
ASR 最爱在数字上出错，而且错得"看起来很正常"：
| 症状 | 正确 | 类型 |
|---|---|---|
| `Llama 3.18B` | **Llama 3.1 8B** | 版本号与参数量粘成小数 |
| `The Nvidia 40-Watt unit` | **140-watt** | 首位数字被吞 |
| `250099` | **2,509** | 两个数字粘在一起 |
| `9600 Megatrans first` | **9600 MT/s** | 单位被听成词 |
| `627 watt` | **67 watt** | 多一位少一位 |
| `If 700,000 vehicles` | **Over 700,000 vehicles** | 介词误听成数字前缀 |

**做法**：参数型视频（手机 / 迷你主机 / 显卡 / 相机）**先查官网规格页锁定数字**，再回头对字幕；能用规格反算的必须反算（见 6.10）。

### 铁律27　幻听整句不删条（条数是骨架）
ASR 常在安静段落补出**根本不存在的话**：`Thanks for watching this video.` / `Please subscribe.` / `Thanks for watching.`
- 条数必须与时间码骨架一致，**不许删条目**（删一条后面全错位、时间码全乱）
- 按原样翻译，**在交付回复里单独说明位置与判断依据**，让用户决定要不要并进邻条
- 判据：前后句语义连贯顺畅，只有这一句突然跳题；且它出现在片中某处而不是结尾

### 铁律28　产品名 / 游戏名 / 型号靠反查库，不靠音近
有些错根本不是"音近"，光听音永远猜不出来，必须查库：
| ASR | 正确 | 靠什么锁定 |
|---|---|---|
| `Sports Horizon 6` | **Forza Horizon 6** | 游戏库反查（"Horizon" 唯一，前缀完全不同） |
| `Edge Mesa NAI Plus` | **MSI EdgeMesa N AI+** | 官网产品页 |
| `Trasor Tower` | **Trésor Tower** | 酒店官网（带重音符 é） |
| `Hacacon` | **Hakkasan** | 米其林餐厅名录 |
| `Rouse` | **Rao's** | 酒店餐厅列表（撇号不能省） |
| `cleavelander` | **Clevelander** | 酒店官网 |
| `Quinn` | **Qwen** | 模型名（通义千问） |
| `Flux2` / `comfy UI` / `ML Perf` | **FLUX.2** / **ComfyUI** / **MLPerf** | 官方写法（大小写、空格、点号） |

**做法**：先把「品牌 + 品类 + 年份」丢进 WebSearch 拿到官方写法，再回字幕逐点改。大小写、空格、连字符、重音符、撇号一律按官方，不做"看起来更顺"的改动。

---

## 4. 四轮验证（脚本会全自动跑）

| 轮次 | 检查内容 | 通过标准 |
|---|---|---|
| 第一轮 | 英文 ASR 修正 + 残留关键词扫描 | 残留 = 0 |
| 第二轮 | 中文 100% 覆盖 + 标点合规 | 条数 = N，`：` = 0，`——` = 0 |
| 第三轮 | 纯英文行（无中文字符）扫描 | = 0 |
| 第四轮 | 条目数 / 时间码 / 内容对齐全量比对 | 时间码 diff = 0，漂移 = 0 |

v3 起还硬检查：**BOM 恰好 1 个**、**全 CRLF**、**条目间空行 = N−1**、**解析无残留尾块**。

命令：
```
python scripts/verify_srt.py "<path/to/视频名>.srt"
python scripts/verify_srt.py --en a.srt --zh b.srt --dy c.srt
python scripts/verify_srt.py "<path/to/视频名>.srt" --resid "Sally,mission star,Instead 360"
python scripts/verify_srt.py "<path/to/视频名>.srt" --stats
```

---

## 5. 抖音/国内自媒体合规替换（翻译时同步执行）

| 类型 | 处理 |
|---|---|
| 境外平台名 | YouTube→视频平台、Netflix→视频平台、Instagram→社交应用、Facebook→社交应用、TikTok→短视频平台、Twitter/X→社交平台、WhatsApp→聊天软件、Chrome→浏览器、Google Play→应用商店、Booking.com→旅游网站 |
| 订阅/频道 | 订阅→关注、频道→主页/账号、Newsletter→推送 |
| 商业推广 | 送测→自购、赞助→合作伙伴/自费、广告→个人分享/推广内容 |
| 导流 | 简介链接、个人网站、二维码、邮件订阅 → 删除或泛化 |
| 物流/品牌 | FedEx→国际物流、境外店铺名→海淘渠道 |

**保留**：时间码、条目数完全不变；`中国香港` 这类正确表述不改。
完整替换表见 `references/douyin_compliance.md`。

> ⚠️ **语境盲区**：验证器的禁用词表对 `订阅 / 频道 / 赞助 / 广告 / 链接` 做**全文匹配**，
> **描述性、非推广**的用词也会 FAIL。合规版里这些词一个都不能留，用中性同义词替换（不删句子）：
> 赞助商→**合作伙伴**、广告→**推广内容**、订阅（制）→**关注 / 按月收费**、频道→**账号**。
> 别指望"这句不是在打广告所以能留"——扫描器不看上下文。

> ⚠️ **禁用词可能落在跨条句子的前一条上**：
> 一句话被 ASR 切成两条（如 `#339 And that was one of the shortest scenes,` + `#340 I think we've ever done on the channel`），
> 「频道」二字实际落在 **#339 的译文里**，只覆盖 #340 无效。做法：写 DY_OVR 前先用
> `process_template.py --keys` 把 ZH 全文过一遍，**按实际落点逐条覆盖**，跨条句子两条同改。

> ⚠️ **`description` 也要换**：`links in the description` 里的 description 在中文语境就是「简介」，
> 「简介」同样在禁用词边缘。稳妥写法：`官网地址我放在下方文字说明里`。

---

## 6. 专名考据方法（不确定就查，别猜）

0. **"存疑不臆造"总原则**：查不到的专名、听不懂的口语乱句，**宁可保留原文也不猜**；
   中文里用中性表述带过即可。这些存疑项**不得放进残留词表**，否则会自造假告警。
   > 实例：Xiaomi 18 Fold 的 `#70 what are the bulbs you are not`、Linux 项目的 `#260 Qwen 3.8`、GTA6 的 `#312 Not alone.`，均保留原样。

1. **优先用"菜品描述型"文章，不要只查菜单**。食评/媒体的做法描述会同时给出食材与工艺，一次能确认多处译法。
   > 实例：用 reportergourmet 对「绿胡椒菲力改比目鱼版」的描述，一次确认 `sole`／绿胡椒／鳀鱼三处译法。
2. **地方特产查产地方言/官方词条**。
   > 实例：`spaccasassi` = `paccasassi` = 海茴香（*Crithmum maritimum*，Conero 特产），故 ASR 把 `fennel` 听成 `funnel`。
3. **人名/店名查官网或权威榜单**（Michelin / 50 Best / 官网团队页），确认拼写与职务；**产品/参数查官方发布页**。
   > 实例：小米 18 Fold 一次 WebSearch 锁定「中国 2026-09-07 首发、外屏 5.38" 4000 nits、玄戒 XRing O3 三纳米、6000mAh + 67W + 50W」。
4. 查完把结论写进 `references/asr_patterns.md`，下次直接复用。

### 6.5 用"第二份 ASR 字幕"做交叉校对（强烈推荐，尤其是专名密集的视频）
同一段音频找**另一个 ASR 转写源**，逐段对照。两个 ASR 独立出错，重合处基本可信，分歧处一眼暴露。

- 找法：搜 `视频标题 + transcript`，常见站点如 `youtubetotranscript.com`（把视频 ID 拼成 `.../transcript?v=<videoId>`）。
- **更省事（本机 yt-dlp + 有外网）**：
  ```
  yt-dlp "ytsearch6:视频标题" --skip-download --print "%(id)s|%(channel)s|%(title)s"           # 定位视频
  yt-dlp --skip-download --write-auto-subs --sub-langs en-orig --sub-format vtt \
         -o _tmp_<项目>/ref.%(ext)s "https://www.youtube.com/watch?v=<videoId>"                # 拉字幕
  ```
  `--sub-langs en` 常报 HTTP 429，改用 **en-orig** 成功率更高。拿到 VTT 后本地去时间码、去 `<[^>]+>` 内联标签、去掉滚动重复行。
- **先按铁律 23 判结局**（同源 / 互补 / 主轨缺词），再决定能借多少。

**词级 cue 对齐法（最精确，v2.3 新增）**
官方自动字幕的 VTT 带 `<HH:MM:SS.mmm><c>word</c>` 词级时间戳。不要"整段文本肉眼比对"，而是：
1. 解析出 `(start, end, word)` 列表
2. 对本地 SRT 的每条 `[t1, t2]`，取落在区间内的词拼成一句
3. 得到「本地第 k 条 ↔ 官方第 k 段」的 **1:1 对照**，再逐条并排看

这样完全不受两份字幕断句不同、条数不同的干扰。实例：NYC 步行化 106 条与官方轨 1:1 对得上，一次定案 `seedy underbelly`、`well-lit streets`、`or BID`、`opted for…and tables`、`curbs and crosswalks`、`woonerf` 六处。

- **官方字幕也是 ASR，不是标准答案**：两路都对才改；只有一路支持时保留**主 ASR**。
- **两个 ASR 都给出同一个"错"结果时不要盲信**：两份都把 `Interlaken` 转成 `interlocking`，此时靠常识与地名库判断。
- 第二份 ASR 的**断句与条目切分不同**，只用于比对语义，绝不照搬它的分条。
- 用第二份 ASR 改写的条目，仍要在交付报告里列入"不确定项"，注明依据。

### 6.6 品牌名整条纯拉丁的处理
赞助商品牌独占一条时（如 `Holafly eSIM.`），中文必须补括注，否则触发"纯拉丁行 = 0"和漂移双重告警：
`Holafly eSIM.` → **`Holafly eSIM（旅行联网服务）。`**；合规版整体泛化（`一款 eSIM。`）。

### 6.7 「机翻轨」的处理（源文件不是 ASR 英文，而是自动翻译轨）
西语/其它语种视频常带一条**自动翻译的英文轨**。这类文件的错误不是音近错字，而是**系统性病句**：
- **重复词**：`...and applications and applications.` → 删重复
- **错位插入 / 多余尾巴**：`place behind the element in question and in question`
- **品牌被拆成两词**：`Harmony OS` → **HarmonyOS**（全篇统一，须进 EN_FIX 逐条替换）
- **机翻式硬伤**：`they are more than standardized reality there` → `they are already standard reality over there`
- 语言混用时要顺手归一：`Xiaoyi`（小艺）/ `Celia`（海外名）同指一个助手，中文用「小艺」
- 存疑的口语称呼（如 `hey Jay`）**宁可不改英文**，中文按招呼语处理，并在交付表里列为存疑项

### 6.8 动手前先做一次 WebSearch（餐饮/科技/系统类尤其重要）
**不要一上来就逐条猜音近词。** 先用一次搜索把"正确词表"锁定，再回头对 ASR 做纠错：
- **频道/博主背景也是考据点**：博主的口头禅、他公开 praise 过的餐厅/产品，常能一锤定音。
  > 实例（英国牛排馆）：确认博主是 Gary Eats、其心中最佳餐厅是 Opheem（伯明翰米二），据此定案 `O'Feam`→**Opheem**。
- **餐饮探店**：搜「餐厅名 + chef + michelin」；再搜招牌菜做法，确认食材译名。
  > 实例（Piazza Duomo）：确认「阿尔巴、Chef Enrico Crippa、米其林三星、朗盖 Langhe」；白松露经典菜 = 土豆泥 + **正山小种 Lapsang Souchong** + 鹌鹑蛋（一举确认 `poteto`、`lap sansuchon`）。
- **科技/系统类**：搜「产品名 + specs / release」，确认型号与参数。
- **酒店/文旅类**：搜「酒店名 + rooms + restaurants + opened」，一次锁定房数、餐厅名、开业年份，用来反证 ASR 的专名与数字。
  > 实例（GTA6 迈阿密）：查到 Fontainebleau「1,504 间房、Lapis Spa 40,000 平方英尺、Hakkasan + Scarpetta、Trésor Tower 2005 年建、1954 年开业」，字幕里的数字全部对得上，于是只改专名不动数字。
- 搜索结论**务必写回 `references/asr_patterns.md`**。

### 6.9 yt-dlp 交叉校对「非同源」硬判定
用标题词 / 独特句 / 专名组合反复 ytsearch 仍找不到原视频时，下载到时长接近但内容完全不同的结果，**必须判非同源并放弃该路证据**，不许因为时长对得上就硬套官方字幕。
硬判标准：抽查任意 3 句独特内容，能对上一句才算同源。
放弃后改走 6.8 的 WebSearch 考据 + 官方资料，并在交付时把「未取得第二份 ASR」列入不确定项。

### 6.10 参数型视频的反算校验（v2.3 新增）
讲硬件参数的片子（手机/迷你主机/显卡/相机），ASR 错数字最隐蔽——`140` 听成 `40`、`3.1 8B` 粘成 `3.18B`，读起来毫无破绽。**用规格之间的物理关系反算**是最硬的判据：
- **显存/内存带宽** = 位宽(bit) × 速率(MT/s) ÷ 8
  > 实例：MSI N1X 的 256-bit LPDDR5X-9600 → 256 × 9600 ÷ 8 = **307 GB/s**，字幕写 300GB/s ✅ 说明 `9600 Megatrans first` 确实是 MT/s
- **充电功率** = 电压 × 电流（`67W = 20V×3.35A`）
- **分辨率 × 刷新率** 不能超过接口带宽
- **参数量与显存**：`8B` 的模型量化后约 5–6GB，若字幕说"2GB 显存跑 8B"就要怀疑

反算对得上 → 数字可信、可以定案；对不上 → 说明数字被听错，回官网再查。**别跳过这一步，它是唯一能自动发现数字错误的办法。**

---

## 7. 交付话术与结果表模板

```
**<项目名>（N 条）已完成交付** ✅

三份文件都在原视频目录，文件名与视频同名（播放器可直接加载）：

| 文件 | 说明 |
|---|---|
| `….srt` | 英文修正版，**已覆盖原文件**（X 处 ASR 修正） |
| `…_zh.srt` | 中文正常版 |
| `…_zh_douyin.srt` | 抖音合规版（Y 条覆盖） |

**四轮验证结果**

| 检查项 | 结果 |
|---|---|
| 条数 / key 连续 | N = N = N，1..N 连续 ✅ |
| 时间码差异 | 0 ✅ |
| 全角冒号 / 破折号 | 0 / 0 ✅ |
| 纯英文行 | 0 ✅ |
| 空条目 | 0 ✅ |
| 全量漂移 mismatch | 0 ✅ |
| ASR 残留关键词 | K 项全部清零 ✅ |
| BOM / 换行 / 空行 | 单 BOM + CRLF，N−1 组条目间空行 ✅ |
| 合规版禁用词残留 | 0 ✅ |

**本轮关键考据**：…（列 3–5 条最有价值的专名/术语判定，写清依据）

**存疑项与推断项**（没有第二路可证，按合理推断处理，请用户留意）：
- #xx `原文` → `推断`，依据是…

**保留未改的**：…（存疑不臆造的那些，说明为什么不动）

**合规版改动**：…（改了几条、改了什么、为什么）

**收尾**：临时目录（原文备份、修正脚本、分片译文、复读文件）已整体删除，
目录里只剩 mp4 / 素材 / 三份 SRT；新经验写进 `references/asr_patterns.md` 第 N 节。
```

若本片**没拿到第二路 ASR**，必须在结果表下面单独写一句：
> 本片没有抓到用于交叉校对的第二路字幕（原因：代理 502 / 未找到同源视频），改走官方资料考据，关键参数已用规格反算验证。

---

## 8. 环境与工程注意事项

- **一律用 Python 做文件读写与检索**，不要把脚本输出管进 `tail` / `head`：部分沙箱 shell 缺少 `ls` / `grep` / `tail` / `dirname`，会直接报 `command not found` 并让整条命令 exit 127，而**脚本本身可能已经正常执行**，容易误判。
- **Windows 上打印中文**：`python -c` 里先 `sys.stdout.reconfigure(encoding='utf-8')`，否则 GBK 编码报 `UnicodeEncodeError`。
- 路径含空格、`:`、`｜`（全角竖线）、`：`（全角冒号）、非 ASCII 时，Python 里用 **raw string**；含 `’`、`£`、`–` 等特殊字符时，**最稳的做法是根本不手写路径**：用目录名关键词 hint 在父目录下动态定位（`os.listdir` + 子串匹配 + 取 `.srt` 后缀），彻底绕开转义问题。
  > 实例：`Why NYC Removed Cars From Its Busiest Streets ｜ Walking Tour ｜ Architectural Digest` 目录名里有 4 个全角竖线，手写路径必错。
- **`Edit` 偶尔返回 success 但没真正写入**（文件被占用）。改完**必须用 Python 复读/grep 确认**，再去执行脚本。
- **删除临时文件也用 Python**（`shutil.rmtree` / `os.remove`），不要依赖 shell 的 `rm`（部分环境 shim 失效）。
- **`python -c` / heredoc 里不要写正则**（反斜杠被 shell 吃掉一层，见铁律 25）。
- **`'\n'.replace` 别写反**：要 `replace('\n', '\r\n')`；写成 `replace('\r\n', '\r\n')` 是空操作，输出全是 LF，会被 verify 的「全 CRLF」拦下。
- Python 字典值里避免出现 ASCII 双引号，中文句内引号用 `「」`，否则字符串会提前截断。
- **字典匹配策略**：优先完整句精确匹配，未命中再降级为 `if kw.lower() in text.lower()` 模糊匹配；重复 key 用 `ENTRY_OVERRIDES` 按索引覆盖；大字典抽检首/中/尾。
- **`os.listdir` 顺序不稳**，遍历目录一律先 `sorted()`，否则两次运行的输出无法比对。
- 大文件（>500 条）先分片写中文（每片 ≤350 条），单片文件更易维护与复查。
- 全程用简体中文与用户沟通；结论优先给**结构化表格 + ✅ 状态**。

---

## 9. 自检清单（交付前逐项打勾）

- [ ] 三份文件已生成，英文版已覆盖原文件
- [ ] N 条全部有中文，无空值
- [ ] 时间码三份完全一致
- [ ] `：` = 0，`——` = 0
- [ ] 纯英文行 = 0
- [ ] 漂移 mismatch = 0（含纯数字行、专名密集行已补中文）
- [ ] 专名断言全部通过（含大小写、key 已用 `(old,new)` 元组或 dump 核对）
- [ ] 同一专名的所有错拼变体已逐点改净（`--find` 四层搜过，含**跨条拼接**）
- [ ] 数字/单位/型号已逐条核对，参数型视频做过反算（铁律 26 / 6.10）
- [ ] 幻听整句已识别、未删条、已在交付说明里列出（铁律 27）
- [ ] dump 行数与硬解析条数一致（`--stats` 尾块无残留）
- [ ] check 文件已全量逐条复读（等差移位后无残留半条错位）
- [ ] 残留 ASR 关键词 = 0（且无自造假告警）
- [ ] 合规版无境外平台名/导流链接，且**无「订阅/频道/赞助/广告/链接」任何残留（含描述性用法）**
- [ ] 单 BOM + CRLF + **条目间空行 = N−1**
- [ ] 视频目录只剩三份 SRT（中间产物已整体删除）
- [ ] 新 ASR 模式已写回 `references/asr_patterns.md`
