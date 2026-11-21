#!/usr/bin/env node
// Debug/inspection entry: dump the neutral IR for a deck file as JSON.
//   node cli.mjs <deck.pptx|deck.pdf>
import { ingest } from "./ingest.mjs";

const file = process.argv[2];
if (!file) {
  console.error("usage: deck-io <deck.pptx|deck.pdf>");
  process.exit(1);
}
const deck = await ingest(file);
console.log(JSON.stringify(deck, null, 2));
