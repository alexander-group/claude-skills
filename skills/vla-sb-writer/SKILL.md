---
name: vla-sb-writer
description: Write VLA (Very Large Array) scheduling blocks (SBs) for continuum observations of point-source targets such as TDEs, GRBs, SNe and FBOTs, as OPT text-format .optSB files that pass OPT validation. Handles any mix of L, S, C, X, Ku, K and Ka bands in A, B, C or D configuration. It picks gain and flux calibrators from the bundled VLA calibrator list, sets resources, cycle times and NRAO weather limits for the configuration and bands, and fits scans into a requested total time. It writes linked early/late SBs when needed to maximize the LST range the observation can start in and the time on source. Use this whenever someone asks to write, make, draft, generate or update a VLA SB, scheduling block, or OPT/optSB file, plans VLA radio follow-up of a transient, says "load the skill for writing VLA SBs", or needs a VLA phase calibrator or LST range for an SB, even if they don't say "scheduling block".
---

# VLA scheduling-block writer

## What a good SB set achieves

The whole point is to get the data. Two goals drive every decision below:

1. **Maximize the LST range in which the observation can start.** Dynamic scheduling only runs an SB when its LST start range, weather limits and priority line up. A narrow window, or limits stricter than needed, can leave a time-critical source unobserved for days.
2. **Maximize time on source** within the requested total time. Overheads include setup, slews, pointing, requantizer scans and calibrators; spend only what calibration needs.

A single SB often can't satisfy both. The target or gain calibrator may set partway through. A calibrator may pass above 80° (the antennas can't track well near zenith). The flux calibrator may be up only at the start or only at the end. The group then writes **two linked SBs, early and late** (never more than two), which are copies with different LST start ranges and typically:
- a different flux calibrator, or the flux calibrator moved between first and last
- opposite antenna wraps

Together they cover as much of the usable start LST as possible. Only one of them will ever run (the comments tell the operators so), so **each linked SB is the full requested length**; never split the time between them. `plan_sbs.py` makes this choice for you: it picks the single SB, or early/late pair, with the most start-LST coverage, preferring variants with more time on source.

## Tools

Scripts live in `scripts/` next to this file. Run them by their full path from the user's working directory (e.g. `python <this skill's directory>/scripts/plan_sbs.py ...`), so the `.optSB` files land where the user wants them. The commands below write `scripts/` for short. They need Python 3.8+ with numpy, pandas and astropy, and read the bundled calibrator list in `data/`. If an import fails, tell the user to run `pip install -r <skill dir>/requirements.txt`.

| script | does |
|---|---|
| `find_calibrators.py` | lists gain-calibrator candidates (codes and flux per band and configuration), plus target and flux-calibrator visibility; looks up names in `$TNS_CATALOG` |
| `plan_sbs.py` | **main path:** chooses single vs early/late, flux calibrator and placement, wrap, and LST ranges; writes the SB file(s) via `build_sb.py`; prints budgets and coverage |
| `build_sb.py` | builds one SB with explicit choices; use it when you need to override the planner |
| `check_sb.py` | static checker; run it on every file before handing it over |

For the field-by-field file format, see `references/sb-format.md`. For the reasoning behind resources, cycle times, the weather table, calibrator criteria and LST rules, see `references/strategy.md`. Real group SBs are in `references/examples/`.

## 1. Collect the inputs

You need all six of these. Ask for whichever are missing, in one message, rather than guessing:

1. **Target name** exactly as it appears in the OPT source catalog. A mismatch fails validation.
2. **Source catalog name**, usually the project code (e.g. `26A-445`).
3. **Total SB time**, e.g. "1h", "1.5 h", "90 min". The group submits only whole or half-hour SBs, and the scripts hit the requested length to the second. If someone asks for a length that isn't a multiple of 30 min, confirm which half hour they want. This is the length of *each* SB; linked SBs don't share it.
4. **Bands**: any of L, S, C, X, Ku (also called U), K, Ka.
5. **RA/Dec**. If the user gives only a transient name, use `--name`, which reads `$TNS_CATALOG`. If that is unset or the name isn't found, ask for coordinates.
6. **Array configuration**: A, B, C or D. If they say "Any", ask which configuration the SB will run in.

Optional inputs:
- epoch label for the file name (e.g. `e3`)
- comments to the operators
- band weights, if some bands need more time
- whether the target is bright enough to self-calibrate (about 0.1 Jy or more over a 1 GHz band), which allows the relaxed API limit with `--selfcal`

## 2. Choose the gain calibrator

```bash
python scripts/find_calibrators.py --ra <RA> --dec <Dec> --config <cfg> --bands <comma list>
```

Choose **one gain calibrator for all bands**:
- coded P or S in this configuration for every band (the output marks these "usable YES"). P and S are equally acceptable.
- **the closest usable candidate, above all else**: within about 10° if any band is Ku or above, about 15° otherwise
- flux of at least a few hundred mJy
- for Ku and above, also P or S at X band (at least about 0.3 Jy), because it takes the X-band reference pointing. Check `data/vla-calibrators-2.txt`; a calibrator with no X row can't be used.

Separation outranks code and flux: never pick a P calibrator, or a brighter one, over a closer S calibrator. In one real case (Ku, C config), J0019+2021 (P, 1.1 Jy, 7.2°) was wrong. J2340+2641 (S, 0.4 Jy, 4.0°) was right. The equally close J2358+1955 had no X-band entry, so it couldn't take the pointing. Only when two usable candidates are at about the same separation, prefer the one whose elevation window better matches the target's. If the closest calibrator narrows the start-LST range (e.g. it passes above 80°), still use it, and tell the user how much start range it costs.

## 3. Plan and write the SBs

```bash
python scripts/plan_sbs.py --target <name> --catalog <catalog> --config <cfg> --bands <bands> \
    --total <time> --ra <RA> --dec <Dec> --gain-cal <J name> --epoch <eN> \
    --comments "<note to operators>" --outdir <dir>
