#!/usr/bin/env python3
"""Plan and write the set of linked SBs (single, or early/mid/late) for one target.

Goal: MAXIMIZE THE LST RANGE in which some SB can start, and MAXIMIZE TIME ON SOURCE, for a fixed
total SB length. A start LST is usable for a variant (flux calibrator + whether it is observed first
or last) if the target and gain calibrator stay between --min-el and --max-el for the whole SB and the
flux calibrator is in that range while it is observed. When no one variant covers every usable start
LST (target or calibrator sets, or passes above 80 deg mid-SB), several linked SBs are written so that
together they cover all of it; operators run only one of them.

Example
-------
  plan_sbs.py --target AT2024zau --catalog 26A-445 --config D --bands Ku --total 1.5h \\
      --ra 06:47:16.38 --dec +41:57:55.1 --gain-cal J0646+4451 --epoch e3 --outdir .
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_calibrators as fcal  # noqa: E402
from build_sb import make_sb, budget, parse_total, fmt, HIGH, SHORT, BAND_ORDER  # noqa: E402

STEP_MIN = 5
N = 24 * 60 // STEP_MIN
TOL = 3   # grid steps (15 min) of coverage we'll give up to pick a variant with more time on source


def lst_str(i):
    m = (i % N) * STEP_MIN
    return f"{m // 60:02d}:{m % 60:02d}:00"


def in_range(coord, t0, t1, lo, hi):
    """True if coord stays within [lo, hi] deg elevation for LST t0..t1 hours (sampled every 2 min)."""
    k = max(2, int((t1 - t0) * 30) + 1)
    for j in range(k + 1):
        el = fcal.elevation(t0 + (t1 - t0) * j / k, coord.ra.deg, coord.dec.deg)
        if el < lo or el > hi:
            return False
    return True


def runs(mask):
    """Contiguous True runs on the circular grid -> list of (start, end) indices (end inclusive)."""
    if all(mask):
        return [(0, N - 1)]
    out = []
    for i in range(N):
        if mask[i] and not mask[i - 1]:
            j = i
            while mask[(j + 1) % N]:
                j += 1
            out.append((i, j))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--target', required=True); ap.add_argument('--catalog', required=True)
    ap.add_argument('--config', required=True, choices=list('ABCD'))
    ap.add_argument('--bands', required=True); ap.add_argument('--total', required=True)
    ap.add_argument('--ra'); ap.add_argument('--dec'); ap.add_argument('--name', help='look up RA/Dec in $TNS_CATALOG')
    ap.add_argument('--gain-cal', required=True, help='J2000 name, chosen with find_calibrators.py')
    ap.add_argument('--flux-cals', default='3C286,3C147,3C48',
                    help='candidates in order of preference (3C138 is added as a last resort)')
    ap.add_argument('--min-el', type=float, help='default 30 (A/B) or 35 (C/D)')
    ap.add_argument('--max-el', type=float, default=80.0)
    ap.add_argument('--max-sbs', type=int, default=3)
    ap.add_argument('--min-gain', type=float, default=30,
                    help='minutes of extra start-LST coverage needed to justify another linked SB')
    ap.add_argument('--epoch', default='', help='epoch label for file names, e.g. e3')
    ap.add_argument('--comments', default='')
    ap.add_argument('--weights', default='')
    ap.add_argument('--selfcal', action='store_true')
    ap.add_argument('--outdir', default='.')
    a = ap.parse_args()

    bands = [b for b in BAND_ORDER if b in [x.strip() for x in a.bands.split(',')]]
    total = parse_total(a.total)
    L = total / 3600
    min_el = a.min_el if a.min_el is not None else (35.0 if a.config in 'CD' else 30.0)
    weights = {k.strip(): float(v) for k, v in (kv.split('=') for kv in filter(None, a.weights.split(',')))}
    if a.ra and a.dec:
        ra, dec = a.ra, a.dec
    elif a.name:
        ra, dec = fcal.lookup_tns(a.name)
        print(f"TNS lookup: {a.name} -> {ra} {dec}")
    else:
        sys.exit("give --ra/--dec or --name")
    tgt = fcal.to_skycoord(ra, dec)
    cals, coords = fcal.load_catalog()

    def cal(name):
        col = 'ALT.NAME' if name.startswith('3C') else 'IAU FULL NAME'
        idx = cals.index[cals[col] == name]
        if not len(idx):
            sys.exit(f"{name} not in calibrator list")
        return coords[idx[0]]
    gcoord = cal(a.gain_cal)

    flux_names = [f.strip() for f in a.flux_cals.split(',') if f.strip()]
    nb, high = len(bands), any(b in HIGH for b in bands)
    f_first = (600 + nb * 210) / 3600                      # setup + flux block at the start
    f_last = ((390 if high else 150) + nb * 210) / 3600    # pointing/slew + flux block at the end

    def evaluate(flux_list):
        variants = []
        for fname in flux_list:
            fc = cal(fname)
            for first in (True, False):
                mask = []
                for i in range(N):
                    t0 = i * STEP_MIN / 60
                    ok = in_range(tgt, t0, t0 + L, min_el, a.max_el) and in_range(gcoord, t0, t0 + L, min_el, a.max_el)
                    if ok:
                        ft0 = t0 if first else t0 + L - f_last
                        ok = in_range(fc, ft0, ft0 + (f_first if first else f_last), min_el, a.max_el)
                    mask.append(ok)
                if not any(mask):
                    continue
                try:
                    r = make_sb(a.target, a.catalog, a.config, bands, total, a.gain_cal, fname, '00:00:00-00:00:00',
                                weights=weights, flux_first=first, selfcal=a.selfcal)
                except ValueError as e:
                    sys.exit(str(e))
                variants.append(dict(flux=fname, first=first, mask=mask, on_target=r['on_target']))
        return variants

    variants = evaluate(flux_names)
    union = [any(v['mask'][i] for v in variants) for i in range(N)]
    if '3C138' not in flux_names:   # last resort, only if it adds coverage
        extra = evaluate(['3C138'])
        if any(any(v['mask'][i] for v in extra) and not union[i] for i in range(N)):
            variants += extra
            union = [any(v['mask'][i] for v in variants) for i in range(N)]
    if not any(union):
        # how long could an SB be?
        best = 0
        for i in range(N):
            t0 = i * STEP_MIN / 60
            h = 0
            while h < 12 and in_range(tgt, t0, t0 + h + 0.25, min_el, a.max_el) and \
                    in_range(gcoord, t0, t0 + h + 0.25, min_el, a.max_el):
                h += 0.25
            best = max(best, h)
        sys.exit(f"No start LST keeps target + {a.gain_cal} within {min_el:g}-{a.max_el:g} deg for {fmt(total)}. "
                 f"Longest possible SB (ignoring the flux calibrator) is about {best:g} h. Shorten the SB, lower "
                 f"--min-el, or split it into separate SBs.")

    # ---- greedy circular interval cover: fewest SBs, then most time on source ----
    chosen, covered = [], [False] * N
    full = [v for v in variants if all(v['mask'])]
    if full:
        best = max(full, key=lambda v: v['on_target'])
        chosen.append((best, 0, N - 1))
    else:
        cand = [(v, s, e) for v in variants for s, e in runs(v['mask'])]
        gap = next(i for i in range(N) if not union[i])
        while True:
            p = next(((gap + k) % N for k in range(1, N + 1) if union[(gap + k) % N] and not covered[(gap + k) % N]),
                     None)
            if p is None:
                break
            reach = []
            for v, s, e in cand:
                ln = (e - s) % N
                if (p - s) % N <= ln:                     # run contains p
                    reach.append(((e - p) % N, v, s, e))
            far = max(r[0] for r in reach)
            pick = max((r for r in reach if r[0] >= far - TOL), key=lambda r: (r[1]['on_target'], r[0]))
            _, v, s, e = pick
            chosen.append((v, s, e))
            for k in range((e - s) % N + 1):
                covered[(s + k) % N] = True
    # drop SBs that add little: an extra linked SB is only worth it for >= --min-gain of new start LSTs
    def cover(sel):
        return {(s + k) % N for _, s, e in sel for k in range((e - s) % N + 1)}
    while len(chosen) > 1:
        loss = [(len(cover(chosen)) - len(cover(chosen[:i] + chosen[i + 1:])), i) for i in range(len(chosen))]
        lost, i = min(loss)
        if lost * STEP_MIN >= a.min_gain:
            break
        chosen.pop(i)
    chosen.sort(key=lambda c: (c[1] - (next(i for i in range(N) if not union[i]) if not all(union) else 0)) % N)
    if len(chosen) > a.max_sbs:
        print(f"WARNING: full coverage needs {len(chosen)} SBs; keeping the {a.max_sbs} with the widest ranges.")
        chosen = sorted(chosen, key=lambda c: -((c[2] - c[1]) % N))[:a.max_sbs]
        chosen.sort(key=lambda c: c[1])

    labels = {1: [''], 2: ['early', 'late'], 3: ['early', 'mid', 'late']}.get(len(chosen),
                                                                            [f'p{i + 1}' for i in range(len(chosen))])
    wraps = {1: [''], 2: ['CCW', 'CW'], 3: ['CCW', '', 'CW']}.get(len(chosen), [''] * len(chosen))
    base = f"{''.join(SHORT[b] for b in reversed(bands))}_{a.target}" + (f"_{a.epoch}" if a.epoch else '')
    comments = a.comments.replace(';', ',').strip()
    if len(chosen) > 1:
        link = "Please observe only 1 of the linked SBs depending on LST start time."
        comments = f"{comments} {link}".strip()
    os.makedirs(a.outdir, exist_ok=True)
    print(f"\nPLAN: {len(chosen)} SB(s), {fmt(total)} each, target+gain cal kept within {min_el:g}-{a.max_el:g} deg")
    written = []
    for (v, s, e), lab, wrap in zip(chosen, labels, wraps):
        lst = '00:00:00-23:59:00' if (s, e) == (0, N - 1) else f"{lst_str(s)}-{lst_str(e)}"
        name = base + (f"_{lab}" if lab else '')
        r = make_sb(a.target, a.catalog, a.config, bands, total, a.gain_cal, v['flux'], lst, sb_name=name, wrap=wrap,
                    comments=comments, weights=weights, flux_first=v['first'], selfcal=a.selfcal)
        path = os.path.join(a.outdir, name + '.optSB')
        with open(path, 'w') as f:
            f.write(r['text'])
        written.append(path)
        print(f"  {name:<34} LST start {lst}  flux {v['flux']} {'first' if v['first'] else 'last '}  "
              f"wrap {wrap or '-':<3}  on target {fmt(r['on_target'])}")
        budget(r, total, a.config, out=sys.stdout)
    n_union = sum(union)
    n_cov = len({(s + k) % N for _, s, e in chosen for k in range((e - s) % N + 1)} & {i for i in range(N) if union[i]})
    print(f"\nCOVERAGE: start LSTs covered {n_cov * STEP_MIN / 60:.1f} h of {n_union * STEP_MIN / 60:.1f} h possible "
          f"(target above {min_el:g} deg: {fcal.window(tgt, min_el)}; above {a.max_el:g}: {fcal.window(tgt, a.max_el)})")
    print("WROTE " + ' '.join(written))


if __name__ == '__main__':
    main()
