#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const BUNDLE_MARKER = "!function(){var e,t,i,a,r,n,o=";
const BUNDLE_END_MARKER = "},s={};function l(e){";
const KNOWN_VISUAL_KEYS = [
  "actionButton",
  "advancedSlicerVisual",
  "areaChart",
  "azureMap",
  "barChart",
  "bookmarkNavigator",
  "cardVisual",
  "clusteredBarChart",
  "clusteredColumnChart",
  "columnChart",
  "decompositionTreeVisual",
  "donutChart",
  "filledMap",
  "funnel",
  "gauge",
  "image",
  "keyDriversVisual",
  "kpi",
  "lineChart",
  "lineClusteredColumnComboChart",
  "lineStackedColumnComboChart",
  "listSlicer",
  "map",
  "multiRowCard",
  "pageNavigator",
  "pieChart",
  "pivotTable",
  "pythonVisual",
  "qnaVisual",
  "ribbonChart",
  "scatterChart",
  "scriptVisual",
  "shape",
  "shapeMap",
  "slicer",
  "stackedAreaChart",
  "tableEx",
  "textSlicer",
  "textbox",
  "treemap",
  "waterfallChart",
];

function cloneDeep(value) {
  if (value === null || typeof value !== "object") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(cloneDeep);
  }
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    out[key] = cloneDeep(item);
  }
  return out;
}

function buildLodashShim() {
  return {
    omit(obj, keys) {
      const out = {};
      if (!obj || typeof obj !== "object") {
        return out;
      }
      const skip = new Set(keys || []);
      for (const [key, value] of Object.entries(obj)) {
        if (!skip.has(key)) {
          out[key] = value;
        }
      }
      return out;
    },
    pick(obj, keys) {
      const out = {};
      if (!obj || typeof obj !== "object") {
        return out;
      }
      for (const key of keys || []) {
        if (key in obj) {
          out[key] = obj[key];
        }
      }
      return out;
    },
    map(arr, fn) {
      return (arr || []).map(fn);
    },
    isEmpty(obj) {
      return !obj || Object.keys(obj).length === 0;
    },
    flatten(arr) {
      return (arr || []).flat();
    },
    forEach(arr, fn) {
      return (arr || []).forEach(fn);
    },
    includes(arr, value) {
      return (arr || []).includes(value);
    },
    uniq(arr) {
      return [...new Set(arr || [])];
    },
    chain(arr) {
      let value = arr;
      return {
        map(fn) {
          value = (value || []).map(fn);
          return this;
        },
        uniq() {
          value = [...new Set(value || [])];
          return this;
        },
        value() {
          return value;
        },
      };
    },
    noop() {},
    cloneDeep,
    isString(value) {
      return typeof value === "string";
    },
    isArray: Array.isArray,
    isObject(value) {
      return !!value && typeof value === "object";
    },
    assign: Object.assign,
    defaults(obj, ...sources) {
      return Object.assign({}, ...sources.reverse(), obj);
    },
    some(arr, fn) {
      return (arr || []).some(fn);
    },
    find(arr, fn) {
      return (arr || []).find(fn);
    },
    mapValues(obj, fn) {
      const out = {};
      for (const [key, value] of Object.entries(obj || {})) {
        out[key] = fn(value, key);
      }
      return out;
    },
    values(obj) {
      return Object.values(obj || {});
    },
    keys(obj) {
      return Object.keys(obj || {});
    },
    filter(arr, fn) {
      return (arr || []).filter(fn);
    },
    reduce(arr, fn, initial) {
      return (arr || []).reduce(fn, initial);
    },
    isEqual(a, b) {
      return JSON.stringify(a) === JSON.stringify(b);
    },
  };
}

function createContext() {
  const context = vm.createContext({
    _: buildLodashShim(),
    window: {},
    document: {
      currentScript: { src: "https://example.com/desktop.min.js" },
      getElementsByTagName() {
        return [];
      },
      head: {
        appendChild() {},
      },
      baseURI: "https://example.com/",
    },
    globalThis: {},
    self: {},
    URLSearchParams,
    console,
    alert() {},
    setTimeout,
    clearTimeout,
    TextEncoder,
    Promise,
    Symbol,
    trustedTypes: {
      createPolicy(_name, obj) {
        return obj;
      },
    },
  });
  context.globalThis = context;
  context.window = context;
  context.self = context;
  context.location = {
    href: "https://example.com/app",
    protocol: "https:",
  };
  return context;
}

