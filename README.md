# Alexander group Claude skills

This repo holds Claude Code skills for the group's observing and analysis workflows.

| skill | what it does |
|---|---|
| [`vla-sb-writer`](skills/vla-sb-writer/SKILL.md) | Writes VLA continuum scheduling blocks (`.optSB`, OPT text format) for point-source targets. It chooses calibrators, resources and cycle times from the array configuration and fits the scans into a requested total time. |

## Install

```bash
git clone <this repo> ~/claude-skills
mkdir -p ~/.claude/skills
ln -s ~/claude-skills/skills/vla-sb-writer ~/.claude/skills/vla-sb-writer
```

Restart Claude Code, then ask for an SB, e.g. *"load the skill for writing VLA SBs"*. Run `git pull` to get updates; the symlinks keep pointing at the latest version.

Python requirements: `numpy`, `pandas`, `astropy`.

### TNS lookup (optional)

`vla-sb-writer` can look up a transient's coordinates by name. Point it at your local TNS CSV:

```bash
export TNS_CATALOG=/path/to/tns_public_objects.csv   # put this in ~/.bashrc
```

It accepts any CSV with `name`, `ra` and `dec` (or `declination`) columns, in sexagesimal or degrees. The TNS public-objects dump and `radio-booms-and-beyond/targets/metadata.csv` both work. Without it, the skill asks for RA/Dec.

## Adding a skill

Put it in `skills/<skill-name>/` with a `SKILL.md` (YAML front matter with `name` and `description`), plus any `scripts/`, `references/` and `data/` it needs. Keep each skill self-contained, with no absolute paths to anyone's home directory. Add a row to the table above.
