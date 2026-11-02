#!/usr/bin/env python3
"""Generate a VLA continuum scheduling block (OPT text format, VERSION 7) for one point-source target.

Resources and gain-cycle times are chosen from the array configuration (see TABLES below, derived
from the group's hand-written SBs); the time left after fixed overheads is split across bands.

Example
-------
  build_sb.py --target AT2026amv --catalog 26A-445 --config A --bands Ku --total 1h \\
      --gain-cal J0811+0146 --flux-cal 3C147 --lst 04:25:00-11:45:00 --wrap CCW \\
      --comments "First observation of TDE candidate AT2026amv." --out U_AT2026amv_e1.optSB
"""
import argparse
import datetime
import math
import os
import re
import sys

import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

# ---------------------------------------------------------------------------
# Tables (group practice; see references/strategy.md)
# ---------------------------------------------------------------------------
BAND_ORDER = ['Ka', 'K', 'Ku', 'X', 'C', 'S', 'L']          # blocks are emitted high -> low frequency
HIGH = {'Ku', 'K', 'Ka'}                                    # need X-band reference pointing
THREE_BIT = {'Ka', 'K', 'Ku', 'X', 'C'}                     # need a requantizer (Requant_*) scan
SHORT = {'Ka': 'A', 'K': 'K', 'Ku': 'U', 'X': 'X', 'C': 'C', 'S': 'S', 'L': 'L'}  # file-name letters

RESOURCES = {
    'A': {'L': 'L16f2A', 'S': 'S16f2A', 'C': 'C32f2Amixalt-blank', 'X': 'X32f2A',
          'Ku': 'Ku48f2A', 'K': 'K64f2A', 'Ka': 'Ka64f2A'},
    'B': {'L': 'L16f3B', 'S': 'S16f3B', 'C': 'C32f3Bmixalt-blank', 'X': 'X32f3DCB',
          'Ku': 'Ku48f3DCB', 'K': 'K64f3DCB', 'Ka': 'Ka64f3DCB'},
    'C': {'L': 'L16f5DC', 'S': 'S16f5DC', 'C': 'C32f5DC', 'X': 'X32f3DCB',
          'Ku': 'Ku48f3DCB', 'K': 'K64f3DCB', 'Ka': 'Ka64f3DCB'},
}
RESOURCES['D'] = dict(RESOURCES['C'])
UNVERIFIED = {('A', 'Ka')}   # never used in the group's SBs; confirm the name exists in the OPT

# Maximum on-target seconds between gain-calibrator scans (median of group SBs).
CYCLE = {
    'L':  {'A': 540, 'B': 480, 'C': 420, 'D': 420},
    'S':  {'A': 300, 'B': 390, 'C': 420, 'D': 420},
    'C':  {'A': 300, 'B': 300, 'C': 380, 'D': 380},
    'X':  {'A': 300, 'B': 330, 'C': 330, 'D': 330},
    'Ku': {'A': 260, 'B': 300, 'C': 350, 'D': 375},
    'K':  {'A': 195, 'B': 250, 'C': 250, 'D': 250},
    'Ka': {'A': 150, 'B': 200, 'C': 240, 'D': 240},
}
GAIN_SCAN = 60        # s, each gain-calibrator scan
REQUANT = 30          # s
SETUP_TOTAL = 600     # s, whole setup loop (first scan absorbs the initial slew)
SETUP_EACH = 60       # s, each additional attenuator setup scan
PTG_GAIN = 210        # s, X-band reference pointing on the gain calibrator
PTG_FLUX = 390        # s, X-band reference pointing on the flux calibrator (includes the long slew)
FLUX_SCAN, FLUX_REPS = 90, 2   # s x reps per band on the flux/bandpass calibrator
REPOINT = 3600        # s, max time at Ku/K/Ka after a reference pointing before re-pointing
REPOINT_SLACK = 900   # s, don't add a pointing just to cover a short overrun
SLEW_RATE = 20.0      # deg/min (elevation; azimuth is 40 deg/min) for slew-absorbing scans