function createStub(name = "stub") {
  const target = function stubTarget() {
    return createStub(`${name}()`);
  };
  return new Proxy(target, {
    get(_target, prop) {
      if (prop === Symbol.toPrimitive) {
        return () => name;
      }
      if (prop === "toString") {
        return () => `[${name}]`;
      }
      if (prop === "valueOf") {
        return () => name;
      }
      if (prop === "__esModule") {
        return true;
      }
      if (prop === "default") {
        return createStub(`${name}.default`);
      }
      return createStub(`${name}.${String(prop)}`);
    },
    apply() {
      return createStub(`${name}()`);
    },
    construct() {
      return createStub(`new ${name}`);
    },
    ownKeys() {
      return [];
    },
    getOwnPropertyDescriptor() {
      return { enumerable: true, configurable: true };
    },
  });
}

function findModuleObjectBounds(source) {
  const markerStart = source.indexOf(BUNDLE_MARKER);
  if (markerStart !== -1) {
    const markerEnd = source.indexOf(BUNDLE_END_MARKER, markerStart);
    if (markerEnd !== -1) {
      return {
        start: markerStart + BUNDLE_MARKER.length,
        end: markerEnd + 1,
        strategy: "fixed-markers",
      };
    }
  }

  const startMatch = /=\{[0-9]+:function\([A-Za-z_$]+,[A-Za-z_$]+,[A-Za-z_$]+\)\{/.exec(source);
  if (!startMatch) {
    throw new Error("Could not locate webpack module map start.");
  }
  const start = startMatch.index + 1;
  const endRegex = /\},[A-Za-z_$]+=\{\};function [A-Za-z_$]+\([A-Za-z_$]+\)\{/g;
  endRegex.lastIndex = start;
  const endMatch = endRegex.exec(source);
  if (!endMatch) {
    throw new Error("Could not locate webpack module map end.");
  }
  return {
    start,
    end: endMatch.index + 1,
    strategy: "regex-fallback",
  };
}

function loadBundleModules(bundlePath, context) {
  const source = fs.readFileSync(bundlePath, "utf8");
  const bounds = findModuleObjectBounds(source);
  const moduleObjectText = source.slice(bounds.start, bounds.end);
  const modules = vm.runInContext(`(${moduleObjectText})`, context, { timeout: 10000 });
  return {
    modules,
    sourceLength: source.length,
    bundleParseStrategy: bounds.strategy,
  };
}

function createRuntime(bundlePath) {
  const context = createContext();
  const {
    modules,
    sourceLength,
    bundleParseStrategy,
  } = loadBundleModules(bundlePath, context);
  const cache = {};
  const failures = [];
  const localizationOverrides = [];

  function isLocalizationModule(fn) {
    const source = Function.prototype.toString.call(fn);
    return source.includes("i.d(t,{D:function(){return") || source.includes('i.d(t,{D:function(){return ');
  }

  function req(id) {
    const fn = modules[id];
    if (fn && isLocalizationModule(fn)) {
      localizationOverrides.push(id);
      return {
        D(key) {
          return key;
        },
      };
    }
    if (cache[id]) {
      return cache[id].exports;
    }
    const module = { exports: {} };
    cache[id] = module;
    if (!fn) {
      module.exports = createStub(`m${id}`);
      return module.exports;
    }
    try {
      fn(module, module.exports, req);
    } catch (error) {
      failures.push({
        moduleId: id,
        message: error instanceof Error ? error.message : String(error),
      });
      if (!module.exports || Object.keys(module.exports).length === 0) {
        module.exports = createStub(`m${id}`);
      }
    }
    return module.exports;
  }

  req.d = (exports, definition) => {
    for (const key in definition) {
      if (!Object.prototype.hasOwnProperty.call(exports, key)) {
        Object.defineProperty(exports, key, {
          enumerable: true,
          get: definition[key],
        });
      }
    }
  };
  req.o = (obj, prop) => Object.prototype.hasOwnProperty.call(obj, prop);
  req.r = (exports) => {
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    Object.defineProperty(exports, "__esModule", { value: true });
  };
  req.n = (mod) => {
    const getter = mod && mod.__esModule ? () => mod.default : () => mod;
    req.d(getter, { a: getter });
    return getter;
  };
  req.t = (value) => value;
  req.g = context;
  req.amdO = {};
  req.hmd = (module) => module;
  req.bind = (_reqFn, id) => () => req(id);
  req.e = () => Promise.resolve();

  return {
    req,
    failures,
    sourceLength,
    modules,
    bundleParseStrategy,
    localizationOverrides,
  };
}

function sanitize(value, seen = new WeakSet()) {
  if (value === null || value === undefined) {
    return value;
  }
  if (typeof value === "function") {
    return undefined;
  }
  if (typeof value !== "object") {
    return value;
  }
  if (seen.has(value)) {
    return "[Circular]";
  }
  seen.add(value);
  if (Array.isArray(value)) {
    const out = [];
    for (const item of value) {
      const sanitized = sanitize(item, seen);
      if (sanitized !== undefined) {
        out.push(sanitized);
      }
    }
    return out;
  }
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    const sanitized = sanitize(item, seen);
    if (sanitized !== undefined) {
      out[key] = sanitized;
    }
  }
  return out;
}

function summarizeObjects(objects) {
  const objectNames = Object.keys(objects || {});
  const objectPropertyCounts = {};
  let propertyCount = 0;
  for (const objectName of objectNames) {
    const properties = objects[objectName]?.properties || {};
    const count = Object.keys(properties).length;
    objectPropertyCounts[objectName] = count;
    propertyCount += count;
  }
  return {
    objectNames,
    objectCount: objectNames.length,
    objectPropertyCounts,
    propertyCount,
  };
}

function sanitizePlugin(entry) {
  const sanitized = {};
  for (const [key, value] of Object.entries(entry || {})) {
    if (key === "capabilities" || typeof value === "function") {
      continue;
    }
    const clean = sanitize(value);
    if (clean !== undefined) {
      sanitized[key] = clean;
    }
  }
  return sanitized;
}

function buildVisualRecord(visualType, entry) {
  const capabilities = entry?.capabilities || entry;
  const sanitizedCapabilities = sanitize(capabilities);
  const objects = sanitizedCapabilities?.objects || {};
  const objectSummary = summarizeObjects(objects);
  const dataRoles = sanitizedCapabilities?.dataRoles || [];
  return {
    visualType,
    plugin: sanitizePlugin(entry),
    capabilityKeys: Object.keys(sanitizedCapabilities || {}),
    dataRoleNames: dataRoles.map((role) => role.name),
    dataRoles,
    ...objectSummary,
    capabilities: sanitizedCapabilities,
  };
}

function scoreRegistryCandidate(candidate) {
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    return 0;
  }
  const keys = Object.keys(candidate);
  if (keys.length < 10) {
    return 0;
  }
  const visualKeyHits = KNOWN_VISUAL_KEYS.filter((key) => key in candidate);
  if (visualKeyHits.length < 8) {
    return 0;
  }
  let capabilityHits = 0;
  for (const key of visualKeyHits.slice(0, 12)) {
    const value = candidate[key];
    const capabilities = value?.capabilities || value;
    if (
      capabilities
      && typeof capabilities === "object"
      && (
        Array.isArray(capabilities.dataRoles)
        || (capabilities.objects && typeof capabilities.objects === "object")
      )
    ) {
      capabilityHits += 1;
    }
  }
  if (capabilityHits < 4) {
    return 0;
  }
  return visualKeyHits.length * 10 + capabilityHits * 25 + keys.length;
}

