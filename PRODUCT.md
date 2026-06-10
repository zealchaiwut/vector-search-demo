# Product Context

## What vector-search-demo Is

vector-search-demo is a small reference application that demonstrates semantic
(vector) search end to end: embed documents, store the vectors, and return the
most similar results for a natural-language query. It exists to show the whole
pattern, ingest, embed, index, query, rank, in the smallest honest form.

## Target Users

Developers evaluating how to add semantic search to an app. They want a working,
readable example they can trace and adapt, more than a finished product.

## Core User Flows

1. **Ingest** — add documents or text; each is chunked, embedded, and indexed.
2. **Query** — type a natural-language question; get back ranked similar results.
3. **Inspect** — see each result's similarity score and which chunk matched.

## Design Principles

- Readable over clever: the value of the demo is that you can follow the code.
- Show the mechanics: surface similarity scores, embedding dimensions, index size.
- Minimal dependencies: no heavyweight framework where a small one does the job.

> Starter context. Refine with `/impeccable init` (or edit directly) as the
> product takes shape.
