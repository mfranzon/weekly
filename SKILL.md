---
name: weekly
description: Write the team's weekly summary (Mon-Fri) for the given project paths, as a Markdown file with Mermaid diagrams.
argument-hint: <path> [path...] [last week]
disable-model-invocation: true
---

# Weekly

Produce a **weekly**: a brief, outcome-first summary of the work week (Monday to Friday) for the projects in `$ARGUMENTS`, read by the author and their team.

## 1. Collect

Run the collector on every path in the arguments (no path given: the current directory):

```
python3 "${CLAUDE_SKILL_DIR}/collect.py" <path> [path...]
```

Add `--prev N` when the arguments ask for an earlier week ("last week" is `--prev 1`).

The digest it prints is the single source for the weekly. Per project it holds the commits, pull requests, tags and changelog lines of the week, then each Claude session: title, what the human asked, files edited, and the final reply. A path that is a parent directory yields one section per project under it.

Done when the digest is read in full. If it reports nothing found, say so and stop.

## 2. Fill the gaps

Commits and pull requests are what **landed**; sessions show what was attempted. For each session whose asks point at code work with no matching commit, look at the project (`git status`, `git log -p` on the files edited, the files themselves) until you can place it in one bucket:

- **landed**: committed or merged
- **in progress**: changed on disk or on a branch, not merged
- **explored**: research, experiments, questions answered, nothing to merge

Done when every session with edits or more than a couple of asks is in a bucket.

## 3. Write

Write `weekly-<YYYY>-W<ww>.md` (week label from the digest's first line) in the current directory, in this shape:

```markdown
# Weekly <YYYY>-W<ww> (<Mon date> to <Fri date>)

<Two or three sentences: the week's headline for someone who reads only this.>

<mermaid timeline>

## <Project name>

**Landed**
- <outcome>, with the commit hash or PR number

**In progress**
- <outcome so far, and what remains>

**Explored**
- <question, and the conclusion reached>

## Effort

<mermaid pie>

## Next

- <open threads visible in the digest: unfinished work, stated next steps>
```

Rules for the content:

- Write **outcomes**: what now exists or is now known, grouped by theme. Several sessions and commits on one theme are one bullet.
- Every claim traces to the digest or to what you checked in step 2. Results and numbers come from the final replies or the repo, quoted as found.
- A teammate who was absent all week is the reader: name things in plain words, and say what a project is on first mention when its name does not.
- Omit an empty bucket, and omit sessions that are one-off questions with no bearing on the project.
- Commits by other authors belong in the weekly, credited by name.
- Brief: a project gets three to six bullets in total.

Rules for the diagrams:

- **Timeline** (`timeline`): one section per day Monday to Friday, each with one to three short events of what landed or was worked on that day. With several projects, prefix the event with the project name. Event text carries no colons or semicolons.
- **Pie** (`pie title Agent active time by project`): minutes per project from the digest, labels in double quotes. With a single project, slice by theme instead, estimating each theme's share from its sessions' minutes.
- Add a `gantt` only when a theme spans several days and the timeline hides that.

Done when the file is written and every Mermaid block follows the rules above. Reply with the file path and the headline sentences.