function findRegistryBySource(modules) {
  const candidates = [];
  for (const [moduleId, fn] of Object.entries(modules)) {
    const source = Function.prototype.toString.call(fn);
    let hits = 0;
    for (const visualKey of KNOWN_VISUAL_KEYS) {
      if (source.includes(`${visualKey}:`)) {
        hits += 1;
      }
    }
    if (hits >= 8) {
      candidates.push({ moduleId: Number(moduleId), hits });
    }
  }
  candidates.sort((a, b) => b.hits - a.hits || a.moduleId - b.moduleId);
  return candidates;
}

function findRegistry(req, modules) {
  const sourceCandidates = findRegistryBySource(modules);
  const inspected = new Set();

  function inspectModule(moduleId) {
    if (inspected.has(moduleId)) {
      return null;
    }
    inspected.add(moduleId);
    const exports = req(moduleId);
    const candidates = [{ exportKey: null, value: exports }];
    for (const [exportKey, value] of Object.entries(exports || {})) {
      candidates.push({ exportKey, value });
    }
    let best = null;
    for (const candidate of candidates) {
      const score = scoreRegistryCandidate(candidate.value);
      if (!best || score > best.score) {
        best = { ...candidate, score };
      }
    }
    if (best && best.score > 0) {
      return {
        moduleId,
        exportKey: best.exportKey,
        registry: best.value,
        score: best.score,
      };
    }
    return null;
  }

  for (const candidate of sourceCandidates) {
    const resolved = inspectModule(candidate.moduleId);
    if (resolved) {
      return {
        ...resolved,
        discovery: "source-scan",
        sourceHits: candidate.hits,
      };
    }
  }

  let bestOverall = null;
  for (const moduleId of Object.keys(modules).map(Number).sort((a, b) => a - b)) {
    const resolved = inspectModule(moduleId);
    if (resolved && (!bestOverall || resolved.score > bestOverall.score)) {
      bestOverall = resolved;
    }
  }
  if (bestOverall) {
    return {
      ...bestOverall,
      discovery: "export-scan",
      sourceHits: null,
    };
  }
  throw new Error("Could not discover the visual registry module dynamically.");
}

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

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
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

  writeJson(path.join(args.outDir, "visual-capabilities.full.json"), fullManifest);
  writeJson(path.join(args.outDir, "visual-capabilities.summary.json"), summaryManifest);

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
