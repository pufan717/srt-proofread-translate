#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SRT 处理脚本模板（通用版 v2）—— 复制本文件改名后填写，只依赖标准库

用途：一次完成「EN 修正 → 断言 → 写三份文件 → 字节自检 → 调 verify_srt.py 验证」
用法：
    python process_模板.py                 # 正式跑：断言通过才写文件
    python process_模板.py --dry-run       # 只跑断言与漂移检测，不写文件
    python process_模板.py --no-verify     # 写完不自动验证
    python process_模板.py --check         # 额外生成并排复读文件 check.txt
    python process_模板.py --dump 1-60     # 只打印修正后英文 1–60 条
    python process_模板.py --keys          # 逐条打印 EN+ZH，用于核对 DY_OVR 的 key

填写顺序（见下方 ===== 填写区 =====）：
    1) CONFIG["srt"]            —— 英文 SRT 绝对路径
    2) EN_FIX                   —— {条目号: (原文整条, 修正后整条)}，推荐写元组
    3) CONFIG["zh_parts"]       —— 中文分片文件名（每片 ≤350 条），脚本自动合并
    4) CONFIG["dy_overrides"]   —— 合规版需要改写的条目
    5) CONFIG["proper_nouns"] / ["untouched"] / ["resid"] / ["shrink_ok"] —— 断言与扫描

v2 相对 v1 新增（都是踩过坑换来的）：
    · EN_FIX 支持 (old, new) 元组，写错条目号会立刻报「原文不符」，这是防 key 偏移最硬的闸门
    · 首次运行自动把原文备份成 <base>_en_original.srt（默认放脚本同目录 = 临时目录），
      之后永远从备份读 → 脚本可反复重跑，且不会在视频目录留下多余文件
    · 漏词审计：修正后比原文少 3 词以上直接拦（除非条目号在 shrink_ok 里）
    · resid 预检：先在修正后文本上扫一遍，会自造假告警的词当场报出来
    · 写盘后做字节自检（BOM=1 / 全 CRLF / 条目间空行=N-1），不把问题留给 verify

