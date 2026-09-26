# Add or change a scip-cli command

1. Read `.cursor/skills/new-command/SKILL.md` and follow the checklist end-to-end.
2. Read `.cursor/skills/test/SKILL.md`; add/update e2e tests and `COMMAND_SETUP_PATHS`.
3. Update `scip_cli/SKILL.md` and `README.md` if flags or behavior are user-visible.
4. Run `/test` workflow (or `scripts/test.sh` if the change is wide).
5. Report: command name, files touched, tests run.

Do not commit unless the user asks.
