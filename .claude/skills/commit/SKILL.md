---
name: commit
description: "Commit the current changes using the project convention `<type>: <description> AB#<id>`. Takes the work item id as argument."
disable-model-invocation: true
argument-hint: <work-item-id>
allowed-tools: Bash(git status *), Bash(git diff *), Bash(git log *), Bash(git add *), Bash(git commit *)
---

# Commit

Work item id: `$ARGUMENTS`

1. Run `git branch --show-current`. If it is `main` or `master`, stop and refuse. Tell the user to create a `<type>/<kebab-case>` branch first.
2. If `$ARGUMENTS` is empty or not a number, ask for the work item id. Never invent one.
3. Run `/check`. If anything fails, stop and report. Don't commit failing code.
4. Review `git status` and `git diff`. Never stage `.env`, `.env.*`, secrets, `uploads/`, `logs/` or `.claude/settings.local.json`. Stage files by name, not `git add -A`.
5. If the changes cover more than one logical change, propose a split (which files go in which commit, with the messages) and wait for approval before committing.
6. Commit as `<type>: <description> AB#<id>`:
   - `<type>`: `feature`, `fix`, `chore`, `docs`, `refactor` or `test`
   - `<description>`: imperative, lower-case, under about 60 characters
   - Example: `fix: reject expired reset tokens AB#1234`
   - Add no body unless the why isn't obvious. Add no `Co-Authored-By` or "Generated with" lines.
7. Show `git log -1 --stat`. Do not push.
