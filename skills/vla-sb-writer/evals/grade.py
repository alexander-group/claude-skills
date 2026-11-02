"""Programmatic grader for the vla-sb-writer eval cases in this folder.

Usage:  python evals/grade.py <workspace>/iteration-N

Each <case>/<config>/outputs/ under the iteration directory is graded against the statements in
evals/<case>/graders/*.md, and a grading.json is written next to outputs/. Case facts (target, coordinates,
expected resources, etc.) live in CASES below; update them if you change a case's prompt.
"""
import sys, os, glob, json, re, argparse
SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the skill directory
sys.path.insert(0, SK + '/scripts')
import check_sb, find_calibrators as fc
from astropy.coordinates import SkyCoord
import astropy.units as u

CASES = {
 'c-band-grb-a-config': dict(cat='26B-123', tgt='GRB261028A', cfg='A', bands=['C'], hours=1.0,
     ra='14:22:31.52', dec='+12:05:44.1', res={'C32f2Amixalt-blank'}, maxsep=15),
 'ku-band-tde-d-config': dict(cat='26A-445', tgt='AT2024zau', cfg='D', bands=['Ku'], hours=1.5,
     ra='06:47:16.376', dec='+41:57:55.09', res={'Ku48f3DCB'}, maxsep=10),
 'lscx-multiband-b-config': dict(cat='25A-159', tgt='AT2023clx', cfg='B', bands=['L','S','C','X'], hours=2.0,
     ra='11:40:09.444', dec='+15:19:39.04', res={'L16f3B','S16f3B','C32f3Bmixalt-blank','X32f3DCB'}, maxsep=15),
}
cals, coords = fc.load_catalog(); tables = fc.load_band_tables(); names = check_sb.known_cal_names()

def parse(path):
    recs = []
    for l in open(path, errors='replace'):
        s = l.strip()
        if s and not s.startswith('#'):
            recs.append([x.strip() for x in s.split(';')])
    return recs

def expand(recs):
    stack, counts = [[]], []
    for p in recs:
        if p[0] == 'LOOP-START': stack.append([]); counts.append(int(p[2]) if p[2].isdigit() else 1)
        elif p[0] == 'LOOP-END' and counts: b = stack.pop(); stack[-1].extend(b * counts.pop())
        elif p[0] in ('STD', 'PTG', 'IP') and len(p) > 5: stack[-1].append(p)
    return [s for blk in stack for s in blk]

def secs(d):
    v = re.findall(r'(\d+)\s*([hms])', d); return sum(int(n) * {'h': 3600, 'm': 60, 's': 1}[k] for n, k in v)

WEATHER_OK = {'c-band-grb-a-config': [(100, 45), (100, 90)], 'ku-band-tde-d-config': [(10, 15), (10, 30)],
              'lscx-multiband-b-config': [(15, 30), (15, 60)]}
MINEL = {'c-band-grb-a-config': 30, 'ku-band-tde-d-config': 35, 'lscx-multiband-b-config': 30}


