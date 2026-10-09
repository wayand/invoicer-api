---
name: pr-description
description: Draft a pull request title and description for the current branch from the PR template. Use when the user wants a PR description or is about to open a PR.
allowed-tools: Bash(git status *), Bash(git diff *), Bash(git log *), Read
---

# PR description

1. Collect the facts with `git log master..HEAD --oneline` and `git diff master...HEAD --stat` (use `main` if that is the base). Read the diff where needed.
2. Use `.azuredevops/pull_request_template.md` as the structure if it exists. This repo is currently on GitHub and has no such file, so otherwise use these headings: **What**, **Why**, **Changes**, **Testing**, **Notes for reviewers**.
3. Fill in the sections:
   - **Title**: `<type>: <description> AB#<id>`, under about 70 characters. Ask for the work item id. Never invent it.
   - **What / Why**: two or three sentences each. The Why is the motivation, not a restatement of the diff.
   - **Changes**: short bullets grouped by area.
   - **Testing**: only what was actually done in this session or evident from the branch (tests added, commands run with their real results). If nothing was run, write "Not run". Never claim checks that did not happen.
   - **Notes for reviewers**: risks, migrations, new env vars, follow-ups, anything to look at first.
4. Add no AI attribution or "Generated with" footer.
5. Output the title and description as Markdown for the user to paste. Don't push or open the PR.
