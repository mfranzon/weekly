#!/usr/bin/env python3
"""Digest one work week (Mon-Fri) of Claude Code sessions and git activity for the given paths."""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

PROJECTS = os.path.expanduser("~/.claude/projects")
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
SCRATCH = re.compile(r"/claude-\d+/(.+)-[0-9a-f]{8}-[0-9a-f-]{27}/scratchpad")


def run(cmd, cwd):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def within(child, parent):
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def clip(text, n):
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


class Resolver:
    """Maps a session cwd to the project it belongs to, or None when outside the requested paths."""

    def __init__(self, paths):
        self.paths = paths
        self.cache = {}

    def root(self, cwd):
        # A worktree resolves to its main checkout, so parallel-agent work folds into one project.
        if os.path.isdir(cwd):
            common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
            if common.endswith("/.git"):
                return os.path.dirname(common)
        return None

    def project(self, cwd):
        if cwd not in self.cache:
            self.cache[cwd] = self._project(cwd)
        return self.cache[cwd]

    def _project(self, cwd):
        m = SCRATCH.search(cwd)
        if m:  # scratchpad dirs encode the owning project path with "-" for every separator
            for p in self.paths:
                if m.group(1).startswith(re.sub(r"[^A-Za-z0-9]", "-", p)):
                    return p
            return None
        root = self.root(cwd)
        for p in self.paths:
            if root and (within(root, p) or within(p, root)):
                return root
            if within(cwd, p):
                return p
        return None


def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()


def scan_sessions(resolver, since, until):
    sessions = {}
    for f in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        if os.path.getmtime(f) < since.timestamp():
            continue
        subagents = glob.glob(os.path.join(f[: -len(".jsonl")], "subagents", "*.jsonl"))
        title = None
        for path in [f] + subagents:
            main = path == f
            with open(path, errors="replace") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if main and d.get("type") == "ai-title":
                        title = d.get("aiTitle")
                    ts, cwd = d.get("timestamp"), d.get("cwd")
                    if not ts or not cwd:
                        continue
                    when = parse_ts(ts)
                    if not since <= when < until:
                        continue
                    proj = resolver.project(cwd)
                    if not proj:
                        continue
                    s = sessions.setdefault((proj, os.path.basename(f)), {
                        "project": proj, "start": when, "end": when, "prompts": [],
                        "files": collections.Counter(), "active_ms": 0, "last_text": "",
                    })
                    s["start"], s["end"] = min(s["start"], when), max(s["end"], when)
                    kind = d.get("type")
                    content = (d.get("message") or {}).get("content")
                    if kind == "system" and d.get("subtype") == "turn_duration":
                        s["active_ms"] += d.get("durationMs", 0)
                    elif kind == "user" and main:
                        if (d.get("origin") or {}).get("kind") == "human" and isinstance(content, str) \
                                and not content.lstrip().startswith("<"):
                            s["prompts"].append(content)
                    elif kind == "assistant" and isinstance(content, list):
                        for b in content:
                            if b.get("type") == "tool_use" and b.get("name") in EDIT_TOOLS:
                                fp = (b.get("input") or {}).get("file_path") or (b.get("input") or {}).get("notebook_path")
                                if fp and "/scratchpad/" not in fp:
                                    s["files"][os.path.relpath(fp, proj) if within(fp, proj) else fp] += 1
                            elif b.get("type") == "text" and main and b.get("text", "").strip():
                                s["last_text"] = b["text"]
        for (proj, name), s in sessions.items():
            if name == os.path.basename(f):
                s["title"] = title
    return [s for s in sessions.values() if s["prompts"]]


