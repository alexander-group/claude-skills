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
- coded P or S in this configuration for every band (the output marks these "usable YES")
- as close as possible: within about 10° if any band is Ku or above, about 15° otherwise
- flux of at least a few hundred mJy

A strong P calibrator farther away beats a weak nearby S one. Also check the calibrator's elevation window against the target's. A calibrator whose window is shorter than the target's narrows the LST range, which works against goal 1. If two candidates are comparable, prefer the one whose visibility better matches the target's.

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
- Sets an antenna wrap on every SB, because the group always gives one: CCW if the target is rising during the SB, CW if it is setting. For an early/late pair this is usually CCW/CW.
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

## 4. Check

```bash
python scripts/check_sb.py <dir>/*.optSB --target <name> --catalog <catalog> --expect <total>
```

Fix every ERROR. Read the WARNs; a weather limit stricter or looser than the NRAO table is one example. The checker can't see the OPT's source catalog, slew model or hardware database, so the user's OPT import and validation remain the final test.

## 5. Report

Tell the user:
- each file's name and LST start range, and the total start-LST coverage compared with the target's visibility window
- why the SB is split, if it is (e.g. "target passes above 80° at LST 06:16–07:19", or "3C147 sets before the late window"), and that each linked SB is the full length because only one will run
- time on source per SB, and per band
- the gain calibrator (separation, codes) and each SB's flux calibrator and its placement
- the weather limits used

Remind the user that the target must already be in source catalog `<catalog>` under exactly `<name>` before they import. Linked SBs should be linked in the OPT so that only one runs. They should then run validation and check the Static Report for slews.
