#!/usr/bin/env node
import { runSearch } from "./commands/search.js";
import { runIngest } from "./commands/ingest.js";
import { runInit } from "./commands/init.js";

const [, , command, ...args] = process.argv;

if (command === "search") {
  runSearch(args);
} else if (command === "ingest") {
  runIngest();
} else if (command === "init") {
  runInit(args).catch((err) => {
    process.stderr.write(`Error: ${err.message}\n`);
    process.exit(1);
  });
} else if (command === "ping") {
  const { runPing } = await import("./commands/ping.js");
  runPing().catch((err) => {
    process.stderr.write(`Error: ${err.message}\n`);
    process.exit(1);
  });
} else {
  process.stderr.write(
    `Usage: commander <command> [options]\n\nCommands:\n  search <query> [-k <number>]  Search indexed documents\n  ingest                        Index synthetic documents into the collection\n  init [--recreate]             Provision the Milvus documents collection\n  ping                          Check Milvus connectivity\n`
  );
  process.exit(1);
}
