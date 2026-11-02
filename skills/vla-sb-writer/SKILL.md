---
name: vla-sb-writer
description: Write VLA (Very Large Array) scheduling blocks (SBs) for continuum observations of point-source targets such as TDEs, GRBs, SNe and FBOTs, as OPT text-format .optSB files that pass OPT validation. Handles any mix of L, S, C, X, Ku, K and Ka bands in A, B, C or D configuration. It picks gain and flux calibrators from the bundled VLA calibrator list, sets resources and gain-cycle times for the configuration, fits scans into a requested total time, and computes the LST start range. Use this whenever someone asks to write, make, draft, generate or update a VLA SB, scheduling block, or OPT/optSB file, plans VLA radio follow-up of a transient, says "load the skill for writing VLA SBs", or needs a VLA phase calibrator or LST range for an SB, even if they don't say "scheduling block".
---

# VLA scheduling-block writer

This skill produces OPT text-format SBs (`VERSION; 7;`) in the style the group uses by hand. Three scripts do the deterministic work. Your job is to collect the inputs, make the judgment calls (calibrators, LST range, band weights, flux calibrator placement), and explain them.

Scripts live in `scripts/` next to this file. They need Python 3 with numpy, pandas and astropy, and read the bundled calibrator list in `data/`.

- `find_calibrators.py` lists gain-calibrator candidates, flux-calibrator visibility and LST start ranges.
- `build_sb.py` writes the SB and prints a time budget.
- `check_sb.py` is a static checker that runs before the user imports the file into the OPT.

For the meaning of the file's fields, see `references/sb-format.md`. For the reasoning behind resources, cycle times, calibrator criteria and LST rules, see `references/strategy.md`. Real group SBs are in `references/examples/`.

## 1. Collect the inputs

You need all six of these. Ask for whichever are missing, in one message, rather than guessing. Every wrong input produces an SB that fails validation or wastes telescope time.

1. **Target name** exactly as it appears in the OPT source catalog. The SB refers to the target by name, so a mismatch fails validation.
2. **Source catalog name** in the OPT. This is usually the project code, e.g. `26A-445`. It becomes `SRC-CAT; VLA, <catalog>;`.
3. **Total SB time**, e.g. "1h", "1.5 h", "90 min".
4. **Bands**: any of L, S, C, X, Ku (also called U), K, Ka.
5. **RA/Dec** of the target. If the user gives only a transient name, try `find_calibrators.py --name <name>`. That reads the CSV at `$TNS_CATALOG`. If the variable is unset or the name isn't found, ask for coordinates.
6. **Array configuration**: A, B, C or D. If the user says "Any" or doesn't know, ask which configuration the SB will run in, because resources and cycle times depend on it.

Optional inputs, with defaults:
- epoch label for the file name (e.g. `e2`)
- comments to the operators (urgency, science case, linked SBs)
- band weights, if some bands need more time
- weather limits: `w=10,p=15`, or `w=7,p=10` if K or Ka is included
- wrap preference

## 2. Find calibrators

```bash
python scripts/find_calibrators.py --ra <RA> --dec <Dec> --config <A|B|C|D> --bands <comma list>
```

Choose **one gain calibrator for all bands**:
- It should be coded P or S in this configuration for every requested band; "usable YES" in the output marks these.
- It should be as close as possible to the target: within about 10° if any band is Ku or above, about 15° otherwise.
- Its flux should be at least a few hundred mJy.

The guide prefers a strong P calibrator a little farther away over a weak nearby S one. If no single calibrator works for all bands, say so and propose the best compromise, or a per-band choice; per-band choices need hand-editing after the build.

Then get start ranges with the chosen calibrator and the SB length:

```bash
python scripts/find_calibrators.py --ra <RA> --dec <Dec> --config <cfg> --bands <bands> --gain-cal <J name> --length <hours>
```

Use `--min-el 35` in C or D configuration. Choose the flux calibrator and whether it goes first or last:
- Prefer 3C286, 3C147 or 3C48. Avoid 3C138, which is variable.
- Use the combination with the widest start range that suits the request.
- Observing the flux calibrator first (`--flux-first`) works well when it is high at the start and the target rises afterwards.

If no single range works, or the user wants flexibility, write two linked SBs (`_early` and `_late`, often with opposite wraps). Note in the comments that only one should be observed.

## 3. Build the SB

```bash
python scripts/build_sb.py --target <name> --catalog <catalog> --config <cfg> --bands <bands> \
    --total <time> --gain-cal <J name> --flux-cal <3Cxx> --lst <HH:MM:SS-HH:MM:SS> \
    [--flux-first] [--wrap CW|CCW] [--weights X=2,C=1] --comments "<text>" \
    --sb-name <name> --out <path>.optSB
```

The script handles:
- the resource for each band and configuration
- the setup loop
- X-band reference pointing for Ku and above
- 30 s requantizer scans for 3-bit bands
- gain/target cycles under the per-configuration cycle limit
- the bandpass/flux block
- scans that absorb slews between distant calibrators

It fits all of this into `--total` and prints a time budget on stderr. Keep the budget output to show the user.

**Naming.** Follow the group convention: band letters from low to high frequency, then the target, then the epoch. For example `LSCX_AT2022hvp_e3.optSB` or `U_AT2026amv_e1_early.optSB`, where U = Ku and A = Ka. Write the file to the location the user asked for, or to the current directory.

**Comments.** If the user gave no comments, write a one-sentence note to the operators in the group's style. Include what the source is, why it's time-sensitive, and the cadence request. For example: "Follow-up observation of TDE AT2026amv. Please observe within the next week if possible, or ASAP thereafter." Avoid `;` in comments, because it is the field separator.

Don't write SB text by hand unless the user needs something the generator can't express, such as different calibrators per band, polarization calibration, or a second pointing. In those cases, start from the generator's output and edit it, then run the checker.

## 4. Check it

```bash
python scripts/check_sb.py <path>.optSB --target <name> --catalog <catalog> --expect <total>
```

Fix every ERROR. Usually that means rerunning `build_sb.py` with different arguments. Mention any WARNs to the user; an unverified resource name is one example. The checker can't see the OPT's source catalog, slew model or hardware database, so the user's OPT import remains the final test.

## 5. Report

Tell the user:
- the file path
- the time budget: total, time on target per band, number of cycles
- the gain calibrator, with its separation and codes
- the flux calibrator and where it sits in the SB
- the LST start range, with the reasoning for each

Remind the user that the target must already be in source catalog `<catalog>` under exactly `<name>`, with the RA/Dec used here, before they import the SB. Then they should run the OPT's validation and check the Static Report for the estimated slews and elevations.
