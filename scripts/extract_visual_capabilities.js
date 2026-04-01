#!/usr/bin/env node

"use strict";

const path = require("path");

const {
  buildAnalysisManifest,
  buildTraceManifest,
  buildVisualRecord,
  createRuntime,
  findRegistry,
  writeJson,
} = require("./lib/visual_capabilities_bundle");

function parseArgs(argv) {
  const args = {
    bundle: path.join("schema-analysis", "output", "DESKTOP.MIN.JS"),
    outDir: path.join("schema-analysis", "generated"),
    split: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--bundle") {
      args.bundle = argv[++i];
    } else if (arg === "--out-dir") {
      args.outDir = argv[++i];
    } else if (arg === "--split") {
      args.split = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const {
    req,
    failures,
    sourceLength,
    modules,
    bundleParseStrategy,
    localizationOverrides,
  } = createRuntime(args.bundle);
  const registryInfo = findRegistry(req, modules);
  const registry = registryInfo.registry;

  const visuals = {};
  const summaryVisuals = {};
  let totalObjects = 0;
  let totalProperties = 0;

  for (const visualType of Object.keys(registry).sort()) {
    const record = buildVisualRecord(visualType, registry[visualType]);
    visuals[visualType] = record;
    summaryVisuals[visualType] = {
      visualType,
      pluginName: record.plugin.name || visualType,
      titleKey: record.plugin.titleKey || null,
      watermarkKey: record.plugin.watermarkKey || null,
      roleCount: record.dataRoles.length,
      dataRoleNames: record.dataRoleNames,
      objectCount: record.objectCount,
      propertyCount: record.propertyCount,
      objectNames: record.objectNames,
      objectPropertyCounts: record.objectPropertyCounts,
      capabilityKeys: record.capabilityKeys,
    };
    totalObjects += record.objectCount;
    totalProperties += record.propertyCount;
  }

  const meta = {
    generatedAt: new Date().toISOString(),
    bundlePath: path.resolve(args.bundle),
    bundleBytes: sourceLength,
    bundleParseStrategy,
    registryModuleId: registryInfo.moduleId,
    registryExportKey: registryInfo.exportKey,
    registryDiscovery: registryInfo.discovery,
    registrySourceHits: registryInfo.sourceHits,
    localizationMode: "dynamic localization module override",
    localizationOverrideModuleIds: [...new Set(localizationOverrides)].sort((a, b) => a - b),
    visualCount: Object.keys(visuals).length,
    totalObjectDefinitions: totalObjects,
    totalPropertyDefinitions: totalProperties,
    moduleFailureCount: failures.length,
  };

  const fullManifest = {
    meta,
    moduleFailures: failures,
    visuals,
  };

  const summaryManifest = {
    meta,
    moduleFailures: failures,
    visuals: summaryVisuals,
  };

  const traceManifest = buildTraceManifest({
    bundlePath: args.bundle,
    modules,
    registryInfo,
    visuals,
  });
  const analysisManifest = buildAnalysisManifest({
    bundlePath: args.bundle,
    visuals,
  });

  writeJson(path.join(args.outDir, "visual-capabilities.full.json"), fullManifest);
  writeJson(path.join(args.outDir, "visual-capabilities.summary.json"), summaryManifest);
  writeJson(path.join(args.outDir, "visual-capabilities.trace.json"), traceManifest);
  writeJson(path.join(args.outDir, "visual-capabilities.analysis.json"), analysisManifest);

  if (args.split) {
    for (const [visualType, record] of Object.entries(visuals)) {
      writeJson(path.join(args.outDir, "visuals", `${visualType}.json`), record);
    }
  }

  console.log(
    `Extracted ${meta.visualCount} visual definitions, `
      + `${meta.totalObjectDefinitions} object groups, `
      + `${meta.totalPropertyDefinitions} properties.`,
  );
  console.log(`Wrote ${path.resolve(args.outDir)}`);
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}
