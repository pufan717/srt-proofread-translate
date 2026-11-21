#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SRT 四轮验证（通用版 v3）—— 只依赖 Python 3 标准库

用法：
  1) 自动推导（推荐，文件名同基底）
     python verify_srt.py "D:\\path\\视频名.srt"
     会自动去找 同目录\\视频名_zh.srt 和 视频名_zh_douyin.srt

  2) 显式指定
     python verify_srt.py --en a.srt --zh b.srt --dy c.srt

  3) 只验英文修正
     python verify_srt.py --en a.srt

  4) 附加残留关键词扫描（逗号分隔，默认词边界 + 大小写敏感）
     python verify_srt.py "视频名.srt" --resid "Sally,mission star,Instead 360"

  5) 加统计（条数 / 时长 / 平均字数）
     python verify_srt.py "视频名.srt" --stats

v3 相对 v2 新增的检查：
  · 条目之间是否有空行（缺空行会让 VideoSubtitleTool 把整份当成 1 条，历史上真实事故）
  · 双 BOM / 条目文本内部换行 / 中文重复标点
  · 时间码行尾附加设置（align:start 之类）可正确解析
  · 解析后残留未识别尾块的告警（防漏最后一条）

退出码：0 = 全部通过；1 = 存在失败项（详见输出 FAIL 行）
"""

import argparse
import os
import re
import sys

# 兼容：空行分隔 / 无空行分隔；毫秒分隔符 , 与 .；时间码行尾可带 align:start 之类附加设置
PAT = re.compile(
    r'^(\d+)[ \t]*\n'
    r'(\d{2}:\d{2}:\d{2}[,.]\d{3}[ \t]*-->[ \t]*\d{2}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n'
    r'(.*?)'
    r'(?=\n\d+[ \t]*\n\d{2}:\d{2}:\d{2}[,.]\d{3}[ \t]*-->|\n?\Z)',
    re.S | re.M,
)

# 中文里绝不合法、一定是手滑的重复标点（`……` 是合法的，不在表内）
DUP_PUNCT = re.compile(r'([，。、；！？])\1')


# ---------- 基础工具 ----------

def read_raw(path):
    with open(path, 'rb') as f:
        b = f.read()
    bom = b.count(b'\xef\xbb\xbf')
    crlf = b.count(b'\r\n')
    lf = b.count(b'\n')
    if lf == 0:
        raise SystemExit('文件为空或换行异常: %s' % path)
    raw = b.decode('utf-8-sig')          # 自动剥掉所有 BOM
    raw = raw.replace('\r\n', '\n')
    return dict(bytes=b, bom=bom, crlf=crlf, lf=lf, raw=raw,
                blanks=raw.count('\n\n'))


def parse(raw):
    ents, order, last_end = {}, [], 0
    for m in PAT.finditer(raw):
        k = int(m.group(1))
        ents[k] = (m.group(2), m.group(3).strip())
        order.append(k)
        last_end = m.end()
    tail = raw[last_end:].strip()
    return ents, order, tail


def cn(s):
    """中文字符数"""
    return len(re.findall(r'[\u4e00-\u9fff]', s))


def is_pure_latin(s):
    """整行无中文字符但含拉丁字母 => 需补中文"""
    return cn(s) == 0 and bool(re.search(r'[A-Za-z]', s))


def tc_seconds(tc):
    h, m, rest = tc.split(':')
    s, ms = re.split(r'[,.]', rest)
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def hms(sec):
    sec = int(round(sec))
    return '%d:%02d:%02d' % (sec // 3600, sec % 3600 // 60, sec % 60)


def word_pat(w):
    """词边界匹配：ASCII 字母数字视为词字符，避免 low 命中 below"""
    return r'(?<![A-Za-z0-9])' + re.escape(w) + r'(?![A-Za-z0-9])'


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('srt', nargs='?', help='英文 SRT 路径（自动推导 _zh / _zh_douyin）')
    ap.add_argument('--en', help='英文 SRT 路径')
    ap.add_argument('--zh', help='中文正常版路径')
    ap.add_argument('--dy', help='中文合规版路径')
    ap.add_argument('--resid', default='', help='残留关键词，逗号分隔（默认大小写敏感）')
    ap.add_argument('--resid-ci', action='store_true',
                    help='残留词改为大小写不敏感匹配。慎用，会命中自己写对的专名（如 four seasons 命中 Four Seasons）')
    ap.add_argument('-n', '--n', type=int, default=0, help='期望条数（可选，默认取英文条数）')
    ap.add_argument('--stats', action='store_true', help='额外打印条数/时长/平均字数')
    args = ap.parse_args()

    en_path = args.en or args.srt
    if not en_path:
        ap.print_help()
        return 2

    base = en_path[:-4] if en_path.lower().endswith('.srt') else en_path
    zh_path = args.zh or (base + '_zh.srt')
    dy_path = args.dy or (base + '_zh_douyin.srt')

    fails, warns = [], []

    def ok(cond, label, detail=''):
        mark = 'PASS' if cond else 'FAIL'
        print('  [%s] %-30s %s' % (mark, label, detail))
        if not cond:
            fails.append(label)
        return cond

    def warn(label, detail=''):
        print('  [WARN] %-30s %s' % (label, detail))
        warns.append('%s %s' % (label, detail))

    # ===== 载入 =====
    print('主文件 : %s' % en_path)
    E = read_raw(en_path)
    EN, order, tail = parse(E['raw'])
    N = args.n or len(EN)
    print('中文版 : %s  (存在=%s)' % (zh_path, os.path.exists(zh_path)))
    print('合规版 : %s  (存在=%s)' % (dy_path, os.path.exists(dy_path)))

    Z = read_raw(zh_path) if os.path.exists(zh_path) else None
    D = read_raw(dy_path) if os.path.exists(dy_path) else None
    ZH = parse(Z['raw'])[0] if Z else None
    DY = parse(D['raw'])[0] if D else None

    # ===== 1. 条数 / key 连续 / 编码 / 空行 =====
    print('\n=== 1. 条数 / key 连续 / 编码 / 空行 ===')
    ok(len(EN) == N, '英文条数', '%d (期望 %d)' % (len(EN), N))
    ok(sorted(EN) == list(range(1, N + 1)), '英文 key 连续', '1..%d' % N)
    if tail:
        warn('解析后有未识别尾块', '%d 字符: %r' % (len(tail), tail[:40]))
    if Z:
        ok(len(ZH) == N, '中文条数', '%d' % len(ZH))
        ok(sorted(ZH) == list(range(1, N + 1)), '中文 key 连续')
    if D:
        ok(len(DY) == N, '合规条数', '%d' % len(DY))
        ok(sorted(DY) == list(range(1, N + 1)), '合规 key 连续')
    for name, R in (('EN', E), ('ZH', Z), ('DY', D)):
        if not R:
            continue
        ok(R['bom'] == 1, '%s BOM 恰好 1 个' % name, '实际 %d' % R['bom'])
        ok(R['crlf'] == R['lf'], '%s 全 CRLF' % name,
           'CRLF=%d LF=%d' % (R['crlf'], R['lf']))
        # 条目间空行：标准 SRT 必须有，否则按空行分块的工具会把整份当成 1 条
        if N > 1:
            if R['blanks'] == N - 1:
                ok(True, '%s 条目间空行' % name, '%d 组' % R['blanks'])
            elif R['blanks'] == N:
                warn('%s 末尾多一个空行' % name, '%d 组（应为 %d）' % (R['blanks'], N - 1))
            else:
                ok(False, '%s 条目间空行' % name,
                   '实际 %d，应为 %d（缺空行会让按空行分块的工具整份当 1 条）'
                   % (R['blanks'], N - 1))
        if R['bom'] == 0:
            warns.append('%s 无 BOM（部分播放器中文可能乱码）' % name)

    # ===== 2. 时间码一致性 =====
    print('\n=== 2. 时间码一致性 ===')
    diff = [i for i in range(1, N + 1) if i in EN and
            ((ZH and i in ZH and ZH[i][0] != EN[i][0]) or
             (DY and i in DY and DY[i][0] != EN[i][0]))]
    ok(not diff, '三份时间码完全一致',
       ('不一致 %d 条: %s' % (len(diff), diff[:10])) if diff else '')

    # ===== 3. 中文禁忌字符 / 空条目 / 纯拉丁行 =====
    for name, M in (('ZH', ZH), ('DY', DY)):
        if not M:
            continue
        print('\n=== 3. %s 内容合规 ===' % name)
        colon = [k for k, v in M.items() if '：' in v[1]]
        dash = [k for k, v in M.items() if '——' in v[1]]
        empty = [k for k, v in M.items() if not v[1].strip()]
        latin = [k for k, v in M.items() if is_pure_latin(v[1])]
        dup = [k for k, v in M.items() if DUP_PUNCT.search(v[1])]
        multi = [k for k, v in M.items() if '\n' in v[1]]
        ok(not colon, '无全角冒号 ：', ('%s' % colon[:10]) if colon else '')
        ok(not dash, '无破折号 ——', ('%s' % dash[:10]) if dash else '')
        ok(not empty, '无空条目', ('%s' % empty[:10]) if empty else '')
        ok(not latin, '纯拉丁行 = 0',
           ('%s' % [(k, M[k][1][:24]) for k in latin[:8]]) if latin else '')
        if dup:
            warn('%s 重复标点' % name, '%s' % [(k, M[k][1][:20]) for k in dup[:6]])
        if multi:
            warn('%s 条目内换行' % name, '%s（会影响条目间空行计数）' % multi[:6])

    # ===== 4. 全量漂移检测 =====
    if ZH:
        print('\n=== 4. 全量漂移检测（条目号对齐，非抽样）===')
        mm = []
        for i in range(1, N + 1):
            if i not in EN or i not in ZH:
                continue
            ew, zc = len(EN[i][1].split()), cn(ZH[i][1])
            if (ew > 8 and zc <= 4) or (ew <= 3 and zc > 12) or zc == 0:
                mm.append((i, ew, zc, EN[i][1][:40]))
        ok(not mm, '漂移 mismatch = 0',
           ('%d 条: %s' % (len(mm), mm[:6])) if mm else '')
        if mm:
            print('      提示：中文数字（十/三十三）与阿拉伯数字属正常差异；')
            print('            同一条中英语义完全无关才是真错位。')

    # ===== 5. 合规版差异与残留 =====
    if ZH and DY:
        print('\n=== 5. 合规版 ===')
        chg = [k for k in range(1, N + 1) if k in ZH and k in DY and ZH[k][1] != DY[k][1]]
        print('  [INFO] 合规改写条目数            %d  %s' % (len(chg), chg[:20]))
        banned = ['youtube', 'youtu', 'instagram', 'tiktok', 'facebook', 'twitter',
                  'netflix', 'amazon', 'google play', 'discord', 'substack', 'patreon',
                  'newsletter', 'http://', 'https://', 'www.', '.com',
                  '订阅', '频道', '赞助', '广告', '链接']
        hit = {}
        for t in banned:
            ks = [k for k, v in DY.items() if re.search(re.escape(t), v[1], re.I)]
            if ks:
                hit[t] = ks[:6]
        ok(not hit, '合规版无禁用词残留', ('%s' % hit) if hit else '')

    # ===== 6. 残留关键词扫描 =====
    if args.resid.strip():
        mode = '大小写不敏感' if args.resid_ci else '大小写敏感'
        print('\n=== 6. 残留关键词扫描（词边界，%s）===' % mode)
        flags = re.I if args.resid_ci else 0
        for w in [x.strip() for x in args.resid.split(',') if x.strip()]:
            ks = [k for k, v in EN.items() if re.search(word_pat(w), v[1], flags)]
            ok(not ks, '残留 "%s"' % w, ('%s' % ks[:10]) if ks else '')

    # ===== 7. 统计 =====
    if args.stats and EN:
        last = EN[max(EN)][0].split('-->')[-1].strip()
        avg_en = sum(len(v[1]) for v in EN.values()) / max(1, len(EN))
        line = '  条数 %d ｜ 时长 %s ｜ 平均每条约 %.0f 字符' % (
            N, hms(tc_seconds(last)), avg_en)
        if ZH:
            avg_zh = sum(cn(v[1]) for v in ZH.values()) / max(1, len(ZH))
            line += ' ｜ 中文平均 %.1f 字' % avg_zh
        print('\n=== 7. 统计 ===')
        print(line)

    # ===== 汇总 =====
    print('\n' + '=' * 56)
    if fails:
        print('结果：FAIL —— %d 项未通过' % len(fails))
        for f in fails:
            print('  - %s' % f)
    else:
        print('结果：ALL PASS ✅  （%d 条，三份文件对齐、标点合规、无漂移）' % N)
    if warns:
        print('提醒：')
        for w in warns:
            print('  ! %s' % w)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
