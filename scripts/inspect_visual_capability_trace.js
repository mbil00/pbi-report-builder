#!/usr/bin/env node

"use strict";

const path = require("path");

const {
  buildTraceManifest,
  createRuntime,
  findRegistry,
  formatTraceReport,
} = require("./lib/visual_capabilities_bundle");

function parseArgs(argv) {
  const args = {
    bundle: path.join("schema-analysis", "output", "DESKTOP.MIN.JS"),
    visual: null,
    asJson: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--bundle") {
      args.bundle = argv[++i];
    } else if (arg === "--visual") {
      args.visual = argv[++i];
    } else if (arg === "--json") {
      args.asJson = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!args.visual) {
    throw new Error("Missing required argument: --visual <visualType>");
  }

  return args;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const runtime = createRuntime(args.bundle);
  const registryInfo = findRegistry(runtime.req, runtime.modules);
  const traceManifest = buildTraceManifest({
    bundlePath: args.bundle,
    modules: runtime.modules,
    registryInfo,
    visuals: registryInfo.registry,
  });

  if (args.asJson) {
    const trace = traceManifest.visuals[args.visual];
    if (!trace) {
      throw new Error(`Unknown visual type "${args.visual}"`);
    }
    console.log(JSON.stringify({
      meta: traceManifest.meta,
      visualType: args.visual,
      trace,
    }, null, 2));
    return;
  }

  console.log(formatTraceReport(args.visual, traceManifest));
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}