def git_activity(repo, since, until):
    out = {}
    fmt = "%h|%ad|%an|%s"
    log = run(["git", "log", "--all", "--no-merges", f"--since={since.isoformat()}", f"--until={until.isoformat()}",
               "--date=format:%a %d", f"--pretty=format:{fmt}", "--shortstat"], repo)
    commits, cur = [], None
    for line in log.splitlines():
        if "|" in line and not line.startswith(" "):
            cur = line
            commits.append([cur, ""])
        elif line.strip() and commits:
            m = re.findall(r"(\d+) (insertion|deletion)", line)
            commits[-1][1] = " ".join(("+" if k == "insertion" else "-") + n for n, k in m)
    out["commits"] = commits
    base = run(["git", "rev-list", "-1", f"--before={since.isoformat()}", "HEAD"], repo)
    if base:
        diff = run(["git", "diff", "--unified=0", base, "HEAD", "--", "*CHANGELOG*", "*changelog*"], repo)
        out["changelog"] = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]
    tags = run(["git", "for-each-ref", "--format=%(creatordate:iso-strict)|%(refname:short)", "refs/tags"], repo)
    out["tags"] = [t.split("|", 1)[1] for t in tags.splitlines()
                   if "|" in t and since <= dt.datetime.fromisoformat(t.split("|", 1)[0]).astimezone() < until]
    if "github.com" in run(["git", "remote", "-v"], repo):
        prs = run(["gh", "pr", "list", "--state", "all", "--limit", "50", "--search", f"updated:>={since.date()}",
                   "--json", "number,title,state,author,mergedAt,createdAt"], repo)
        try:
            # "updated since" also returns later activity, so each line carries its dates for the reader to judge.
            out["prs"] = [f"#{p['number']} [{p['state']}] {p['title']} ({p['author']['login']}, opened {p['createdAt'][:10]}"
                          + (f", merged {p['mergedAt'][:10]}" if p.get("mergedAt") else "") + ")"
                          for p in json.loads(prs or "[]") if p["createdAt"] < until.astimezone(dt.timezone.utc).isoformat()]
        except (ValueError, KeyError):
            pass
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", help="project directories, or parent directories of projects")
    ap.add_argument("--prev", type=int, default=0, metavar="N", help="report the week N weeks before the current one")
    a = ap.parse_args()

    paths = [os.path.realpath(os.path.expanduser(p)) for p in a.paths]
    for p in paths:
        if not os.path.isdir(p):
            sys.exit(f"not a directory: {p}")
    today = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    since = today - dt.timedelta(days=today.weekday() + 7 * a.prev)
    until = since + dt.timedelta(days=5)

    resolver = Resolver(paths)
    paths[:] = [resolver.root(p) or p for p in paths]  # a worktree or subdirectory stands for its repo
    sessions = scan_sessions(resolver, since, until)
    projects = collections.defaultdict(list)
    for s in sorted(sessions, key=lambda s: s["start"]):
        projects[s["project"]].append(s)
    # Repos with commits but no sessions still count: the path itself, or its direct children.
    for p in paths:
        for cand in [p] + sorted(glob.glob(os.path.join(p, "*"))):
            if os.path.exists(os.path.join(cand, ".git")):
                projects.setdefault(resolver.root(cand) or cand, [])

    iso = since.isocalendar()
    print(f"# Week {iso.year}-W{iso.week:02d}: {since:%a %d %b} to {until - dt.timedelta(days=1):%a %d %b %Y}\n")
    shown = 0
    for proj, sess in sorted(projects.items()):
        git = git_activity(proj, since, until) if os.path.exists(os.path.join(proj, ".git")) else {}
        if not sess and not any(git.values()):
            continue
        shown += 1
        minutes = sum(s["active_ms"] for s in sess) // 60000
        print(f"## {proj}\n")
        dirty = len(run(["git", "status", "--short"], proj).splitlines()) if git else 0
        print(f"sessions: {len(sess)} | agent active time: {minutes} min | commits: {len(git.get('commits', []))}"
              f" | uncommitted files now: {dirty}\n")
        for key, label in (("commits", "Commits (hash|day|author|subject, lines)"), ("prs", "Pull requests updated since Monday (check the dates against the week)"),
                           ("tags", "Tags created"), ("changelog", "Changelog lines added")):
            if git.get(key):
                print(f"### {label}\n")
                for item in git[key][:80]:
                    print("- " + (f"{item[0]}  {item[1]}".rstrip() if isinstance(item, list) else clip(item, 200)))
                print()
        if sess:
            print("### Sessions\n")
        for s in sess:
            print(f"#### {s['start']:%a %d %H:%M} | {s.get('title') or 'untitled'} | {s['active_ms'] // 60000} min")
            for p in s["prompts"][:25]:
                print(f"- ask: {clip(p, 240)}")
            if len(s["prompts"]) > 25:
                print(f"- (+{len(s['prompts']) - 25} more asks)")
            if s["files"]:
                top = s["files"].most_common(15)
                more = f" (+{len(s['files']) - 15} more)" if len(s["files"]) > 15 else ""
                print("- files edited: " + ", ".join(f"{f} x{n}" for f, n in top) + more)
            if s["last_text"]:
                print(f"- final reply: {clip(s['last_text'], 500)}")
            print()
    if not shown:
        print("No sessions or commits found for these paths in this week.")


if __name__ == "__main__":
    main()
