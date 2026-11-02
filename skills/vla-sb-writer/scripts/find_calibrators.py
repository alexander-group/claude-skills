#!/usr/bin/env python3
"""Find VLA gain (phase) calibrators near a target and report LST visibility.

Ported from obstools/sb-helper/setup.py (print_pcals / print_availability),
reading the bundled copy of the VLA calibrator list in ../data/. No network access needed.

Examples
--------
  find_calibrators.py --ra 08:11:26.7 --dec +01:46:52 --config A --bands Ku
  find_calibrators.py --name AT2022hvp --config B --bands L,S,C,X      # uses $TNS_CATALOG
  # once a gain calibrator is chosen, get LST start ranges for a 1.5 h SB:
  find_calibrators.py --ra ... --dec ... --config A --bands Ku --gain-cal J0811+0146 --length 1.5
"""
import argparse
import math
import os
import re
import sys

import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
VLA_LAT = 34.0784  # deg
VLA_LON = -107.6184  # deg (not needed for elevation-vs-LST, kept for reference)

# Which calibrator-list band(s) to consult for each VLA observing band. The list has no
# S, K (mostly) or Ka entries, so those use the neighbouring bands (worst code wins).
BAND_LOOKUP = {
    'L': ['L'], 'S': ['L', 'C'], 'C': ['C'], 'X': ['X'],
    'Ku': ['U'], 'K': ['K', 'U', 'Q'], 'Ka': ['K', 'Q'],
}
CODE_RANK = {'P': 0, 'S': 1, 'W': 2, 'C': 2, 'X': 3, '?': 4}
FLUX_CALS = {'3C48': 'J0137+3309', '3C138': 'J0521+1638', '3C147': 'J0542+4951', '3C286': 'J1331+3030'}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def to_skycoord(ra, dec):
    """RA/Dec as sexagesimal strings (hourangle / deg) or decimal degrees."""
    try:
        return SkyCoord(float(ra) * u.deg, float(dec) * u.deg, frame='icrs')
    except ValueError:
        return SkyCoord(str(ra), str(dec), unit=(u.hourangle, u.deg), frame='icrs')


def load_catalog():
    cals = pd.read_csv(os.path.join(DATA, 'calibrators.csv'))
    coords = SkyCoord(ra=cals['ra'].values, dec=cals['dec'].values, unit=(u.hourangle, u.deg), frame='icrs')
    return cals, coords


def load_band_tables():
    """Parse vla-calibrators-2.txt -> {IAU NAME (J2000 B-name): {band_letter: (codes 'ABCD', flux)}}."""
    tables, cur = {}, None
    band_re = re.compile(r'^\s*[\d.]+cm\s+([A-Z])\s+([PSWXC?])\s+([PSWXC?])\s+([PSWXC?])\s+([PSWXC?])\s+([\d.]+)?')
    with open(os.path.join(DATA, 'vla-calibrators-2.txt')) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == 'J2000':
                cur = parts[0]
                tables[cur] = {}
                continue
            m = band_re.match(line)
            if m and cur:
                flux = float(m.group(6)) if m.group(6) else None
                tables[cur][m.group(1)] = (''.join(m.group(i) for i in range(2, 6)), flux)
    return tables


def lookup_tns(name):
    """Resolve a transient name from the CSV at $TNS_CATALOG. Returns (ra, dec) strings/floats or None."""
    path = os.environ.get('TNS_CATALOG')
    if not path or not os.path.exists(path):
        sys.exit(f"--name given but $TNS_CATALOG is not set or missing ({path!r}). Pass --ra/--dec instead.")
    df = pd.read_csv(path, comment=None, low_memory=False)
    if len(df.columns) == 1:  # TNS public dumps have a date line before the header
        df = pd.read_csv(path, skiprows=1, low_memory=False)
    cols = {c.lower(): c for c in df.columns}
    ncol = cols.get('name') or cols.get('objname')
    racol = cols.get('ra')
    deccol = cols.get('dec') or cols.get('declination')
    if not (ncol and racol and deccol):
        sys.exit(f"Could not find name/ra/dec columns in {path}: {list(df.columns)}")
    key = re.sub(r'^(AT|SN|TDE|FRB|KN)\s*', '', name.strip(), flags=re.I).lower()
    names = df[ncol].astype(str).str.strip()
    stripped = names.str.replace(r'^(AT|SN|TDE|FRB|KN)\s*', '', regex=True, case=False).str.lower()
    hit = df[(names.str.lower() == name.strip().lower()) | (stripped == key)]
    if hit.empty:
        sys.exit(f"{name} not found in {path}. Ask the user for RA/Dec.")
    row = hit.iloc[0]
    return row[racol], row[deccol]


