#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SRT 通读 / 检索 / 并排复读工具（通用版 v2）—— 只依赖 Python 3 标准库

为什么单独一个脚本：以前每个项目都要临时手写「导出序号|文本」「生成并排 check 文件」
「模糊搜专名出现点」三套小脚本，既费时又容易因为手写正则漏掉最后一条（真实踩坑）。
这里固化成一套，解析用与 verify_srt.py 相同的硬解析逻辑，条数以正则为准。

用法：
  python dump_srt.py "视频名.srt"                      # 全部条目：序号| 文本
  python dump_srt.py "视频名.srt" 1 120                # 只导 1–120
  python dump_srt.py "视频名.srt" --zh                 # 并排：序号 / EN| / ZH|
  python dump_srt.py "视频名.srt" --zh --out check.txt # 并排写文件
  python dump_srt.py "视频名.srt" --zh --wrap 62       # 并排 + 62 字折行
  python dump_srt.py "视频名.srt" --find "Fontainebleau"   # 检索（含音近变体 / 跨条）
  python dump_srt.py "视频名.srt" --stats              # 条数/时长/编码/空行概况
  python dump_srt.py "视频名.srt" --orig               # 改读 <base>_en_original.srt

--find 的四层匹配（这就是铁律15 说的「模糊搜索」）：
  L1 原样子串（大小写敏感）           —— 精确命中
  L2 归一化子串（忽略大小写/空格/连字符）—— 抓 `Fountain Blue` / `fountainblue`
  L3 辅音骨架（去元音后完全相同）      —— 抓 `fountain blue` ↔ `Fontainebleau`、`Lowes` ↔ `Loews`
  L4 相似度（difflib，默认 ≥0.78）     —— 兜底，会有噪声，人工判断
另外对 k 与 k+1 拼接后再搜一遍：专名被切在两条交界处时，单看每条都搜不到。

选项：
  --zh / --dy     并排中文正常版 / 合规版
  --orig          读原文备份而不是主文件
  --find KW       检索关键词
  --thresh F      L4 相似度阈值（默认 0.78）
  --no-cross      关闭跨条拼接检索
  --stats         打印概况
  --out FILE      输出到文件（默认打印到屏幕）
  --wrap N        每行最多 N 个字符（0 = 不折行，默认 0）
