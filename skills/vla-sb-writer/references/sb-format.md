# OPT text SB format (VERSION 7)

This is the plain-text format the OPT exports and imports. It was worked out from about 200 group SBs. Records are separated by `;`, leading whitespace is ignored, and lines starting with `#` are comments (the OPT export adds a `#` header). Field counts below include the trailing empty field after the final `;`.

## Header

```
VERSION; 7;
 SRC-CAT; VLA, <source catalog name>;
HDWR-CAT; NRAO Defaults;
SCHED-BLOCK; <name>; Dynamic; 1; <start date>,<end date>; <LST start>-<LST end>, ; 3.0; <config>; <az>; <el>; N; N; w=<wind>,p=<api>; <comments>; 
```

`SRC-CAT` names the OPT source catalog that holds the target. The catalog is usually named after the project code (e.g. `26A-445`). `VLA` is the built-in calibrator catalog. The target must already exist in that catalog, with exactly the name the scans use.

`SCHED-BLOCK` fields, in order:

| # | value | meaning |
|---|---|---|
| 1 | name | SB name (group style `LSCX_<target>_e<N>[_early/_late]`) |
| 2 | `Dynamic` | scheduling type |
| 3 | `1` | count (number of executions) |
| 4 | `YYYY-MM-DD hh:mm:ss,2099-12-31 23:59:59` | date range in which the SB may run |
| 5 | `hh:mm:ss-hh:mm:ss, ` | LST *start* range. Several comma-separated ranges are allowed. |
| 6 | `3.0` | always 3.0 in group SBs (a few have 0.0) |
| 7 | `A`/`B`/`C`/`D` | array configuration |
| 8 | az | initial azimuth for slew estimates: -85 = CCW wrap, 445 = CW wrap, 180 = no preference |
| 9 | el | initial elevation, 35.0 |
| 10–11 | `N; N` | sun/night avoidance flags (unused) |
| 12 | `w=10.0,p=15.0` | max wind (m/s) and API phase rms (deg), taken from the NRAO table for the most demanding band (strategy.md). "Any" is entered as 100. |
| 13 | comments | free text to the operators: science goal, urgency, and links between SBs ("observe only 1 of the linked SBs") |

## Loops

```
LOOP-START; <name>; <repeat count>; N; ;
...
LOOP-END;
```

Loops nest. The total time is the sum of every scan duration multiplied by the repeat counts of all loops that enclose it.

## Scans

**STD** (standard observing, 16 fields):
```
STD; <scan name>; <source>; <resource>; DUR; 0h 1m 0s; <wrap>; <ptg corr>; N; N; N; Y; N; N; <intents>; ;
```
- `source` is a calibrator name from the VLA catalog (`J0811+0146`, `3C147`, or the alias form `0542+498=3C147`) or the target name from the project catalog.
- `resource` is an NRAO default instrument setup (see strategy.md). `PREV` means "same as the previous scan".
- `DUR` duration includes the slew. A scan whose slew is longer than its duration gets no on-source time.
- `wrap` is blank, `CW`, or `CCW`. Set it only on the first (setup) scans.
- `ptg corr` is `Y` to apply the last reference-pointing solution. The group sets `Y` on every scan after the first `PTG` and `N` when the SB has no pointing.
- `intents` is a comma list ending in `,`:
  - `SetAtnGain,`: every setup, dummy, requantizer, and slew-absorbing scan
  - `CalGain,`: complex gain calibrator
  - `ObsTgt,`: target
  - `CalBP,CalFlux,`: flux and bandpass calibrator
  - `CalPolAng,` / `CalPolLeak,`: polarization; not used by this skill

**PTG** (interferometric reference pointing, 13 fields):
```
PTG; <scan name>; <source>; X-point; DUR; 0h 3m 30s; <wrap>; N; N; N; N; Y; Y;
```
`IP` lines have the same layout as `PTG` (older form).