# ---------------------------------------------------------------------------
# Visibility (analytic elevation vs LST; equivalent to setup.get_elevations without astropy times)
# ---------------------------------------------------------------------------
def elevation(lst_h, ra_deg, dec_deg):
    ha = math.radians((lst_h * 15.0 - ra_deg))
    lat, dec = math.radians(VLA_LAT), math.radians(dec_deg)
    return math.degrees(math.asin(math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha)))


def hms(h):
    h %= 24
    return f"{int(h):02d}:{int(h * 60 % 60):02d}"


def window(coord, thresh):
    """LST interval (rise, set) above `thresh` deg, handling wrap through 0h. 'always'/'never' otherwise."""
    step = 1 / 60
    grid = [i * step for i in range(int(24 / step))]
    above = [elevation(t, coord.ra.deg, coord.dec.deg) > thresh for t in grid]
    if all(above):
        return 'always'
    if not any(above):
        return 'never'
    n = len(grid)
    rise = next(grid[i] for i in range(n) if above[i] and not above[i - 1])
    set_ = next(grid[i] for i in range(n) if not above[i] and above[i - 1])
    return f"{hms(rise)}-{hms(set_)}"


def transit_el(coord):
    return 90 - abs(VLA_LAT - coord.dec.deg)


# ---------------------------------------------------------------------------
def start_ranges(coords_all, length_h, min_el, flux_coord, flux_at):
    """Contiguous LST start ranges where every coord in coords_all stays above min_el for the whole SB
    and the flux calibrator is above min_el at the start (flux_at='start') or end ('end')."""
    step = 1 / 60
    ok = []
    for i in range(int(24 / step)):
        t0 = i * step
        times = [t0 + k * length_h / 20 for k in range(21)]
        good = all(elevation(t, c.ra.deg, c.dec.deg) >= min_el for c in coords_all for t in times)
        tf = t0 if flux_at == 'start' else t0 + length_h
        good &= elevation(tf, flux_coord.ra.deg, flux_coord.dec.deg) >= min_el
        ok.append(good)
    n = len(ok)
    if all(ok):
        return ['00:00:00-23:59:00 (any)']
    out = []
    for i in range(n):
        if ok[i] and not ok[i - 1]:
            j = i
            while ok[(j + 1) % n]:
                j = (j + 1) % n
            out.append(f"{hms(i * step)}:00-{hms(j * step)}:00")
    return out