"""

import argparse
import os
import re
import sys
from difflib import SequenceMatcher

PAT = re.compile(
    r'^(\d+)[ \t]*\n'
    r'(\d{2}:\d{2}:\d{2}[,.]\d{3}[ \t]*-->[ \t]*\d{2}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n'
    r'(.*?)'
    r'(?=\n\d+[ \t]*\n\d{2}:\d{2}:\d{2}[,.]\d{3}[ \t]*-->|\n?\Z)',
    re.S | re.M,
)

VOWELS = re.compile(r'[aeiouy]')


def read_raw(path):
    with open(path, 'rb') as f:
        b = f.read()
    raw = b.decode('utf-8-sig').replace('\r\n', '\n')
    return dict(bytes=b, raw=raw,
                bom=b.count(b'\xef\xbb\xbf'),
                crlf=b.count(b'\r\n'),
                lf=b.count(b'\n'),
                blanks=raw.count('\n\n'))


def parse(raw):
    ents, order, last_end = {}, [], 0
    for m in PAT.finditer(raw):
        k = int(m.group(1))
        ents[k] = (m.group(2), m.group(3).strip())
        order.append(k)
        last_end = m.end()
    return ents, order, raw[last_end:].strip()


def norm(s):
    """L2：小写 + 去掉一切非字母数字/汉字"""
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', s.lower())


def skel(s):
    """L3：归一化后再去掉元音，得到辅音骨架（ASR 音近变体的骨架往往一致）"""
    return VOWELS.sub('', norm(s))


def cn(s):
    return len(re.findall(r'[\u4e00-\u9fff]', s))


def tc_seconds(tc):
    h, m, rest = tc.split(':')
    s, ms = re.split(r'[,.]', rest)
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def hms(sec):
    sec = int(round(sec))
    return '%d:%02d:%02d' % (sec // 3600, sec % 3600 // 60, sec % 60)


def wrap(text, width):
    if not width or width <= 0 or len(text) <= width:
        return text
    out, line = [], ''
    for ch in text:
        line += ch
        if len(line) >= width and ch in ' ，。、；：！？,.;:!?':
            out.append(line)
            line = ''
    if line:
        out.append(line)
    return '\n'.join(out)


def best_window(q, text, widths):
    """在 text 里找一个长度接近 len(q) 的窗口，返回最高相似度与窗口内容"""
    best, bw = 0.0, ''
    n = len(text)
    for w in widths:
        if w < 1 or w > n:
            continue
        for i in range(0, n - w + 1):
            s = text[i:i + w]
            r = SequenceMatcher(None, q, s).ratio()
            if r > best:
                best, bw = r, s
    return best, bw


def do_find(EN, order, kw, thresh, cross):
    q = kw.lower()
    nq = norm(kw)
    sq = skel(kw)

    hits = {}     # k -> [(layer, extra)]

    def add(k, layer, extra=''):
        hits.setdefault(k, []).append((layer, extra))

    for k in order:
        text = EN[k][1]
        if kw in text:
            add(k, 'L1')
            continue
        if nq and nq in norm(text):
            add(k, 'L2')
            continue
        if sq and sq in skel(text):
            add(k, 'L3')

    if cross:
        for a, b in zip(order, order[1:]):
            joined = EN[a][1] + ' ' + EN[b][1]
            if nq and nq in norm(joined) and not any(l in ('L1', 'L2') for l, _ in hits.get(a, [])) \
                    and not any(l in ('L1', 'L2') for l, _ in hits.get(b, [])):
                add(a, 'L2跨条', '#%d+#%d' % (a, b))
            elif sq and sq in skel(joined) and a not in hits and b not in hits:
                add(a, 'L3跨条', '#%d+#%d' % (a, b))

    # L4 兜底：只对没有命中的条目跑，避免噪声淹没精确结果
    widths = [max(1, len(nq) - 1), len(nq), len(nq) + 1, len(nq) + 2]
    for k in order:
        if k in hits:
            continue
        r, w = best_window(nq, norm(EN[k][1]), widths)
        if r >= thresh:
            add(k, 'L4', '%.2f' % r)

    return hits


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('srt')
    ap.add_argument('start', nargs='?', type=int, default=0)
    ap.add_argument('end', nargs='?', type=int, default=0)
    ap.add_argument('--zh', action='store_true', help='并排中文正常版')
    ap.add_argument('--dy', action='store_true', help='并排合规版')
    ap.add_argument('--orig', action='store_true', help='读 _en_original.srt')
    ap.add_argument('--find', default='', help='检索关键词')
    ap.add_argument('--thresh', type=float, default=0.78, help='L4 相似度阈值')
    ap.add_argument('--no-cross', action='store_true', help='关闭跨条拼接检索')
    ap.add_argument('--stats', action='store_true', help='打印概况')
    ap.add_argument('--out', default='', help='输出到文件')
    ap.add_argument('--wrap', type=int, default=0, help='每行最多 N 字符（0=不折行）')
    args = ap.parse_args()

    base = args.srt[:-4] if args.srt.lower().endswith('.srt') else args.srt
    if args.orig:
        # 备份可能在 SRT 同目录，也可能在临时目录（process_template 默认放脚本旁）
        name = os.path.basename(base) + '_en_original.srt'
        cands = [os.path.join(os.path.dirname(base), name),
                 os.path.join(os.getcwd(), name)]
        src = next((p for p in cands if os.path.exists(p)), cands[0])
    else:
        src = args.srt
    if not os.path.exists(src):
        raise SystemExit('❌ 找不到文件: %s' % src)
    if src != args.srt:
        print('（读取原文备份: %s）' % os.path.basename(src))

    E = read_raw(src)
    EN, order, tail = parse(E['raw'])
    N = len(EN)
    if not N:
        raise SystemExit('❌ 一条都没解析出来，检查文件格式')

    Z = D = None
    if args.zh or args.dy:
        p = base + ('_zh.srt' if args.zh else '_zh_douyin.srt')
        if not os.path.exists(p):
            raise SystemExit('❌ 找不到: %s' % p)
        M, _, _ = parse(read_raw(p)['raw'])
        if args.zh:
            Z = M
        else:
            D = M
        if len(M) != N:
            print('⚠️ 条数不一致：EN=%d，中文=%d（并排按 EN 条目号对齐）' % (N, len(M)))

    # ---- 检索 ----
    if args.find:
        hits = do_find(EN, order, args.find, args.thresh, not args.no_cross)
        print('检索 "%s"：命中 %d 条 %s' % (args.find, len(hits), sorted(hits)))
        for k in sorted(hits):
            layers = ' '.join('%s%s' % (l, ('(%s)' % e) if e else '') for l, e in hits[k])
            print('[%d] (%s) %s' % (k, layers, EN[k][1]))
        if not hits:
            print('（没命中。换个更短的词根、或降 --thresh 到 0.7 再试）')
        else:
            print('\n提示：L1/L2 可直接定案；L3 看骨架一致但需人工确认；L4 是兜底噪声，只作候选。')
        return 0

    # ---- 统计 ----
    if args.stats:
        last = EN[order[-1]][0].split('-->')[-1].strip()
        avg_en = sum(len(v[1]) for v in EN.values()) / N
        print('条数      : %d' % N)
        print('时长      : %s（末条结束）' % hms(tc_seconds(last)))
        print('平均长度  : %.0f 字符/条' % avg_en)
        print('BOM       : %d ｜ CRLF=%d LF=%d ｜ 空行组=%d（标准应为 %d）'
              % (E['bom'], E['crlf'], E['lf'], E['blanks'], max(0, N - 1)))
        shortest = sorted(EN.items(), key=lambda x: len(x[1][1].split()))[:5]
        longest = max(EN.items(), key=lambda x: len(x[1][1].split()))
        print('最短 5 条 : %s' % [(k, v[1]) for k, v in shortest])
        print('最长 1 条 : #%d (%d 词) %s'
              % (longest[0], len(longest[1][1].split()), longest[1][1][:50]))
        if tail:
            print('⚠️ 有未识别尾块（%d 字符）：%r —— 条数可能少算，需人工确认'
                  % (len(tail), tail[:60]))
        else:
            print('尾块      : 无残留（末条已完整解析）✅')
        return 0

    # ---- 区间 / 并排 ----
    lo = args.start or order[0]
    hi = args.end or order[-1]
    sel = [k for k in order if lo <= k <= hi]
    lines = []

    for k in sel:
        if Z:
            zh = Z.get(k, ('', ''))[1]
            lines.append('%d' % k)
            lines.append('EN| ' + wrap(EN[k][1], args.wrap))
            lines.append('ZH| ' + wrap(zh, args.wrap))
        elif D:
            dy = D.get(k, ('', ''))[1]
            lines.append('%d' % k)
            lines.append('EN| ' + wrap(EN[k][1], args.wrap))
            lines.append('DY| ' + wrap(dy, args.wrap))
        else:
            lines.append('[%d] %s' % (k, wrap(EN[k][1], args.wrap)))

    text = '\n'.join(lines)
    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text + '\n')
        print('已写入 %s（%d 条）' % (args.out, len(sel)))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
