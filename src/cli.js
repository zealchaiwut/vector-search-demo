#!/usr/bin/env node
import { runSearch } from "./commands/search.js";
import { runIngest } from "./commands/ingest.js";

const [, , command, ...args] = process.argv;

if (command === "search") {
  runSearch(args);
} else if (command === "ingest") {
  runIngest();
} else {
  process.stderr.write(
    `Usage: commander <command> [options]\n\nCommands:\n  search <query> [-k <number>]  Search indexed documents\n  ingest                        Index synthetic documents into the collection\n`
  );
  process.exit(1);
}