def starts_in(rng):
    out = set()
    for r in filter(None, [x.strip() for x in rng.split(',')]):
        m = re.match(r'(\d+):(\d+)(?::(\d+))?-(\d+):(\d+)(?::(\d+))?', r)
        if not m: continue
        a = int(m[1]) * 60 + int(m[2]); b = int(m[4]) * 60 + int(m[5])
        for k in range(0, (b - a) % 1440 + 1, 5): out.add(((a + k) % 1440) // 5)
    return out


def fmt_s(x):
    return f'{x // 3600}h {x % 3600 // 60}m {x % 60}s'


def check_one(case, t, f):
    c = CASES[case]; recs = parse(f); scans = expand(recs)
    hdr = next((p for p in recs if p[0] == 'SCHED-BLOCK'), [''] * 15)
    tgt = SkyCoord(c['ra'], c['dec'], unit=(u.hourangle, u.deg))
    b = os.path.basename(f)
    if 'correct OPT text structure' in t:
        errs, _, _, _ = check_sb.check(f, argparse.Namespace(target=None, catalog=None, expect=None), names)
        return not errs, f'{b}: ' + ('; '.join(errs) if errs else 'no errors')
    if 'source catalog' in t:
        src = next((p[1] for p in recs if p[0] == 'SRC-CAT'), '')
        tg = {s[2] for s in scans if s[0] == 'STD' and 'ObsTgt' in s[14]}
        return src.split(',')[-1].strip() == c['cat'] and tg == {c['tgt']}, f'{b}: SRC-CAT={src!r}; targets={sorted(tg)}'
    if 'configuration field' in t:
        used = {s[3] for s in scans if s[0] == 'STD' and s[3] not in ('X-point', 'PREV')}
        return used == c['res'] and hdr[7] == c['cfg'], f'{b}: resources={sorted(used)}; config={hdr[7]!r}'
    if 'gain calibrator' in t:
        g = sorted({s[2] for s in scans if s[0] == 'STD' and 'CalGain' in s[14]}); ev = []; ok = bool(g)
        for name in g:
            hit = cals.index[cals['IAU FULL NAME'] == name.split('=')[-1]]
            if not len(hit): ok = False; ev.append(f'{name}: not in list'); continue
            sep = tgt.separation(coords[hit[0]]).deg
            codes = [fc.band_code(tables.get(cals['IAU NAME'][hit[0]], {}), x, c['cfg'])[0] for x in c['bands'] if x != 'S']
            ok &= sep <= c['maxsep'] and all(x in 'PS' for x in codes)
            ev.append(f'{name}: sep {sep:.1f}, codes {codes}')
        return ok, f'{b}: ' + '; '.join(ev)
    if 'reference pointing' in t:
        fk = next((i for i, s in enumerate(scans) if s[0] == 'STD' and s[3].startswith('Ku') and 'SetAtnGain' not in s[14]), None)
        pt = next((i for i, s in enumerate(scans) if s[0] in ('PTG', 'IP') and s[3] == 'X-point'), None)
        return pt is not None and fk is not None and pt < fk, f'{b}: first PTG {pt}, first Ku cal/tgt {fk}'
    if 'total duration' in t:
        want = int(c['hours'] * 3600); tot = sum(secs(s[5]) for s in scans)
        return tot == want, f'{b}: {fmt_s(tot)}'
    if 'antenna wrap' in t:
        w = {s[6] for s in scans if len(s) > 6} - {''}
        return bool(w), f'{b}: wraps {sorted(w) or "none"}'
    if 'stays above 20' in t:
        tot = sum(secs(s[5]) for s in scans) / 3600; bad = []
        for i in sorted(starts_in(hdr[5])):
            st = i * 5 / 60
            for j in range(11):
                e = fc.elevation(st + j * tot / 10, tgt.ra.deg, tgt.dec.deg)
                if e < 20: bad.append(f'start {fc.hms(st)} el {e:.0f}'); break
        return bool(hdr[5]) and not bad, f'{b}: {hdr[5]!r} ' + ('; '.join(bad[:2]) if bad else 'ok')
    if 'ASAP' in t:
        return bool(re.search(r'asap|as soon as possible', hdr[13], re.I)), f'{b}: {hdr[13][:120]!r}'
    if 'file name' in t:
        return bool(re.fullmatch(r'U_AT2024zau_e3(_early|_late|_mid)?\.optSB', b)), b
    if 'weather field' in t:
        m = re.fullmatch(r'w=([\d.]+),p=([\d.]+)', hdr[12])
        ok = bool(m) and (float(m[1]), float(m[2])) in WEATHER_OK[case]
        return ok, f'{b}: {hdr[12]}'
    if 'CalBP,CalFlux' in t:
        fl = {}
        for s in scans:
            if s[0] == 'STD' and 'CalFlux' in s[14] and re.search(r'3C(48|138|147|286)', s[2]):
                fl.setdefault(s[3][0], set()).add(s[2])
        return all(x in fl for x in 'LSCX'), f'{b}: bands with flux scans {sorted(fl)}'
    return None, 'no programmatic check'


def grade(case, rundir):
    c = CASES[case]; out = []
    files = [f for f in glob.glob(rundir + '/outputs/**/*', recursive=True)
             if os.path.isfile(f) and not f.endswith(('.md', '.py', '.json', '.log'))]
    sbs = sorted(f for f in files if 'SCHED-BLOCK' in open(f, errors='replace').read())
    texts = [open(g).read().split('---', 2)[2].strip() for g in sorted(glob.glob(f'{SK}/evals/{case}/graders/*.md'))]
    if not sbs:
        return [dict(text=t, passed=False, evidence='no OPT-format SB file in outputs') for t in texts], None
    for t in texts:
        if 'can start at no less than' in t:
            tgt = SkyCoord(c['ra'], c['dec'], unit=(u.hourangle, u.deg)); L = c['hours']
            possible = {i for i in range(288) if fc.in_range(tgt, i / 12, i / 12 + L, MINEL[case], 80)} if hasattr(fc, 'in_range') else None
            if possible is None:
                import plan_sbs; possible = {i for i in range(288) if plan_sbs.in_range(tgt, i / 12, i / 12 + L, MINEL[case], 80)}
            have = set()
            for f in sbs:
                hdr = next((p for p in parse(f) if p[0] == 'SCHED-BLOCK'), [''] * 15); have |= starts_in(hdr[5])
            frac = len(have & possible) / max(1, len(possible))
            out.append(dict(text=t, passed=frac >= 0.75, evidence=f'{len(sbs)} SB(s); covers {frac:.0%} of {len(possible)*5/60:.1f} h of usable start LST'))
            continue
        res = [check_one(case, t, f) for f in sbs]
        ok = all(r[0] for r in res)
        ev = ' | '.join(r[1] for r in res)
        if 'antenna wrap' in t:
            ok = ok and len(sbs) <= 2
            ev = f'{len(sbs)} SB file(s); ' + ev
        out.append(dict(text=t, passed=ok, evidence=ev))
    return out, sbs


it = sys.argv[1]
for case in CASES:
    for cfgdir in glob.glob(f'{it}/{case}/*/'):
        if not os.path.isdir(cfgdir + 'outputs'): continue
        res, f = grade(case, cfgdir.rstrip('/'))
        n = sum(r['passed'] for r in res)
        json.dump(dict(expectations=res, summary=dict(passed=n, failed=len(res) - n, total=len(res), pass_rate=n / len(res))),
                  open(cfgdir + 'grading.json', 'w'), indent=2)
        print(f'{case}/{os.path.basename(cfgdir.rstrip("/"))}: {n}/{len(res)}  ({f})')
        for r in res:
            if not r['passed']: print('   FAIL', r['text'][:70], '|', r['evidence'][:160])
