# weekly

A [Claude Code](https://claude.com/claude-code) skill that writes a summary of your work week (Monday to Friday) for one or more projects, as a Markdown file with Mermaid diagrams.

It reads two sources: your local Claude Code session transcripts and the git history of each project. From those it reports what landed, what is in progress, and what was only explored.

## Install

Clone the repo into your skills directory under the name `weekly`:

```
git clone <repo-url> ~/.claude/skills/weekly
```

Requirements:

- Python 3.7 or later (standard library only)
- git 2.31 or later
- `gh`, optional, for pull requests of projects hosted on GitHub

## Use

In Claude Code:

```
/weekly ~/code/project-a ~/code/project-b
/weekly ~/code last week
/weekly
```

- A path can be a project or a parent directory; a parent yields one section per project under it.
- With no path, the current directory is used.
- The result is written to `weekly-<YYYY>-W<ww>.md` in the current directory.

The skill runs only when you call it; Claude does not invoke it by itself.

## What the weekly contains

- A two or three sentence headline
- A Mermaid timeline with one section per day
- Per project: **Landed**, **In progress** and **Explored** bullets, with commit hashes and PR numbers
- A Mermaid pie of agent active time by project
- Open threads for next week

## How it works

`SKILL.md` holds the instructions Claude follows. `collect.py` gathers the raw material and prints a digest:

| Source | What it collects |
| --- | --- |
| `~/.claude/projects/*/*.jsonl` | Per session: title, what you asked, files edited, final reply, agent active minutes |
| `git log --all` | Commits of the week with author and line counts |
| `git` tags and changelog files | Tags created and changelog lines added during the week |
| `gh pr list` | Pull requests updated since Monday (GitHub remotes only) |

Sessions run in a git worktree count towards the main checkout, so parallel-agent work folds into one project.

You can run the collector by itself to see the digest:

```
python3 collect.py ~/code/project-a            # current week
python3 collect.py ~/code/project-a --prev 1   # last week
```

## Privacy

The collector only reads local files and runs `git` and `gh`; it sends nothing anywhere itself. The digest does contain your prompts and Claude's replies, and Claude reads it to write the weekly. Generated `weekly-*.md` files are in `.gitignore`, since they hold real project details.
