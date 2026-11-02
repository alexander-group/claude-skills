# Alexander group Claude skills

[Claude Code](https://claude.com/claude-code) skills for the group's observing and analysis workflows. A skill is a folder of instructions and scripts that Claude loads when a request matches it. You ask in plain language, e.g. *"write a Ku-band VLA SB for AT2024zau, D config, 1.5 h"*, and Claude follows the skill's workflow.

| skill | what it does |
|---|---|
| [`vla-sb-writer`](skills/vla-sb-writer/) | Writes VLA continuum scheduling blocks (`.optSB`, OPT text format) for point-source targets. It picks calibrators, resources, cycle times and NRAO weather limits, and writes linked early/late SBs to maximize LST coverage and time on source. See its [README](skills/vla-sb-writer/README.md). |

## Install

You need Claude Code, plus Python 3.8+ for the skills' scripts.

```bash
git clone <this repo's URL> ~/claude-skills
pip install -r ~/claude-skills/skills/vla-sb-writer/requirements.txt   # numpy, pandas, astropy

mkdir -p ~/.claude/skills
ln -s ~/claude-skills/skills/vla-sb-writer ~/.claude/skills/vla-sb-writer
```

Restart Claude Code. To check the skill is installed, ask "what skills do you have?" and look for `vla-sb-writer`. Then ask for an SB, e.g. *"load the skill for writing VLA SBs"*.

Because the skill is a symlink, `git pull` in `~/claude-skills` updates it in place.

**Per-user setting.** For TNS name lookup, point the skill at your local TNS CSV:

```bash
export TNS_CATALOG=/path/to/tns_public_objects.csv   # e.g. in ~/.bashrc
```

The CSV needs `name`, `ra` and `dec` (or `declination`) columns, in sexagesimal or degrees; the TNS public-objects dump and `radio-booms-and-beyond/targets/metadata.csv` both work. Without it, the skill asks for RA/Dec.

## Layout

```
skills/<skill-name>/
├── SKILL.md          # instructions Claude reads (YAML front matter: name, description)
├── README.md         # notes for humans
├── requirements.txt  # Python dependencies of the scripts
├── scripts/          # deterministic helpers the skill calls
├── references/       # docs Claude reads on demand
├── data/             # bundled data (e.g. the VLA calibrator list)
└── evals/            # test cases (prompt + graders) for checking changes
```

Test outputs go in `skills/<skill-name>-workspace/`, which is git-ignored.

## Contributing

- **Adding a skill.** Create `skills/<name>/` with a `SKILL.md`. The `description` in its front matter decides when Claude uses the skill, so say what the skill does *and* when to use it. Keep the skill self-contained: bundle its data, use no absolute paths into anyone's home directory, and put per-user settings in environment variables. Add a row to the table above.
- **Changing a skill.** Run its evals before and after; each skill's README says how. Note anything users need to know in the commit message.
- **Building skills with Claude.** The `skill-creator` skill (`/skill-creator` in Claude Code) can draft a skill, run its test cases with and without the skill, and show the results in a review page.
