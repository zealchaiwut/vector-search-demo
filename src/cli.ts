#!/usr/bin/env node
import { Command } from "commander";

const program = new Command();

program
  .name("commander")
  .description("Vector search demo CLI")
  .version("0.1.0");

program
  .command("serve")
  .description("Start the Fastify web server")
  .action(async () => {
    const { startServer } = await import("./server/index.js");
    await startServer();
  });

program
  .command("ping")
  .description("Check Milvus connectivity")
  .action(async () => {
    const { runPing } = await import("./commands/ping.js");
    await runPing();
  });

program
  .command("init")
  .description("Provision an empty, indexed collection")
  .action(async () => {
    const { runInit } = await import("./commands/init.js");
    await runInit();
  });

program
  .command("ingest")
  .description("Index documents into the collection")
  .action(async () => {
    const { runIngest } = await import("./commands/ingest.js");
    await runIngest();
  });

program
  .command("search")
  .description("Search indexed documents")
  .argument("[query...]", "search query terms")
  .action(async (queryParts: string[]) => {
    const { runSearch } = await import("./commands/search.js");
    await runSearch(queryParts);
  });

program.parse();
