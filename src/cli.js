#!/usr/bin/env node
import { runSearch } from "./commands/search.js";

const [, , command, ...args] = process.argv;

if (command === "search") {
  runSearch(args);
} else {
  process.stderr.write(
    `Usage: commander <command> [options]\n\nCommands:\n  search <query> [-k <number>]  Search indexed documents\n`
  );
  process.exit(1);
}