# NRAO dynamic-scheduling weather limits (obsguide/dynsched/weather-constraints):
# band: (max wind m/s, conservative API phase rms deg, self-cal API deg). None = any.
WEATHER = {
    'L': (None, None, None), 'S': (None, 60, 120), 'C': (None, 45, 90), 'X': (15, 30, 60),
    'Ku': (10, 15, 30), 'K': (7, 10, 20), 'Ka': (6, 7, 14),
}
ANY_VALUE = 100.0     # what the group enters in the OPT for "any" (e.g. w=100.0 for C band)


def weather_limits(bands, selfcal=False):
    """Strictest limits over the bands in the SB (the whole SB runs under one constraint)."""
    winds = [WEATHER[b][0] for b in bands if WEATHER[b][0] is not None]
    apis = [WEATHER[b][2 if selfcal else 1] for b in bands if WEATHER[b][1] is not None]
    return (min(winds) if winds else ANY_VALUE), (min(apis) if apis else ANY_VALUE)


def fmt(sec):
    sec = int(round(sec))
    return f"{sec // 3600}h {sec % 3600 // 60}m {sec % 60}s"


def parse_total(s):
    s = s.strip().lower()
    if re.fullmatch(r'[\d.]+', s):
        return float(s) * 3600 if float(s) < 12 else float(s) * 60   # bare number: hours if <12 else minutes
    m = re.fullmatch(r'(?:([\d.]+)h)?\s*(?:([\d.]+)m(?:in)?)?', s)
    if not m or not any(m.groups()):
        sys.exit(f"Cannot parse --total {s!r}; use e.g. 1h30m, 90m, 1.5")
    return float(m.group(1) or 0) * 3600 + float(m.group(2) or 0) * 60


def cal_coord(name):
    cals = pd.read_csv(os.path.join(DATA, 'calibrators.csv'))
    col = 'ALT.NAME' if name.upper().startswith('3C') else 'IAU FULL NAME'
    hit = cals[cals[col] == name]
    if hit.empty:
        sys.exit(f"Calibrator {name} not in data/calibrators.csv ({col}). Use the J2000 name, e.g. J0811+0146, or 3C48.")
    r = hit.iloc[0]
    return SkyCoord(r['ra'], r['dec'], unit=(u.hourangle, u.deg))


def slew_scan_dur(sep_deg):
    """Duration for a scan that starts with a slew of `sep_deg`, leaving ~30 s on source."""
    return max(60, int(math.ceil((sep_deg / SLEW_RATE * 60 + 30) / 15.0)) * 15)


# ---------------------------------------------------------------------------
class SB:
    def __init__(self):
        self.lines, self.scans = [], []   # scans: (kind, source, seconds, reps)
        self.indent, self.reps = 1, [1]

    def loop(self, name, n=1):
        self.lines.append('  ' * self.indent + f"LOOP-START; {name}; {n}; N; ;")
        self.indent += 1
        self.reps.append(self.reps[-1] * n)

    def end(self):
        self.indent -= 1
        self.reps.pop()
        self.lines.append('  ' * self.indent + "LOOP-END;")

    def std(self, name, src, res, sec, intent, wrap='', ptgcorr='N'):
        self.lines.append('  ' * self.indent +
                          f"STD; {name}; {src}; {res}; DUR; {fmt(sec)}; {wrap}; {ptgcorr}; N; N; N; Y; N; N; {intent}; ;")
        self.scans.append((intent, src, sec, self.reps[-1]))

    def ptg(self, name, src, sec, wrap=''):
        self.lines.append('  ' * self.indent + f"PTG; {name}; {src}; X-point; DUR; {fmt(sec)}; {wrap}; N; N; N; N; Y; Y;")
        self.scans.append(('PTG', src, sec, self.reps[-1]))

    def blank(self):
        self.lines.append('')

    def total(self):
        return sum(s * r for _, _, s, r in self.scans)


