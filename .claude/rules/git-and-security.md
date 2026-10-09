# Git and security

## Do
- Work on a branch named `<type>/<kebab-case>` (`feature`, `fix`, `chore`, `docs`, `refactor`, `test`), created off an up-to-date `master`.
- Write commits as `<type>: <description> AB#<id>`. Ask for the work item ID. Never invent one.
- Keep commit messages short: an imperative one-liner, a body only when the why isn't obvious.
- Commit or push only when asked.
- Tell the user right away if you find a secret in code, history, logs or config. Don't repeat the value.

## Don't
- Don't commit or push to `main` or `master`. Don't force-push. Don't use `--no-verify`.
- Don't add AI attribution (`Co-Authored-By`, "Generated with ...") to commits, PRs or files.
- Don't read `.env` or other local env files. Use `.env.sample`.
- Don't print, log or paste secrets, tokens or personal data.
