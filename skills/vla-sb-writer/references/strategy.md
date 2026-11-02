# Continuum observing strategy (group practice + NRAO Guide to Observing)

`build_sb.py` and `plan_sbs.py` encode all of this. Read this file when you need to explain a choice, override a default, or decide something the script doesn't decide for you, such as calibrator choice, LST range, or band weights.

## Resources by configuration

These are the most-used resources in about 200 group SBs.

| band | A | B | C / D |
|---|---|---|---|
| L | L16f2A | L16f3B | L16f5DC |
| S | S16f2A | S16f3B | S16f5DC |
| C | C32f2Amixalt-blank | C32f3Bmixalt-blank | C32f5DC |
| X | X32f2A | X32f3DCB | X32f3DCB |
| Ku | Ku48f2A | Ku48f3DCB | Ku48f3DCB |
| K | K64f2A | K64f3DCB | K64f3DCB |
| Ka | Ka64f2A *(unverified, never used by the group)* | Ka64f3DCB | Ka64f3DCB |

- The C-band `mixalt-blank` resources in A and B configurations avoid the 6.2 and 6.4 GHz microwave links, as the NRAO guide recommends.
- `X-point` is the 8-bit X-band reference-pointing setup.
- C, X, Ku, K, and Ka are 3-bit or mixed resources. Each needs a 30 s requantizer scan (`Requant_<band>`, `SetAtnGain`) before use whenever the resource changes or after a `PTG`. The guide gives 10–30 s; the group uses 30 s.
- L and S are 8-bit and need no requantizer scan.

## Start-up sequence

- The first loop, `Setup Scans`, has one `SetAtnGain` scan per resource. Add `X-point` first if any band is Ku or above.
- All setup scans are on the first calibrator observed: the gain calibrator, or the flux calibrator when it is observed first.
- The first scan absorbs the initial slew, which can take up to 9 min. The whole loop is about 10 min, as the guide recommends (10–12 min).
- Each additional scan in the loop is 1 min.
- Set the antenna wrap on these scans, and only these. The NRAO guide says it may be left blank, but the group always sets CW or CCW.

## Reference pointing (Ku, K, Ka)

- Run `PTG` on the gain calibrator with `X-point` for 3m30s. It needs at least 2m30s on source.
- Run `PTG` on the flux calibrator for about 6m30s, because it also absorbs the long slew.
- Pointing solutions are valid for about 20° and about 1 hour (30–40 min in daytime). `build_sb.py` inserts another `PTG` on the gain calibrator, plus a requantizer scan, when more than about 1 h (plus 15 min slack) would pass at Ku/K/Ka without one.
- Avoid elevations above 80°.

## Gain-calibrator cycle

Each cycle is one gain scan of 60 s followed by at most this much time on target (seconds; medians of group SBs):

| | A | B | C | D |
|---|---|---|---|---|
| L | 540 | 480 | 420 | 420 |
| S | 300 | 390 | 420 | 420 |
| C | 300 | 300 | 380 | 380 |
| X | 300 | 330 | 330 | 330 |
| Ku | 260 | 300 | 350 | 375 |
| K | 195 | 250 | 250 | 250 |
| Ka | 150 | 200 | 240 | 240 |

These are shorter than the NRAO guide's limits (roughly 8–10 min at C/X and 4–6 min at K), which is conservative and fine. `build_sb.py` picks the number of cycles so that no cycle exceeds the limit.

## Calibrators

**Gain (complex gain) calibrator**
- Prefer code P, then S, in the requested configuration *and* every requested band. Avoid W, X, and `?`.
- The calibrator list has no S, K, or Ka columns, so `find_calibrators.py` uses the worse of L/C for S and of K/Ku/Q for K and Ka.
- Separation: within about 10° for Ku and above, about 15° for L to X. Closer is better at high frequency.
- The guide says to prefer a strong P calibrator farther away over a weak nearby S one.
- Flux should be at least a few hundred mJy. One calibrator for all bands keeps the SB simple; the group almost always does this.
- The same calibrator gets the X-band pointing, so it must be at least about 0.3 Jy and code P or S at X.

**Flux and bandpass calibrator**
- Use 3C48, 3C147, or 3C286. 3C138 is variable and flaring, so avoid it unless nothing else is up.
- It must be above about 30° elevation when it's observed:
  - at the start (`--flux-first`) if it is up at the LST start and sets later
  - otherwise at the end, if it rises during the SB
- 2 × 90 s per band (about 3 min) is enough for these bright sources.

## Weather limits (NRAO dynamic scheduling)

The source is https://science.nrao.edu/facilities/vla/docs/manuals/obsguide/dynsched/weather-constraints. The SB's `w=<wind>,p=<API>` field should carry the limits for the **most demanding band in the SB**. Limits stricter than needed only make the SB harder to schedule; limits looser than needed risk unusable data.

| band | max wind (m/s) | API phase rms, conservative (deg) | API, self-calibration (deg) |
|---|---|---|---|
| 4, P, L | any | any | any |
| S | any | 60 | 120 |
| C | any | 45 | 90 |
| X | 15 | 30 | 60 |
| Ku | 10 | 15 | 30 |
| K | 7 | 10 | 20 |
| Ka | 6 | 7 | 14 |
| Q | 5 | 5 | 10 |

"Any" is entered as 100, as in the group's C-band SBs (`w=100.0,p=45.0`). Use the self-calibration column (`--selfcal`) only when the target is bright enough to self-calibrate, roughly 0.1 Jy over a 1 GHz band.

## Linked early / late SBs

The goal is to maximize the LST range in which *some* SB can start, and the time on source. Split into linked SBs when no single SB can start across the whole usable window, because:
- the target or gain calibrator rises or sets partway through the window
- the target or a calibrator would pass above 80° during the SB; tracking near zenith is poor, so the SB must finish before transit (early) or start after it (late)
- the flux calibrator is up only at the start for some starts and only at the end for others; the variants then differ in whether the flux block is first or last, or in which 3C source they use

Group conventions:
- **at most two** SBs, with names ending `_early` and `_late`
- each is the full requested length, because only one runs
- a wrap is always set on the setup scans: CCW while the target is rising, CW once it is setting (usually early CCW, late CW)
- identical scans apart from the calibrator order
- comments say "Please observe only 1 of the linked SBs depending on LST start time."
- ranges may overlap; that is fine and gives the operators more options

Don't add the second SB for less than about 30 min of extra start range. Each SB is extra work to check, and the gain is small.

SB lengths are whole or half hours (1 h, 1.5 h, 2 h …). The generator pads or trims the first setup scan so the total comes out exactly right.

## LST start range

The range lists the *start* times for which the whole SB stays observable:
- start no earlier than when the target and gain calibrator rise above about 30° (35° in C and D configurations, where shadowing is a concern)
- start no later than (setting time − SB length)
- the flux calibrator must be above about 30° at the start (flux first) or at start + length (flux last)
- no source above 80° during the SB (calibrators only while they're observed)

`plan_sbs.py` applies all of these and splits into linked SBs when needed (see above).

## Elevation and shadowing

The guide recommends keeping elevations above 40° in D and above 25° in C where possible. Maximum elevation is roughly Dec + 56°. Sources south of about −30° can't avoid shadowing in compact configurations, so accept lower elevations and note it in the comments.
