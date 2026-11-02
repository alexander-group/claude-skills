#!/usr/bin/env python3
"""Static checker for VLA OPT text-format scheduling blocks (.optSB).

It catches formatting and structural mistakes before you import into the OPT; it is not a
replacement for OPT validation (which also checks slews, source catalog entries, and elevations).

  check_sb.py FILE [FILE ...] [--target NAME] [--catalog NAME] [--expect 1h30m] [--quiet]

Exit status is 1 if any file has ERRORs (WARNs do not fail).
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_sb import RESOURCES, THREE_BIT, HIGH, parse_total, fmt, DATA, weather_limits  # noqa: E402

FIELDS = {'STD': 17, 'PTG': 14, 'IP': 14, 'LOOP-START': 6, 'LOOP-END': 2,
          'VERSION': 3, 'SRC-CAT': 3, 'HDWR-CAT': 3, 'SCHED-BLOCK': 15}
INTENTS = {'SetAtnGain', 'CalGain', 'ObsTgt', 'CalBP', 'CalFlux', 'CalPolAng', 'CalPolLeak', 'CalPointing'}
EXTRA_RESOURCES = {'X-point', 'PREV', 'C32f2A', 'C32f3B', 'S14f2Ashiftalt-blank'}
KNOWN_RESOURCES = {r for cfg in RESOURCES.values() for r in cfg.values()} | EXTRA_RESOURCES
DUR_RE = re.compile(r'^\d+h \d+m \d+s$')


def band_of(res):
    m = re.match(r'^(Ka|Ku|K|X|C|S|L)\d', res)
    return m.group(1) if m else None


def secs(s):
    h, m, x = (int(v) for v in re.findall(r'(\d+)[hms]', s))
    return h * 3600 + m * 60 + x


def known_cal_names():
    import csv
    names = set()
    with open(os.path.join(DATA, 'calibrators.csv')) as f:
        for row in csv.DictReader(f):
            names |= {row['IAU FULL NAME'], row['IAU NAME'], row['ALT.NAME']}
    names.discard('')
    return names


def check(path, args, cals):
    errs, warns = [], []
    E = lambda n, m: errs.append(f"line {n}: {m}")
    W = lambda n, m: warns.append(f"line {n}: {m}")
    seen, config, weather = set(), None, None
    stack, counts = [[]], []        # for loop expansion
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except OSError as e:
        return [str(e)], [], None, 0

    for n, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s or s.startswith('#'):
            continue
        p = [x.strip() for x in s.split(';')]
        kind = p[0]
        if kind not in FIELDS:
            E(n, f"unknown record type {kind!r}")
            continue
        seen.add(kind)
        if len(p) != FIELDS[kind]:
            E(n, f"{kind} has {len(p) - 1} ';'-separated fields, expected {FIELDS[kind] - 1}")
            continue
        if kind == 'VERSION' and p[1] != '7':
            W(n, f"VERSION {p[1]} (group SBs use 7)")
        elif kind == 'SRC-CAT':
            if not p[1].startswith('VLA,'):
                E(n, "SRC-CAT should be 'VLA, <catalog>'")
            elif args.catalog and p[1].split(',', 1)[1].strip() != args.catalog:
                E(n, f"source catalog is {p[1].split(',', 1)[1].strip()!r}, expected {args.catalog!r}")
        elif kind == 'SCHED-BLOCK':
            config = p[7]
            if config not in ('A', 'B', 'C', 'D', ''):
                E(n, f"configuration {config!r} not A/B/C/D")
            lst = p[5] + ('' if p[5].endswith(',') else ',')
            if not re.fullmatch(r'(\d\d:\d\d(:\d\d)?-\d\d:\d\d(:\d\d)?, ?)+', lst):
                E(n, f"LST start range {p[5]!r} should look like 04:25:00-11:45:00,")
            elif not re.fullmatch(r'(\d\d:\d\d:\d\d-\d\d:\d\d:\d\d, ?)+', lst):
                W(n, f"LST start range {p[5]!r} has no seconds; the OPT exports HH:MM:SS")
            m = re.fullmatch(r'w=([\d.]+),p=([\d.]+)', p[12])
            if not m:
                E(n, f"weather field {p[12]!r} should look like w=10.0,p=15.0")
            else:
                weather = (n, float(m.group(1)), float(m.group(2)))
            if not re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d, ?\d{4}-\d\d-\d\d \d\d:\d\d:\d\d', p[4]):
                E(n, f"date range {p[4]!r} malformed")
        elif kind == 'LOOP-START':
            if not p[2].isdigit() or int(p[2]) < 1:
                E(n, f"loop count {p[2]!r} must be a positive integer")
                p[2] = '1'
            stack.append([])
            counts.append(int(p[2]))
        elif kind == 'LOOP-END':
            if not counts:
                E(n, "LOOP-END without LOOP-START")
                continue
            body = stack.pop()
            stack[-1].extend(body * counts.pop())
        elif kind in ('STD', 'PTG', 'IP'):
            src, res, mode, dur = p[2], p[3], p[4], p[5]
            if mode != 'DUR':
                W(n, f"timing mode {mode!r} (group SBs use DUR)")
            if not DUR_RE.match(dur):
                E(n, f"duration {dur!r} should look like '0h 1m 30s'")
                continue
            if not src:
                E(n, "scan has no source")
            if res not in KNOWN_RESOURCES:
                W(n, f"resource {res!r} not among known NRAO defaults used by the group")
            if p[6] not in ('', 'CW', 'CCW'):
                E(n, f"wrap {p[6]!r} must be blank, CW or CCW")
            intent = ''
            if kind == 'STD':
                intent = p[14]
                its = [i for i in intent.split(',') if i]
                if not its:
                    E(n, "STD scan has no intent")
                for i in its:
                    if i not in INTENTS:
                        E(n, f"unknown intent {i!r}")
                if p[7] not in ('Y', 'N'):
                    E(n, f"pointing-correction flag {p[7]!r} must be Y or N")
            if res == 'X-point' and kind == 'STD' and 'SetAtnGain' not in intent:
                W(n, "X-point resource used for a non-setup STD scan")
            stack[-1].append(dict(line=n, kind=kind, src=src, res=res, sec=secs(dur), intent=intent))

    if counts:
        errs.append(f"{len(counts)} LOOP-START without matching LOOP-END")
    for k in ('VERSION', 'SRC-CAT', 'HDWR-CAT', 'SCHED-BLOCK'):
        if k not in seen:
            errs.append(f"missing {k} record")
    scans = stack[0] if len(stack) == 1 else [s for blk in stack for s in blk]
    if not scans:
        errs.append("no scans")
        return errs, warns, config, 0

    # ---- structural rules on the expanded scan sequence ----
    if 'SetAtnGain' not in scans[0]['intent']:
        W(scans[0]['line'], "first scan is not a setup (SetAtnGain) scan")
    cur, ready, pointed, setup_done = None, False, False, set()
    reported = set()
    for sc in scans:
        r = sc['res']
        if sc['kind'] in ('PTG', 'IP'):
            pointed, cur, ready = True, 'PTG', False
            continue
        if r == 'PREV':
            continue
        if r != cur:
            cur, ready = r, False
        b = band_of(r)
        if 'SetAtnGain' in sc['intent']:
            if r not in setup_done:
                setup_done.add(r)          # first use = attenuator setup
            else:
                ready = True               # later setup scan on same resource = requantizer setup
            continue
        key = (sc['line'], 'rq')
        if b in THREE_BIT and not ready and key not in reported:
            reported.add(key)
            E(sc['line'], f"{r} scan not preceded by a requantizer (SetAtnGain) scan after a "
                          f"resource change or pointing")
        if r not in setup_done and ('res', r) not in reported and r != 'X-point':
            reported.add(('res', r))
            W(sc['line'], f"{r} used before any attenuator setup scan with that resource")
        if b in HIGH and not pointed and ('ptg', b) not in reported:
            reported.add(('ptg', b))
            E(sc['line'], f"{b}-band scan before any X-band reference pointing (PTG) scan")

    bands, last = {}, None
    for sc in scans:
        if sc['res'] == 'PREV':          # PREV = same resource as the previous scan
            sc['res'] = last or 'PREV'
        elif sc['kind'] == 'STD':
            last = sc['res']
        b = band_of(sc['res'])
        if b:
            bands.setdefault(b, set()).update(i for i in sc['intent'].split(',') if i)
    for b, its in bands.items():
        if 'ObsTgt' in its:
            if 'CalGain' not in its:
                E('-', f"{b} band has target scans but no CalGain scan")
            if 'CalFlux' not in its:
                W('-', f"{b} band has no CalFlux scan in this SB")
            if 'CalBP' not in its:
                W('-', f"{b} band has no CalBP scan in this SB")

    if config:
        for sc in scans:
            b = band_of(sc['res'])
            if b and sc['res'] in KNOWN_RESOURCES - EXTRA_RESOURCES and sc['res'] != RESOURCES[config].get(b) \
                    and ('cfg', sc['res']) not in reported:
                reported.add(('cfg', sc['res']))
                W(sc['line'], f"{sc['res']} is not the group's usual {b}-band resource for {config} config "
                              f"({RESOURCES[config][b]})")

    for sc in scans:
        if any(i in sc['intent'] for i in ('CalGain', 'CalFlux', 'CalBP')) or sc['kind'] != 'STD':
            name = sc['src'].split('=')[-1]
            if name not in cals and sc['src'] not in cals and ('cal', sc['src']) not in reported:
                reported.add(('cal', sc['src']))
                W(sc['line'], f"calibrator {sc['src']!r} not found in the bundled calibrator list")
    if args.target:
        tg = {sc['src'] for sc in scans if 'ObsTgt' in sc['intent']}
        if tg != {args.target}:
            E('-', f"target scans observe {sorted(tg)}, expected only {args.target!r}")

    if weather and bands:
        ln, wv, pv = weather
        sci = [b for b, its in bands.items() if 'ObsTgt' in its] or list(bands)
        tw, tp = weather_limits(sci)
        _, tp_self = weather_limits(sci, selfcal=True)
        if wv > tw or pv > tp_self:
            W(ln, f"weather w={wv:g},p={pv:g} is looser than the NRAO limits for {','.join(sci)} "
                  f"(w={tw:g},p={tp:g}; p={tp_self:g} if self-calibrating)")
        elif wv < tw or pv < tp:
            W(ln, f"weather w={wv:g},p={pv:g} is stricter than the NRAO limits for {','.join(sci)} "
                  f"(w={tw:g},p={tp:g}), which makes the SB harder to schedule")

    total = sum(sc['sec'] for sc in scans)
    if args.expect:
        want = parse_total(args.expect)
        if abs(total - want) > 0.1 * want:
            E('-', f"total duration {fmt(total)} differs from requested {fmt(want)} by more than 10%")
    return errs, warns, config, total


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+')
    ap.add_argument('--target'); ap.add_argument('--catalog'); ap.add_argument('--expect')
    ap.add_argument('--quiet', action='store_true', help='only print files with errors')
    args = ap.parse_args()
    cals = known_cal_names()
    bad = 0
    for f in args.files:
        errs, warns, config, total = check(f, args, cals)
        bad += bool(errs)
        if args.quiet and not errs:
            continue
        print(f"{'FAIL' if errs else 'OK  '} {f}  (config {config or 'Any'}, total {fmt(total)})")
        for e in errs:
            print(f"   ERROR {e}")
        if not args.quiet:
            for w in warns:
                print(f"   WARN  {w}")
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
