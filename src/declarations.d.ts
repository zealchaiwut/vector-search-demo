declare module "./commands/ping.js" {
  export function runPing(): Promise<void>;
}

declare module "./commands/ingest.js" {
  export function runIngest(): void;
}

declare module "./commands/search.js" {
  export function runSearch(args: string[]): void;
}