⚠️ 本脚本会**覆盖** CONFIG["srt"] 指向的英文文件；原文已自动备份为 _en_original.srt。
"""

import os
import re
import shutil
import subprocess
import sys

# ============================ 填写区 ============================

CONFIG = {
    # 1) 英文 SRT 绝对路径（用 raw string，避免 \a \t 等转义）
    "srt": r"D:\path\to\视频名.srt",

    # 1b) 原文备份放哪：留空 = 与本脚本同目录（也就是 _tmp_<项目>/，随临时目录一起删）
    #     只有想长期保留原文时才填别的目录。别填视频目录，交付要求那里只剩三份成品。
    "backup_dir": "",

    # 2) 中文分片（与本脚本同目录，或写绝对路径）。按顺序合并，后面的覆盖前面的。
    "zh_parts": ["zh_part1.py", "zh_part2.py"],

    # 3) 合规版需要改写的条目（只写要改的，其余自动沿用正常版）
    "dy_overrides": {},

    # 4) 铁律11 专名断言：[(专名, [出现条目号, ...]), ...]（比较时不区分大小写）
    "proper_nouns": [
        # ("Uliassi", [2, 7, 223]),
    ],

    # 5) 未修正条目原文断言：[(条目号, "原文片段"), ...]  防相邻条目被误覆盖
    "untouched": [
        # (934, "Goodbye!"),
    ],

    # 6) 残留关键词扫描（词边界匹配，写 ASR 的「原始错误形态」）
    "resid": [],

    # 7) 漏词审计豁免：确实该变短的条目号（删重复词 / 去口吃 / 合并赘语）
    "shrink_ok": [],
}

# 英文修正字典：{条目号: (原文整条, 修正后整条)}
#   ⚠️ 推荐写元组：old 会成为硬断言，key 写偏一位立刻暴露
#   ⚠️ 整条替换，值必须包含该条全部文本；只写半句会丢句尾（铁律13）
#   ⚠️ 只写字符串也可以（不校验原文），但那是最后手段
EN_FIX = {
    # 2: ("the three Michelin star Uliassi. Beautiful.",
    #     "the three-Michelin-star Uliassi. Beautiful."),
}

# ========================== 填写区结束 ==========================


PAT = re.compile(
    r'^(\d+)[ \t]*\n'
    r'(\d{2}:\d{2}:\d{2}[,.]\d{3}[ \t]*-->[ \t]*\d{2}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n'
    r'(.*?)'
    r'(?=\n\d+[ \t]*\n\d{2}:\d{2}:\d{2}[,.]\d{3}[ \t]*-->|\n?\Z)',
    re.S | re.M,
)

BACKUP_SUFFIX = '_en_original'


def read_srt(path):
    with open(path, 'rb') as f:
        b = f.read()
    raw = b.decode('utf-8-sig').replace('\r\n', '\n')
    tc, tx = {}, {}
    for m in PAT.finditer(raw):
        k = int(m.group(1))
        tc[k] = m.group(2)
        tx[k] = m.group(3).strip()
    return tc, tx


def write_srt(path, tc, texts):
    """单 BOM + CRLF + 条目之间空行分隔（标准 SRT）

    注意：条目之间必须留一个空行。历史上这里用 '\\n'.join('%d\\n%s\\n%s' ...)
    写出的文件没有空行分隔，虽然本 skill 的 verify_srt.py 能解析，但
    VideoSubtitleTool（以及不少第三方工具/播放器）按空行分块，
    会把整份文件当成一条字幕，表现为"嵌入后没有字幕"。
    """
    body = '\n\n'.join('%d\n%s\n%s' % (k, tc[k], texts[k]) for k in sorted(texts))
    data = ('\ufeff' + body + '\n').replace('\n', '\r\n').encode('utf-8')
    with open(path, 'wb') as f:
        f.write(data)


def byte_selfcheck(path, n):
    b = open(path, 'rb').read()
    bom, crlf, lf = b.count(b'\xef\xbb\xbf'), b.count(b'\r\n'), b.count(b'\n')
    blank = b.count(b'\r\n\r\n')
    errs = []
    if bom != 1:
        errs.append('BOM=%d（应为 1）' % bom)
    if crlf != lf:
        errs.append('CRLF=%d / LF=%d（应全为 CRLF）' % (crlf, lf))
    if n > 1 and blank != n - 1:
        errs.append('条目间空行=%d（应为 %d）' % (blank, n - 1))
    return errs


def load_zh_parts(script_dir, parts):
    """从 zh_part*.py 里读取 ZH1/ZH2/... 字典并合并"""
    merged, loaded = {}, []
    for name in parts:
        p = name if os.path.isabs(name) else os.path.join(script_dir, name)
        if not os.path.exists(p):
            raise SystemExit('❌ 找不到中文分片: %s' % p)
        src = open(p, encoding='utf-8').read()
        found = re.findall(r'(\w+)\s*=\s*\{.*?\n\}', src, re.S)
        if not found:
            raise SystemExit('❌ %s 中没有找到形如 ZH1 = { ... } 的字典' % p)
        ns = {}
        exec(compile(src, p, 'exec'), ns)
        for var in found:
            d = ns.get(var)
            if isinstance(d, dict) and d:
                merged.update(d)
                loaded.append('%s:%s(%d条)' % (os.path.basename(p), var, len(d)))
    print('已载入中文分片: %s' % ', '.join(loaded))
    return merged


def cn(s):
    return len(re.findall(r'[\u4e00-\u9fff]', s))


def word_pat(w):
    return r'(?<![A-Za-z0-9])' + re.escape(w) + r'(?![A-Za-z0-9])'


def main():
    dry = '--dry-run' in sys.argv
    no_verify = '--no-verify' in sys.argv
    want_check = '--check' in sys.argv
    want_keys = '--keys' in sys.argv
    dump_arg = ''
    if '--dump' in sys.argv:
        i = sys.argv.index('--dump')
        dump_arg = sys.argv[i + 1] if i + 1 < len(sys.argv) else 'all'

    here = os.path.dirname(os.path.abspath(__file__))
    srt = CONFIG['srt']
    if srt.endswith('.srt') and '视频名' in srt:
        raise SystemExit('❌ 请先在 CONFIG["srt"] 里填写真实的 SRT 路径')
    if not os.path.exists(srt):
        raise SystemExit('❌ 找不到文件: %s' % srt)

    # ---------- 原文备份 + 幂等重跑（铁律21） ----------
    base = srt[:-4]
    bdir = CONFIG.get('backup_dir') or here
    bak = os.path.join(bdir, os.path.basename(base) + BACKUP_SUFFIX + '.srt')
    if os.path.exists(bak):
        src = bak
        print('读取原文备份: %s' % os.path.basename(bak))
    else:
        src = srt
        shutil.copyfile(srt, bak)
        print('已备份原文 -> %s' % bak)

    tc, entries = read_srt(src)
    N = len(entries)
    assert sorted(entries) == list(range(1, N + 1)), '❌ 英文条目号不连续'
    print('英文条目数 N = %d' % N)

    # ---------- EN_FIX 归一化 + 原文断言 ----------
    fix = {}
    for k, v in EN_FIX.items():
        if isinstance(v, (tuple, list)):
            assert len(v) == 2, '❌ EN_FIX[%s] 元组长度应为 2' % k
            fix[int(k)] = (v[0], v[1])
        else:
            fix[int(k)] = (None, v)

    bad = [k for k in fix if k not in entries]
    assert not bad, '❌ EN_FIX 含不存在的条目号: %s' % bad

    mism = []
    for k in sorted(fix):
        old = fix[k][0]
        if old is not None and entries[k] != old.strip():
            mism.append((k, old, entries[k]))
    if mism:
        print('\n❌ 原文不符（EN_FIX 的 key 可能偏移了一位）：')
        for k, old, cur in mism[:12]:
            print('  #%d\n    期望: %s\n    实际: %s' % (k, old[:100], cur[:100]))
        raise SystemExit(1)
    n_tuple = sum(1 for v in fix.values() if v[0] is not None)
    print('EN_FIX: %d 条（其中 %d 条带原文断言）' % (len(fix), n_tuple))

    t = {i: entries[i] for i in entries}
    for k, (_, new) in fix.items():
        t[k] = new.strip()

    # ---------- 漏词审计 ----------
    shrink = []
    for k, (old, new) in fix.items():
        if old is None or k in CONFIG['shrink_ok']:
            continue
        ow, nw = len(old.split()), len(new.split())
        if nw < ow - 3:
            shrink.append((k, ow, nw, old[:50]))
    if shrink:
        print('\n❌ 修正后词数骤减（疑似只写了半句，铁律13）：')
        for k, ow, nw, s in shrink:
            print('  #%d  %d 词 → %d 词 | %s' % (k, ow, nw, s))
        print('  确认是要变短的，把条目号写进 CONFIG["shrink_ok"]')
        raise SystemExit(1)

    # ---------- 铁律11：专名断言 / 未修正条目断言 ----------
    for name, keys in CONFIG['proper_nouns']:
        for k in keys:
            assert name.lower() in t[k].lower(), \
                '❌ 专名断言失败: 条目 %d 中找不到 "%s"（实际: %s）' % (k, name, t[k][:60])
    print('专名断言通过: %d 组' % len(CONFIG['proper_nouns']))

    for k, frag in CONFIG['untouched']:
        assert frag in t[k], \
            '❌ 未修正条目被改动: #%d 中找不到 "%s"（实际: %s）' % (k, frag, t[k][:60])
    print('未修正条目断言通过: %d 条' % len(CONFIG['untouched']))

    # ---------- resid 预检（铁律20）----------
    if CONFIG['resid']:
        collide = {}
        for w in CONFIG['resid']:
            ks = [k for k, v in t.items() if re.search(word_pat(w), v)]
            if ks:
                collide[w] = ks[:8]
        if collide:
            print('\n❌ 以下 resid 会命中修正后的正文（自造假告警，铁律20）：')
            for w, ks in collide.items():
                print('  "%s" → %s' % (w, ks))
            print('  请删掉或改成 ASR 的原始错误形态后重跑')
            raise SystemExit(1)
        print('resid 预检通过: %d 项均不命中修正后正文' % len(CONFIG['resid']))

    # ---------- 中文 ----------
    ZH = load_zh_parts(here, CONFIG['zh_parts'])
    missing = [k for k in range(1, N + 1) if k not in ZH]
    if missing:
        print('❌ 中文缺失条目 %d 条: %s' % (len(missing), missing[:20]))
        raise SystemExit(1)
    empty = [k for k, v in ZH.items() if not str(v).strip()]
    assert not empty, '❌ 中文空值条目（铁律1）: %s' % empty[:20]

    colon = [k for k, v in ZH.items() if '：' in v]
    dash = [k for k, v in ZH.items() if '——' in v]
    assert not colon, '❌ 中文含全角冒号 ： %s' % colon[:20]
    assert not dash, '❌ 中文含破折号 —— %s' % dash[:20]

    # ---------- 铁律10：全量漂移检测 ----------
    mm = []
    for i in range(1, N + 1):
        ew, zc = len(t[i].split()), cn(ZH[i])
        if (ew > 8 and zc <= 4) or (ew <= 3 and zc > 12) or zc == 0:
            mm.append((i, ew, zc, t[i][:40]))
    if mm:
        print('⚠️ 漂移告警 %d 条（中文数字/专名括注属常见误报，请人工确认）:' % len(mm))
        for i, ew, zc, s in mm[:20]:
            print('   #%d: %dw/%dc | %s' % (i, ew, zc, s))
    assert not mm, '❌ 漂移检测未通过，请修正后重跑'

    # ---------- 合规版 ----------
    DY = dict(ZH)
    for k, v in CONFIG['dy_overrides'].items():
        assert k in DY, '❌ dy_overrides 含不存在的条目号 %s' % k
        DY[k] = v
    print('合规版改写 %d 条: %s' % (len(CONFIG['dy_overrides']),
                                  sorted(CONFIG['dy_overrides'])[:26]))

    # ---------- 辅助输出模式 ----------
    if want_keys:
        for k in range(1, N + 1):
            mark = 'DY|' if DY[k] != ZH[k] else '  |'
            print('#%-4d EN %s' % (k, t[k]))
            print('     ZH %s' % ZH[k])
            if DY[k] != ZH[k]:
                print('     %s %s' % (mark, DY[k]))
        print('\n（逐条核对 DY_OVR 的 key 之后再加 --dry-run 正式跑）')
        return 0

    if dump_arg:
        lo, hi = 1, N
        if dump_arg != 'all' and '-' in dump_arg:
            a, b = dump_arg.split('-', 1)
            lo, hi = int(a), int(b or N)
        for k in range(max(1, lo), min(N, hi) + 1):
            print('[%d] %s' % (k, t[k]))
        return 0

    if want_check:
        lines = []
        for k in range(1, N + 1):
            lines.append('%d' % k)
            lines.append('EN| ' + t[k])
            lines.append('ZH| ' + ZH[k])
            if DY[k] != ZH[k]:
                lines.append('DY| ' + DY[k])
        cp = os.path.join(here, 'check.txt')
        with open(cp, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        print('\n已生成并排复读文件: %s（%d 条，必须从头读到尾）' % (cp, N))

    zh_path, dy_path = base + '_zh.srt', base + '_zh_douyin.srt'

    if dry:
        print('\n[DRY-RUN] 全部断言通过，未写文件。目标:')
        for p in (srt, zh_path, dy_path):
            print('  %s' % p)
        return 0

    write_srt(srt, tc, t)
    write_srt(zh_path, tc, ZH)
    write_srt(dy_path, tc, DY)

    print('\n✅ 已写入三份文件（%d 条）' % N)
    bad = 0
    for p in (srt, zh_path, dy_path):
        errs = byte_selfcheck(p, N)
        print('   %7d bytes  %s%s' % (os.path.getsize(p), p,
                                      '' if not errs else '  ❌ ' + '；'.join(errs)))
        bad += len(errs)
    assert not bad, '❌ 字节自检未通过'

    if not no_verify:
        vs = os.path.join(here, 'verify_srt.py')
        if os.path.exists(vs):
            print('\n' + '=' * 56)
            print('调用 verify_srt.py 做四轮验证 ...')
            cmd = [sys.executable, vs, srt]
            if CONFIG['resid']:
                cmd += ['--resid', ','.join(CONFIG['resid'])]
            return subprocess.call(cmd)
        print('提示：同目录未找到 verify_srt.py，请手动运行验证')
    return 0


if __name__ == '__main__':
    sys.exit(main())
