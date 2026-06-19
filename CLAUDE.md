# vector-search-demo

Semantic vector search demo: TypeScript/Node monolith with a CLI (`commander`
binary, src/cli.ts) and a Fastify server. Current data path is a **file-backed
mock** (`collection.json` + TF-IDF in `src/data/`); real Milvus wiring
(`src/milvus/`, docker-compose stack, MiniLM embedder in `src/embeddings/`)
exists but is not yet connected to ingest/search. See README Architecture.

- `npm run typecheck` before committing TS changes.
- Live Milvus tests in `tests/` are gated on `MILVUS_HOST` being set;
  `MILVUS_HOST`/`MILVUS_PORT` override `MILVUS_ADDRESS` from `.env`.
- This clone (`uat/`) tracks the `develop` branch; PRs target `master`.

## Commander (ticketing / sprint workflow)

Commander is the personal AI agent platform at `~/dev/commander/prd` that runs
this repo's sprints: BA → Coder → Tester → UAT sign-off, using GitHub Issues as
the sprint board. Dashboard: PRD at `http://localhost:8000` (`start-prd`), UAT
at `http://localhost:8001` (`start-uat`). Full docs: `~/dev/commander/prd/README.md`
and `~/dev/commander/prd/docs/workflow.md`.

**Filing work — bulk create (preferred for multi-ticket batches):**

1. Write a prompts file in **this repo's** `docs/bulk-create/` directory (NOT
   the commander repo) named `YYYY-MM-DD-<slug>.md`. See
   `docs/bulk-create/README.md` for the canonical format and existing files for
   examples: header block (`Date`, `Sprint label`, `Default labels`,
   `Status: drafted`), a context paragraph, then a `## Prompts` section
   containing one fenced code block with the prompts separated by `---`. Each
   prompt is a self-contained feature/fix description ending with explicit
   acceptance criteria. Finish with `## Notes` (dependencies, prerequisites) and
   an empty `## Posted issues` table.
2. The human pastes the code block into the dashboard's **Bulk Create** tab —
   a BA agent drafts each ticket, an estimator sizes it, and selected tickets
   are posted as GitHub issues with the sprint label.

**Filing a single ticket directly** (skips the BA draft step):

```bash
cd ~/dev/commander/prd && source venv/bin/activate
python3 scripts/create_ticket.py --title "..." --body "..." --sprint N --labels "bug"
```

Don't post GitHub issues for sprint work directly with `gh`; go through
Commander so the sprint board, estimates, and labels stay consistent.
