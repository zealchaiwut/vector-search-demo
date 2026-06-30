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
  .option("--model <name>", "embedding model to use for vector search (must be registered and have embeddings stored via embed-corpus)")
  .option("-k <number>", "number of results to return", "10")
  .action(async (queryParts: string[], opts: { model?: string; k?: string }) => {
    const { runSearch } = await import("./commands/search.js");
    // Pass model as a synthetic flag so the existing argv parser can handle it.
    const extra: string[] = [];
    if (opts.model) extra.push("--model", opts.model);
    if (opts.k) extra.push("-k", opts.k);
    await runSearch([...queryParts, ...extra]);
  });

program
  .command("embed-corpus")
  .description("Embed all stored chunks under a named model for corpus comparison")
  .option("--model <name>", "embedding model to use (required; e.g. BAAI/bge-m3)")
  .action(async (opts: { model?: string }) => {
    const { runEmbedCorpus } = await import("./commands/embed-corpus.js");
    const args: string[] = [];
    if (opts.model) args.push("--model", opts.model);
    await runEmbedCorpus(args);
  });

program
  .command("re-embed")
  .description("Recompute embeddings for all existing articles and chunks")
  .action(async () => {
    const { runReEmbed } = await import("./commands/re-embed.js");
    await runReEmbed();
  });

program
  .command("rechunk")
  .description("Delete and regenerate all chunks using current chunk settings, then re-embed")
  .action(async () => {
    const { runRechunk } = await import("./commands/rechunk.js");
    await runRechunk();
  });

program
  .command("verify")
  .description("Check integrity: every article has ≥1 chunk and every chunk has a non-null embedding")
  .action(async () => {
    const { runVerify } = await import("./commands/verify.js");
    await runVerify();
  });

program.parse();