def make_sb(target, catalog, config, bands, total, gain_cal, flux_cal, lst, sb_name=None, wrap='',
            az_start=None, el_start=35.0, wind=None, api=None, selfcal=False, comments='', weights=None,
            flux_first=False):
    """Build one SB. Returns dict(text, name, total, on_target, overhead, plan, res, notes).
    total is in seconds; bands is a list; weights a {band: weight} dict."""
    bands = [b for b in BAND_ORDER if b in bands]
    if not re.fullmatch(r'(\d\d:\d\d:\d\d-\d\d:\d\d:\d\d)(, ?\d\d:\d\d:\d\d-\d\d:\d\d:\d\d)*', lst):
        raise ValueError("lst must look like 04:25:00-11:45:00")
    res = {b: RESOURCES[config][b] for b in bands}
    high = any(b in HIGH for b in bands)
    pc = 'Y' if high else 'N'           # apply reference-pointing corrections on all scans when pointing is done
    w = {b: 1.0 for b in bands}
    w.update(weights or {})
    name = sb_name or f"{''.join(SHORT[b] for b in reversed(bands))}_{target}"   # group style: LSCX_<target>
    az = az_start if az_start is not None else {'CCW': -85.0, 'CW': 445.0, '': 180.0}[wrap]
    dw, da = weather_limits(bands, selfcal)
    wind = dw if wind is None else wind
    api = da if api is None else api
    gc, fc = cal_coord(gain_cal), cal_coord(flux_cal)
    gf_sep = gc.separation(fc).deg
    notes = []

    def flux_block(sb, preceded_by_slew):
        sb.loop('BP_FLUX')
        if high:
            sb.ptg('Xrefpnt_Fcal', flux_cal, max(PTG_FLUX, slew_scan_dur(gf_sep) + 150) if preceded_by_slew else 150)
        elif preceded_by_slew:
            sb.std('Slew_Fcal', flux_cal, res[bands[0]], slew_scan_dur(gf_sep), 'SetAtnGain,', ptgcorr=pc)
        for b in bands:
            if b in THREE_BIT:
                sb.std(f'Requant_{SHORT[b]}', flux_cal, res[b], REQUANT, 'SetAtnGain,', ptgcorr=pc)
            sb.loop(f'BP_FLUX_{SHORT[b]}', FLUX_REPS)
            sb.std('', flux_cal, res[b], FLUX_SCAN, 'CalBP,CalFlux,', ptgcorr=pc)
            sb.end()
        sb.end()
        sb.blank()

    def build(plan, pad=0):
        """plan: {band: (n_cycles, target_scan_seconds)}; n=0 gives a dry run of fixed overheads."""
        sb = SB()
        setup_src = flux_cal if flux_first else gain_cal
        setup_res = (['X-point'] if high else []) + [res[b] for b in bands]
        sb.loop('Setup Scans')
        first = max(SETUP_EACH, SETUP_TOTAL - SETUP_EACH * (len(setup_res) - 1))
        for i, r in enumerate(setup_res):
            label = 'Xref' if r == 'X-point' else SHORT[next(b for b in bands if res[b] == r)]
            sb.std(f'Dummy_{label}', setup_src, r, first + pad if i == 0 else SETUP_EACH, 'SetAtnGain,', wrap=wrap)
        sb.end()
        sb.blank()
        if flux_first:
            flux_block(sb, preceded_by_slew=False)
        if high:
            sb.ptg('Xrefpnt_phase', gain_cal, PTG_GAIN + (slew_scan_dur(gf_sep) if flux_first else 0))
        elif flux_first:
            sb.std('Slew_Gcal', gain_cal, res[bands[0]], slew_scan_dur(gf_sep), 'SetAtnGain,', ptgcorr=pc)
        since_ptg, repoints = 0, 0
        for b in bands:
            n, tdur = plan[b]
            cyc = tdur + GAIN_SCAN
            sb.loop(f'{SHORT[b]}-phase-target cycle')
            if b in THREE_BIT:
                sb.std(f'Requant_{SHORT[b]}', gain_cal, res[b], REQUANT, 'SetAtnGain,', ptgcorr=pc)
            sb.std('', gain_cal, res[b], GAIN_SCAN, 'CalGain,', ptgcorr=pc)
            since_ptg += GAIN_SCAN
            left, chunk = n, 0
            while left:
                k = left
                if b in HIGH and since_ptg + k * cyc > REPOINT + REPOINT_SLACK:
                    k = max(1, (REPOINT - since_ptg) // cyc) if since_ptg + cyc <= REPOINT else 0
                if k:
                    chunk += 1
                    sb.loop(f'target_{SHORT[b]}_loop' + (f'_{chunk}' if chunk > 1 else ''), k)
                    sb.std('', target, res[b], tdur, 'ObsTgt,', ptgcorr=pc)
                    sb.std('', gain_cal, res[b], GAIN_SCAN, 'CalGain,', ptgcorr=pc)
                    sb.end()
                    left -= k
                    since_ptg += k * cyc
                if left:   # re-point on the gain calibrator, then re-set the requantizers
                    sb.ptg(f'Xrefpnt_phase_{repoints + 2}', gain_cal, PTG_GAIN)
                    if b in THREE_BIT:
                        sb.std(f'Requant_{SHORT[b]}', gain_cal, res[b], REQUANT, 'SetAtnGain,', ptgcorr=pc)
                    since_ptg, repoints = 0, repoints + 1
            sb.end()
            sb.blank()
        if not flux_first:
            flux_block(sb, preceded_by_slew=True)
        sb.repoints = repoints
        return sb

    fixed = build({b: (0, 0) for b in bands}).total()
    wsum = sum(w[b] for b in bands)
    extra = 0
    for _ in range(4):        # iterate: extra pointings eat into the target time
        remain = total - fixed - extra
        if remain < 120 * len(bands):
            raise ValueError(f"Total {fmt(total)} is too short: overheads are {fmt(fixed + extra)} for bands "
                             f"{bands}. Ask for more time or fewer bands.")
        plan = {}
        for b in bands:
            rb = remain * w[b] / wsum
            per = CYCLE[b][config] + GAIN_SCAN
            n = max(1, math.ceil(rb / per))
            plan[b] = (n, max(30, int(round((rb / n - GAIN_SCAN) / 5.0)) * 5))
        sb = build(plan)
        new_extra = sb.total() - fixed - sum(n * (t + GAIN_SCAN) for n, t in plan.values())
        if new_extra == extra:
            break
        extra = new_extra
    # hit the requested length exactly: the first setup scan (which absorbs the initial slew) takes up the rounding
    diff = int(round(total - sb.total()))
    if diff:
        first0 = max(SETUP_EACH, SETUP_TOTAL - SETUP_EACH * (len(bands) + (1 if high else 0) - 1))
        if first0 + diff < SETUP_EACH:
            raise ValueError(f"cannot fit {fmt(total)} exactly (off by {diff} s); report this as a bug")
        sb = build(plan, pad=diff)
    if int(round(total)) % 1800:
        notes.append(f"requested length {fmt(total)} is not a whole or half hour; the group submits 0.5 h multiples")
    if sb.repoints:
        notes.append(f"added {sb.repoints} extra X-band reference pointing(s) so no more than "
                     f"{REPOINT // 60} min is spent at Ku/K/Ka after a pointing")
    for b in bands:
        if (config, b) in UNVERIFIED:
            notes.append(f"WARNING: resource {res[b]} has not been used in group SBs; confirm it exists in the OPT.")
    if ANY_VALUE in (wind, api):
        notes.append(f"weather: 'any' entered as {ANY_VALUE:g} (as in group C-band SBs)")

    header = [
        "VERSION; 7;", "",
        f" SRC-CAT; VLA, {catalog};",
        "HDWR-CAT; NRAO Defaults;", "",
        f"SCHED-BLOCK; {name}; Dynamic; 1; {datetime.date.today()} 00:00:00,2099-12-31 23:59:59; {lst}, ; 3.0; "
        f"{config}; {az:.1f}; {el_start:.1f}; N; N; w={wind:.1f},p={api:.1f}; {comments}; ", "",
    ]
    text = '\n'.join(header + sb.lines).rstrip() + '\n'
    on_t = sum(s * r for k, _, s, r in sb.scans if k == 'ObsTgt,')
    return dict(text=text, name=name, total=sb.total(), on_target=on_t, overhead=sb.total() - on_t, plan=plan,
                res=res, notes=notes, gf_sep=gf_sep, wind=wind, api=api, bands=bands)


def budget(r, requested, config, out=sys.stderr):
    print(f"\nTIME BUDGET for {r['name']} ({config} config, {','.join(r['bands'])})", file=out)
    print(f"  requested {fmt(requested)}   generated {fmt(r['total'])}   on target {fmt(r['on_target'])} "
          f"({100 * r['on_target'] / r['total']:.0f}%)   weather w={r['wind']:g},p={r['api']:g}", file=out)
    for b in r['bands']:
        n, tdur = r['plan'][b]
        print(f"  {b:<3} {r['res'][b]:<20} {n} x {fmt(tdur)} on target (cycle limit {CYCLE[b][config]} s) "
              f"= {fmt(n * tdur)}", file=out)
    for n in r['notes']:
        print(f"  NOTE: {n}", file=out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--target', required=True, help='target name exactly as in the OPT source catalog')
    ap.add_argument('--catalog', required=True, help='OPT source catalog name (e.g. the project code 26A-445)')
    ap.add_argument('--config', required=True, choices=list('ABCD'))
    ap.add_argument('--bands', required=True, help='comma list from L,S,C,X,Ku,K,Ka')
    ap.add_argument('--total', required=True, help='total SB length, e.g. 1h, 1h30m, 90m')
    ap.add_argument('--gain-cal', required=True)
    ap.add_argument('--flux-cal', required=True, help='3C48, 3C138, 3C147 or 3C286')
    ap.add_argument('--lst', required=True, help='LST start range HH:MM:SS-HH:MM:SS')
    ap.add_argument('--sb-name', help='default <bands>_<target>')
    ap.add_argument('--wrap', required=True, choices=['CW', 'CCW'],
                    help='antenna wrap for the setup scans (required by the OPT): CCW if the target is rising '
                         'during the SB, CW if setting')
    ap.add_argument('--az-start', type=float, help='default -85 (CCW), 445 (CW), 180 (no wrap)')
    ap.add_argument('--el-start', type=float, default=35.0)
    ap.add_argument('--wind', type=float, help='override; default from the NRAO table for the strictest band')
    ap.add_argument('--api', type=float, help='override; default from the NRAO table for the strictest band')
    ap.add_argument('--selfcal', action='store_true', help='target bright enough to self-calibrate: relaxed API limit')
    ap.add_argument('--comments', default='')
    ap.add_argument('--weights', default='', help='relative target time per band, e.g. X=2,C=1 (default equal)')
    ap.add_argument('--flux-first', action='store_true',
                    help='observe the flux/bandpass calibrator at the start instead of the end')
    ap.add_argument('--out', help='output .optSB path (default: print to stdout)')
    a = ap.parse_args()

    bands = [b.strip() for b in a.bands.split(',') if b.strip()]
    if any(b not in BAND_ORDER for b in bands):
        sys.exit(f"Unknown band in {bands}; use {BAND_ORDER}")
    weights = {k.strip(): float(v) for k, v in (kv.split('=') for kv in filter(None, a.weights.split(',')))}
    total = parse_total(a.total)
    try:
        r = make_sb(a.target, a.catalog, a.config, bands, total, a.gain_cal, a.flux_cal, a.lst, a.sb_name, a.wrap,
                    a.az_start, a.el_start, a.wind, a.api, a.selfcal, a.comments, weights, a.flux_first)
    except ValueError as e:
        sys.exit(str(e))
    if a.out:
        with open(a.out, 'w') as f:
            f.write(r['text'])
    else:
        print(r['text'])
    budget(r, total, a.config)
    if a.out:
        print(f"  wrote {a.out}", file=sys.stderr)


if __name__ == '__main__':
    main()