def band_code(table, band, config):
    """Worst code over the catalog bands consulted for `band`, in `config` ('A','B','C','D' or 'Any')."""
    cfgs = 'ABCD' if config in ('Any', '') else config
    worst, flux, seen = None, None, False
    for b in BAND_LOOKUP[band]:
        if b not in table:
            continue
        seen = True
        codes, fl = table[b]
        for c in cfgs:
            code = codes['ABCD'.index(c)]
            if worst is None or CODE_RANK[code] > CODE_RANK[worst]:
                worst = code
        if fl is not None:
            flux = fl if flux is None else min(flux, fl)
    return (worst if seen else '-'), flux


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ra'); ap.add_argument('--dec'); ap.add_argument('--name')
    ap.add_argument('--config', default='Any', help='A, B, C, D or Any')
    ap.add_argument('--bands', required=True, help='comma list from L,S,C,X,Ku,K,Ka')
    ap.add_argument('--radius', type=float, default=None,
                    help='search radius deg (default 10 if any band >= Ku, else 15)')
    ap.add_argument('--max', type=int, default=12, help='max candidates to print')
    ap.add_argument('--gain-cal', help='chosen gain calibrator (J name); with --length, print LST start ranges')
    ap.add_argument('--length', type=float, help='SB length in hours, for LST start ranges')
    ap.add_argument('--min-el', type=float, default=30.0, help='minimum elevation for LST start ranges')
    ap.add_argument('--all', action='store_true', help='also list calibrators with no data in the requested bands')
    a = ap.parse_args()

    bands = [b.strip() for b in a.bands.split(',') if b.strip()]
    bad = [b for b in bands if b not in BAND_LOOKUP]
    if bad:
        sys.exit(f"Unknown band(s) {bad}; use {list(BAND_LOOKUP)}")
    if a.name and not (a.ra and a.dec):
        ra, dec = lookup_tns(a.name)
        print(f"TNS lookup: {a.name} -> RA {ra}  Dec {dec}")
    elif a.ra and a.dec:
        ra, dec = a.ra, a.dec
    else:
        sys.exit("Give --ra and --dec, or --name with $TNS_CATALOG set.")
    tgt = to_skycoord(ra, dec)
    high = any(b in ('Ku', 'K', 'Ka') for b in bands)
    radius = a.radius or (10.0 if high else 15.0)

    cals, coords = load_catalog()
    tables = load_band_tables()
    sep = tgt.separation(coords).deg

    print(f"\nTARGET  {tgt.to_string('hmsdms', sep=':', precision=2)}   (deg {tgt.ra.deg:.4f} {tgt.dec.deg:+.4f})")
    print(f"  transit elevation {transit_el(tgt):.0f} deg;  LST above 15: {window(tgt, 15)}  "
          f"above 30: {window(tgt, 30)}  above 80: {window(tgt, 80)}")

    print(f"\nGAIN CALIBRATOR CANDIDATES within {radius:g} deg  (config {a.config}; codes P best, S ok, W/X avoid)")
    hdr = f"{'name':<12} {'sep':>5} {'PC':>2} " + ' '.join(f"{b + ' code/Jy':>13}" for b in bands) + '  usable'
    print(hdr); print('-' * len(hdr))
    near = cals.assign(sep=sep)[sep <= radius].sort_values('sep')
    shown = 0
    for _, row in near.iterrows():
        table = tables.get(row['IAU NAME'], {})
        if not a.all and all(band_code(table, b, a.config)[0] == '-' for b in bands):
            continue
        cells, ok = [], True
        for b in bands:
            code, flux = band_code(table, b, a.config)
            cells.append(f"{code}/{flux if flux is not None else '?':>5}")
            ok &= code in ('P', 'S')
        print(f"{row['IAU FULL NAME']:<12} {row['sep']:5.1f} {row['PC']:>2} " + ' '.join(f"{c:>13}" for c in cells)
              + ('  YES' if ok else '  no'))
        shown += 1
        if shown >= a.max:
            break
    if shown == 0:
        print("  none - rerun with a larger --radius")

    print("\nFLUX / BANDPASS CALIBRATORS")
    for alt, jname in FLUX_CALS.items():
        idx = cals.index[cals['ALT.NAME'] == alt]
        c = coords[idx[0]] if len(idx) else None
        if c is None:
            continue
        print(f"  {alt:<6} ({jname})  sep {tgt.separation(c).deg:5.1f} deg  "
              f"LST above 30: {window(c, 30):<13} above 15: {window(c, 15):<13} above 80: {window(c, 80)}")

    if a.gain_cal and a.length:
        gi = cals.index[cals['IAU FULL NAME'] == a.gain_cal]
        if not len(gi):
            sys.exit(f"gain calibrator {a.gain_cal} not in calibrators.csv")
        gcoord = coords[gi[0]]
        print(f"\nLST START RANGES for a {a.length:g} h SB (target + {a.gain_cal} above {a.min_el:g} deg throughout)")
        for alt in FLUX_CALS:
            fc = coords[cals.index[cals['ALT.NAME'] == alt][0]]
            for when in ('start', 'end'):
                r = start_ranges([tgt, gcoord], a.length, a.min_el, fc, when)
                print(f"  {alt:<6} at {when:<5}: {', '.join(r) if r else 'none'}")
        if window(tgt, 80) != 'never':
            print(f"  note: target is above 80 deg during LST {window(tgt, 80)}; avoid long scans there.")


if __name__ == '__main__':
    main()
