import { searchDocuments } from "../core/search.js";

function parseArgs(argv) {
  // argv is the slice after ["node", "cli.js", "search"]
  // Positional: first non-flag arg is the query
  // Flags: -k <number>
  let query = null;
  let k = 10;

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "-k" && i + 1 < argv.length) {
      k = parseInt(argv[i + 1], 10);
      i++;
    } else if (!argv[i].startsWith("-")) {
      query = argv[i];
    }
  }

  return { query, k };
}

export function runSearch(argv) {
  const { query, k } = parseArgs(argv);

  if (!query || query.trim() === "") {
    process.stderr.write(
      "Usage: commander search <query> [-k <number>]\nError: query is required\n"
    );
    process.exit(1);
  }

  const results = searchDocuments(query, k);

  if (results.length === 0) {
    process.stdout.write("No results found\n");
    return;
  }

  for (let i = 0; i < results.length; i++) {
    const r = results[i];
    const rank = i + 1;
    const attachment = `${r.doc_id}.txt`;
    process.stdout.write(
      `\n--- Result ---\n` +
      `Rank:       ${rank}\n` +
      `Title:      ${r.title}\n` +
      `Doc-ID:     ${r.doc_id}\n` +
      `Score:      ${r.score}\n` +
      `Attachment: ${attachment}\n`
    );
  }
  process.stdout.write("\n");
}
