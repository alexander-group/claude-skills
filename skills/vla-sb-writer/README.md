# vla-sb-writer

This skill writes VLA scheduling blocks for continuum observations of point-source targets (TDEs, GRBs, SNe, …) as OPT text-format `.optSB` files ready to import into the OPT. Claude reads `SKILL.md`; this file is for people.

## Using it with Claude

Give Claude six things, and it asks for any that are missing:

1. the target name as it appears in the OPT source catalog
2. the source catalog name (usually the project code, e.g. `26A-445`)
3. the total SB length (a whole or half hour)
4. the bands: any of L, S, C, X, Ku, K, Ka
5. RA/Dec, or a transient name with `$TNS_CATALOG` set
6. the array configuration: A, B, C or D

Example prompt: *"Write an LSCX SB for AT2023clx (11:40:09.44 +15:19:39.0), B config, 2 h, catalog 25A-159, epoch e8."*

Claude then does the following:
- **Gain calibrator:** picks the closest one coded P or S in your configuration for every band, from the bundled VLA calibrator list.
- **Flux calibrator:** picks 3C286, 3C147 or 3C48, and decides whether it is observed first or last.
- **Linked SBs:** decides between a single SB and an **early/late pair** (never more than two). This **maximizes the LST range the observation can start in and the time on source**, while keeping the target and calibrators between 30° (35° in C/D) and 80°.
- **Writes each SB at exactly the requested length**, with:
  - configuration-appropriate resources and gain-cycle times
  - NRAO weather limits for the strictest band
  - a CW/CCW wrap
  - X-band reference pointing for Ku and above, repeated about hourly
  - requantizer scans
  - a bandpass/flux block
- **Checks** every file and reports the LST ranges, coverage, time on source and calibrator choices.

**Before you submit:**
- Make sure the target is in the source catalog under exactly that name.
- Import the files into the OPT and link the early/late pair.
- Run validation, and look at the Static Report.

The scripts' checks are static; they can't see the OPT's catalog or slew model.

## Using the scripts directly

All scripts take `--help`. Run them from anywhere; they find their data relative to their own location.

```bash
S=~/claude-skills/skills/vla-sb-writer/scripts

# 1. gain-calibrator candidates and visibility
python $S/find_calibrators.py --ra 06:47:16.38 --dec +41:57:55.1 --config D --bands Ku

# 2. plan + write the SB(s): single or early/late, LST ranges, flux calibrator placement, wraps
python $S/plan_sbs.py --target AT2024zau --catalog 26A-445 --config D --bands Ku --total 1.5h \
    --ra 06:47:16.38 --dec +41:57:55.1 --gain-cal J0646+4451 --epoch e3 \
    --comments "Third epoch of TDE AT2024zau. Please observe within the next week." --outdir .

# 3. check
python $S/check_sb.py U_AT2024zau_e3_*.optSB --target AT2024zau --catalog 26A-445 --expect 1.5h
```

- `build_sb.py` writes one SB with every choice given explicitly (`--flux-cal`, `--flux-first`, `--lst`, `--wrap`). Use it to override the planner.
- `plan_sbs.py` options:
  - `--min-el` and `--max-el` change the elevation limits
  - `--max-sbs 1` forces a single SB
  - `--min-gain` sets how much extra start range (minutes) justifies a second SB
  - `--weights X=2,C=1` shifts time between bands
  - `--selfcal` uses the relaxed self-calibration weather limit

## Where the defaults come from

The resource names for each configuration, the gain-cycle times, and the setup, requantizer and flux scan lengths were taken from about 200 of the group's hand-written SBs (`obstools/VLA-SBs`). The weather limits come from the [NRAO dynamic-scheduling table](https://science.nrao.edu/facilities/vla/docs/manuals/obsguide/dynsched/weather-constraints). Everything is tabulated at the top of `scripts/build_sb.py` and explained in `references/strategy.md`. Edit the tables there if group practice changes.

Known gaps:
- `Ka64f2A` (Ka band in A configuration) has never been used in a group SB, so the scripts warn about it.
- The `3.0` field in the `SCHED-BLOCK` line is copied unchanged from group SBs; its meaning hasn't been confirmed.
- Polarization calibration, per-band gain calibrators and spectral-line setups aren't generated. Claude can hand-edit those in after the build.

**Updating the calibrator list.** Replace `data/vla-calibrators-2.txt` (the NRAO list text format) and `data/calibrators.csv`. The CSV's columns are `IAU NAME, EQUINOX, PC, ra, dec, POS.REF, ALT.NAME, IAU FULL NAME`, as built by `obstools/sb-helper/setup.py`.

## Testing changes

`evals/` holds three test cases (C/A-config GRB, Ku/D-config TDE with TNS lookup, LSCX/B-config). Each has a prompt and one file per check in `graders/`.

1. Run each prompt with Claude, once with the skill and once without. The `skill-creator` skill automates this into `../vla-sb-writer-workspace/iteration-N/<case>/{with_skill,without_skill}/outputs/`.
2. Grade the runs:
   ```bash
   python evals/grade.py ../vla-sb-writer-workspace/iteration-N
   ```
   This writes a `grading.json` for each run and prints the failures.

The cases also follow the `claude plugin eval` layout. The Ku case's TNS file is bundled in `evals/ku-band-tde-d-config/files/`.

For a quick structural regression after editing the scripts, run the checker over the archive. It should flag only `24B-118/LSCXU_AT2018cqh_e3_pol.optSB`, whose header line is corrupted (`CHED-BLOCK`).

```bash
python scripts/check_sb.py <path-to>/obstools/VLA-SBs/*/*.optSB --quiet
```
