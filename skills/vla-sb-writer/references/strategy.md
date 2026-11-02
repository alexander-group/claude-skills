# Continuum observing strategy (group practice + NRAO Guide to Observing)

`build_sb.py` encodes all of this. Read this file when you need to explain a choice, override a default, or decide something the script doesn't decide for you, such as calibrator choice, LST range, or band weights.

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
- Set the antenna wrap only on these scans. The guide says to leave the wrap blank when in doubt, because NRAO staff will set it.

## Reference pointing (Ku, K, Ka)

- Run `PTG` on the gain calibrator with `X-point` for 3m30s. It needs at least 2m30s on source.
- Run `PTG` on the flux calibrator for about 6m30s, because it also absorbs the long slew.
- Pointing solutions are valid for about 20° and about 1 hour (30–40 min in daytime). If more than 1 h is spent at Ku/K/Ka, consider a second `PTG` on the gain calibrator.
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

## LST start range

The range lists the *start* times for which the whole SB stays observable:
- start no earlier than when the target and gain calibrator rise above about 30° (35° in C and D configurations, where shadowing is a concern)
- start no later than (setting time − SB length)
- the flux calibrator must be above about 30° at the start (flux first) or at start + length (flux last)
- avoid any LST where the target is above 80°, because of fast azimuth slews near zenith

If the window is too narrow, or two LST regions need opposite wraps, write two linked SBs (`_early` and `_late`) and say so in the comments: "Please observe only 1 of the linked SBs depending on LST start time."

## Elevation and shadowing

The guide recommends keeping elevations above 40° in D and above 25° in C where possible. Maximum elevation is roughly Dec + 56°. Sources south of about −30° can't avoid shadowing in compact configurations, so accept lower elevations and note it in the comments.