```

The planner does the following:
- Tries each flux calibrator (3C286, 3C147 and 3C48, plus 3C138 only as a last resort), observed either first or last.
- For each variant, finds every start LST where the target and gain calibrator stay between the minimum elevation and 80° for the whole SB, and the flux calibrator is in that range while it is observed. The default minimum is 30°, or 35° in C and D configurations to limit shadowing.
- Picks one SB, or an early/late pair, with the most start-LST coverage; ties go to more time on source. A second SB is added only if it gains at least 30 min of start range (`--min-gain`). The group's limit is two (`--max-sbs 2`), so don't raise it unless the user asks.
- Sets an antenna wrap on every SB, because the group always gives one: CCW if the target is rising during the SB, CW if it is setting. For an early/late pair this is usually CCW/CW. The starting azimuth follows NRAO: 445 for CCW, −85 for CW. The setup loop is lengthened when needed to absorb the resulting initial slew.
- **The OPT's "suggested wrap" can be wrong.** NRAO says so, and its rules of thumb may not apply when sources are near declination 34° (the VLA's latitude), i.e. passing close to the zenith. In one real case, the target at Dec +35.6 and every calibrator were in the north-east, drifting toward azimuth 85° during the early SB. The OPT warned "CCW wrap requested. CW wrap is suggested", yet CW would have put them at ≈445°, right at the limit, and forced a 9-min unwind. When the OPT's suggestion conflicts with the wrap the planner chose, check the azimuth track of every source in the SB on both wraps across the LST start range. Keep whichever wrap stays clear of −85° and 445°. If that is not the OPT's suggestion, add a sentence to the operator comment saying the wrap is intentional and why.
- Writes `<bands>_<target>_<epoch>[_early|_late].optSB`. Each file is exactly the requested length, and linked SBs get the "observe only 1 of the linked SBs" note appended to the comments.

Each file contains:
- the configuration's resources
- gain-cycle times under the per-configuration limit
- NRAO weather limits for the strictest band in the SB
- X-band reference pointing for Ku and above, repeated about every hour
- 30 s requantizer scans
- the flux/bandpass block

**Read the plan output critically**:
- **Coverage.** "covered X h of Y h possible" should be close to the target's whole window. If the window is much shorter than the target's time above the elevation limit, a calibrator is the bottleneck, so try another gain calibrator.
- **Uncovered start LSTs.** Two SBs can't always cover everything; the planner prints a NOTE when they don't. Say how much is lost and why, e.g. "3C286 is above 80° at LST 12:47–14:16". A shorter total time often covers more, so you can suggest it, but don't change the user's total on your own.
- **No valid start.** If the planner reports none, it also gives the longest SB that fits. Tell the user, and offer to shorten the SB, lower `--min-el`, or split it into separate SBs.

Write a comment if the user gave none. One sentence in the group's style covers what the source is, why it's time-sensitive, and the cadence request, e.g. "Third epoch of TDE AT2024zau. Please observe within the next week if possible, or ASAP thereafter." Don't use `;`, because it is the field separator.

Use `build_sb.py` directly only to override a planner choice, e.g. a specific LST range or flux calibrator the user asked for. It takes the same options plus `--flux-cal`, `--lst`, `--flux-first` and `--wrap` (required: CW or CCW). Hand-edit generated text only for things neither script can express, such as per-band gain calibrators or polarization calibration, and re-run the checker afterwards.

**Hand edits must respect OPT's on-source minimums.** `DUR` includes the slew, so moving a scan to a different source changes its time on source even though its duration stays the same. OPT warns when time on source falls below:
- 20 s for `CalGain` scans
- 2m30s for `PTG` scans; pointing setup takes about 20 s even with no slew, so never use a `PTG` shorter than 3m0s, and use 3m30s by default

**The setup loop must absorb the initial slew.** This matters most when hand-editing or adapting a user's SB, e.g. one that starts with a polarization-leakage block on a different calibrator. The OPT slews from the SCHED-BLOCK starting azimuth (−85 or 445) on the chosen wrap, and the swing can be about 400°, or about 10 min. Any overrun comes out of the first `PTG`. Shortening a user's setup loop, e.g. from 10 min to 9 min when dropping a band's dummy scan, can push that `PTG` below 2m30s on source. `check_sb.py` computes the worst-case slew across the LST start range and reports an ERROR when this happens. Lengthen the first setup scan, not the `PTG`, and take the time from the target scans.

When you give a band its own gain calibrator, lengthen every `CalGain` scan that follows a target scan to cover the slew plus at least 20 s, with margin. In one real case, a calibrator 9° from the target took about 44 s to slew to, so 1m0s scans got only about 16 s on source and 1m20s scans fixed it. Plan for about 5 s per degree of separation, plus 40 s. To keep the SB exactly the requested length, take the extra time from that band's target scans, then re-run the checker.

**Long slews to a flux calibrator at the end of the SB.** The planner estimates slews from angular separation. OPT's slew time is set by the azimuth swing (40°/min), which is much larger when the target is setting in the west and the flux calibrator is rising in the north-east. In one real case, a target at RA 01h, Dec +13 with 3C147 last on the CW wrap needed up to 4m37s to slew, so the planner's 6m30s `Xrefpnt_Fcal` left only 1m52s on source. Before handing over an SB with the flux calibrator last:
- estimate the worst-case azimuth swing across the start range
- make the `PTG` at least the slew plus 2m30s, plus about 20 s of margin (7m30s in that case)
- take the extra time from the target scans

OPT also warns when a single slew takes more than 4m30s. Tell the user about this rather than silently accepting it. To avoid it, put the flux calibrator first, or choose a flux calibrator closer in azimuth to the target.

## 4. Check

```bash
python scripts/check_sb.py <dir>/*.optSB --target <name> --catalog <catalog> --expect <total>
```

Fix every ERROR. Read the WARNs; a weather limit stricter or looser than the NRAO table is one example. The checker can't see the OPT's source catalog, slew model or hardware database, so the user's OPT import and validation remain the final test. It models only the initial slew into the setup loop, using the OPT's 40°/min azimuth rate. It does not model slews between later scans, so it can't catch those scans when their time on source falls below OPT's minimums (see the hand-edit note in step 3). It also flags OPT export placeholders left in `HDWR-CAT` and LST start minutes that aren't multiples of 5, both of which the OPT rejects. After any hand edit, check every scan that now starts with a new or longer slew.

## 5. Report

Tell the user:
- each file's name and LST start range, and the total start-LST coverage compared with the target's visibility window
- why the SB is split, if it is (e.g. "target passes above 80° at LST 06:16–07:19", or "3C147 sets before the late window"), and that each linked SB is the full length because only one will run
- time on source per SB, and per band
- the gain calibrator (separation, codes) and each SB's flux calibrator and its placement
- the weather limits used

Remind the user that the target must already be in source catalog `<catalog>` under exactly `<name>` before they import. Linked SBs should be linked in the OPT so that only one runs. They should then run validation and check the Static Report for slews.
