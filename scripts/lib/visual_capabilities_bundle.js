"use strict";

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
    source,
    modules,
    sourceLength: source.length,
    bundleParseStrategy: bounds.strategy,
  };
}

function createRuntime(bundlePath) {
  const context = createContext();
  const {
    source,
    modules,
    sourceLength,
    bundleParseStrategy,
  } = loadBundleModules(bundlePath, context);
  const cache = {};
  const failures = [];
  const localizationOverrides = [];

  function isLocalizationModule(fn) {
    const sourceText = Function.prototype.toString.call(fn);
    return sourceText.includes("i.d(t,{D:function(){return") || sourceText.includes('i.d(t,{D:function(){return ');
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
    source,
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

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function getModuleSource(modules, moduleId) {
  const fn = modules[moduleId];
  if (!fn) {
    return null;
  }
  return Function.prototype.toString.call(fn);
}

function findMatchingDelimiter(source, startIndex, openChar, closeChar) {
  if (startIndex < 0 || source[startIndex] !== openChar) {
    return -1;
  }
  let depth = 0;
  let inString = null;
  let escaped = false;
  for (let i = startIndex; i < source.length; i += 1) {
    const ch = source[i];
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === inString) {
        inString = null;
      }
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      inString = ch;
      continue;
    }
    if (ch === openChar) {
      depth += 1;
      continue;
    }
    if (ch === closeChar) {
      depth -= 1;
      if (depth === 0) {
        return i;
      }
    }
  }
  return -1;
}

function splitTopLevel(text, separator) {
  const parts = [];
  let start = 0;
  let parenDepth = 0;
  let braceDepth = 0;
  let bracketDepth = 0;
  let inString = null;
  let escaped = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === inString) {
        inString = null;
      }
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      inString = ch;
      continue;
    }
    if (ch === "(") {
      parenDepth += 1;
      continue;
    }
    if (ch === ")") {
      parenDepth -= 1;
      continue;
    }
    if (ch === "{") {
      braceDepth += 1;
      continue;
    }
    if (ch === "}") {
      braceDepth -= 1;
      continue;
    }
    if (ch === "[") {
      bracketDepth += 1;
      continue;
    }
    if (ch === "]") {
      bracketDepth -= 1;
      continue;
    }
    if (
      ch === separator
      && parenDepth === 0
      && braceDepth === 0
      && bracketDepth === 0
    ) {
      parts.push(text.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(text.slice(start));
  return parts.map((part) => part.trim()).filter(Boolean);
}

function parseModuleExports(moduleSource) {
  const marker = "i.d(t,{";
  const markerIndex = moduleSource.indexOf(marker);
  if (markerIndex === -1) {
    return {};
  }
  const objectStart = markerIndex + marker.length - 1;
  const objectEnd = findMatchingDelimiter(moduleSource, objectStart, "{", "}");
  if (objectEnd === -1) {
    return {};
  }
  const body = moduleSource.slice(objectStart + 1, objectEnd);
  const exports = {};
  const exportRegex = /([A-Za-z_$][\w$]*):function\(\)\{return ([A-Za-z_$][\w$]*)\}/g;
  let match = exportRegex.exec(body);
  while (match) {
    exports[match[1]] = match[2];
    match = exportRegex.exec(body);
  }
  return exports;
}

function parseModuleImports(moduleSource) {
  const imports = {};
  const importRegex = /\b([A-Za-z_$][\w$]*)=i\((\d+)\)/g;
  let match = importRegex.exec(moduleSource);
  while (match) {
    imports[match[1]] = Number(match[2]);
    match = importRegex.exec(moduleSource);
  }
  return imports;
}

function extractAssignedObjectLiteral(moduleSource, localSymbol) {
  if (!localSymbol) {
    return null;
  }
  const pattern = new RegExp(`\\b${escapeRegExp(localSymbol)}\\s*=\\s*\\{`);
  const match = pattern.exec(moduleSource);
  if (!match) {
    return null;
  }
  const objectStart = moduleSource.indexOf("{", match.index);
  const objectEnd = findMatchingDelimiter(moduleSource, objectStart, "{", "}");
  if (objectEnd === -1) {
    return null;
  }
  return {
    symbol: localSymbol,
    start: objectStart,
    end: objectEnd,
    text: moduleSource.slice(objectStart, objectEnd + 1),
  };
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function parseObjectEntries(literalText) {
  const entries = {};
  const body = literalText.slice(1, -1);
  for (const part of splitTopLevel(body, ",")) {
    const colonParts = splitTopLevel(part, ":");
    if (colonParts.length < 2) {
      continue;
    }
    const key = colonParts[0];
    if (!/^[A-Za-z_$][\w$]*$/.test(key)) {
      continue;
    }
    entries[key] = colonParts.slice(1).join(":").trim();
  }
  return entries;
}

function findBestVisualObjectLiteral(moduleSource, preferredSymbol) {
  const candidates = [];
  const seenStarts = new Set();

  function addCandidate(symbol) {
    const literal = extractAssignedObjectLiteral(moduleSource, symbol);
    if (!literal || seenStarts.has(literal.start)) {
      return;
    }
    seenStarts.add(literal.start);
    const entries = parseObjectEntries(literal.text);
    const visualEntryValues = Object.entries(entries)
      .filter(([key]) => KNOWN_VISUAL_KEYS.includes(key))
      .map(([, value]) => value);
    const visualHits = visualEntryValues.length;
    if (visualHits > 0) {
      const simpleValueHits = visualEntryValues.filter((value) => !value.startsWith("{")).length;
      const objectLiteralHits = visualEntryValues.filter((value) => value.startsWith("{")).length;
      candidates.push({
        ...literal,
        entries,
        visualHits,
        score: visualHits * 100 + simpleValueHits * 10 - objectLiteralHits * 20,
      });
    }
  }

  if (preferredSymbol) {
    addCandidate(preferredSymbol);
  }

  const assignRegex = /\b([A-Za-z_$][\w$]*)=\{/g;
  let match = assignRegex.exec(moduleSource);
  while (match) {
    addCandidate(match[1]);
    match = assignRegex.exec(moduleSource);
  }

  candidates.sort((a, b) => b.score - a.score || b.visualHits - a.visualHits || a.start - b.start);
  return candidates[0] || null;
}

function parseProviderReference(expression) {
  if (!expression) {
    return { kind: "unknown" };
  }
  let match = /\(\s*0\s*,\s*([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\s*\)/.exec(expression);
  if (match) {
    return {
      kind: "moduleExport",
      importAlias: match[1],
      exportName: match[2],
    };
  }
  match = /([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)/.exec(expression);
  if (match) {
    return {
      kind: "moduleExport",
      importAlias: match[1],
      exportName: match[2],
    };
  }
  match = /^([A-Za-z_$][\w$]*)$/.exec(expression.trim());
  if (match) {
    return {
      kind: "localSymbol",
      localSymbol: match[1],
    };
  }
  return { kind: "unknown" };
}

function shortenSnippet(text, maxLength = 1200) {
  if (!text) {
    return null;
  }
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) {
    return compact;
  }
  return `${compact.slice(0, maxLength - 3)}...`;
}

function normalizeRequiredTypes(requiredTypes) {
  if (!Array.isArray(requiredTypes)) {
    return [];
  }
  return requiredTypes.map((entry) => {
    if (!entry || typeof entry !== "object") {
      return { kind: "unknown" };
    }
    return {
      kind: Object.keys(entry).sort().join("+") || "unknown",
      rawKeys: Object.keys(entry).sort(),
    };
  });
}

function normalizeTypeDefinition(typeDef) {
  if (!typeDef || typeof typeDef !== "object" || Array.isArray(typeDef)) {
    return { kind: "unknown", rawKeys: [] };
  }
  if (typeDef.enumeration && typeof typeDef.enumeration === "object") {
    const values = Array.isArray(typeDef.enumeration.allMembers)
      ? typeDef.enumeration.allMembers
        .map((member) => member && typeof member === "object" ? member.value : undefined)
        .filter((value) => value !== undefined)
      : [];
    return {
      kind: "enum",
      rawKeys: ["enumeration"],
      values,
    };
  }
  const rawKeys = Object.keys(typeDef).sort();
  const primaryKey = rawKeys[0] || "unknown";
  const result = {
    kind: primaryKey,
    rawKeys,
  };
  if (primaryKey === "formatting" && typeDef.formatting && typeof typeDef.formatting === "object") {
    result.formattingKinds = Object.keys(typeDef.formatting).sort();
  }
  if (primaryKey === "fill" && typeDef.fill && typeof typeDef.fill === "object") {
    result.fillKinds = Object.keys(typeDef.fill).sort();
  }
  return result;
}

function normalizePropertyDefinition(propertyDefinition) {
  const definition = propertyDefinition && typeof propertyDefinition === "object" ? propertyDefinition : {};
  return {
    displayName: definition.displayName || null,
    description: definition.description || null,
    placeHolderText: definition.placeHolderText || null,
    suppressFormatPainterCopy: definition.suppressFormatPainterCopy === true,
    formatStringProperty: definition.formatStringProperty
      ? sanitize(definition.formatStringProperty)
      : null,
    type: normalizeTypeDefinition(definition.type),
  };
}

function normalizeObjectDefinitions(objects) {
  const output = {};
  for (const [objectName, objectDefinition] of Object.entries(objects || {})) {
    const properties = objectDefinition?.properties && typeof objectDefinition.properties === "object"
      ? objectDefinition.properties
      : {};
    const normalizedProperties = {};
    for (const [propertyName, propertyDefinition] of Object.entries(properties)) {
      normalizedProperties[propertyName] = normalizePropertyDefinition(propertyDefinition);
    }
    output[objectName] = {
      displayName: objectDefinition?.displayName || null,
      description: objectDefinition?.description || null,
      propertyCount: Object.keys(normalizedProperties).length,
      properties: normalizedProperties,
    };
  }
  return output;
}

function normalizeDataRoles(dataRoles) {
  return (dataRoles || []).map((role) => ({
    name: role.name,
    displayName: role.displayName || null,
    description: role.description || null,
    kind: role.kind ?? null,
    displayOrder: role.displayOrder ?? null,
    joinPredicate: role.joinPredicate ?? null,
    cartesianKind: role.cartesianKind ?? null,
    requiredTypes: normalizeRequiredTypes(role.requiredTypes),
  }));
}

function collectRoleNames(value, out = new Set()) {
  if (Array.isArray(value)) {
    value.forEach((item) => collectRoleNames(item, out));
    return out;
  }
  if (!value || typeof value !== "object") {
    return out;
  }
  if (value.for && typeof value.for === "object" && typeof value.for.in === "string") {
    out.add(value.for.in);
  }
  if (value.bind && typeof value.bind === "object" && typeof value.bind.to === "string") {
    out.add(value.bind.to);
  }
  if (typeof value.role === "string") {
    out.add(value.role);
  }
  Object.values(value).forEach((item) => collectRoleNames(item, out));
  return out;
}

function collectDataReductionAlgorithms(value, out = new Set()) {
  if (Array.isArray(value)) {
    value.forEach((item) => collectDataReductionAlgorithms(item, out));
    return out;
  }
  if (!value || typeof value !== "object") {
    return out;
  }
  if (value.dataReductionAlgorithm && typeof value.dataReductionAlgorithm === "object") {
    Object.keys(value.dataReductionAlgorithm).forEach((name) => out.add(name));
  }
  Object.values(value).forEach((item) => collectDataReductionAlgorithms(item, out));
  return out;
}

function normalizeConditions(conditions) {
  return (conditions || []).map((condition) => Object.entries(condition || {})
    .map(([roleName, constraints]) => ({
      role: roleName,
      min: constraints?.min ?? null,
      max: constraints?.max ?? null,
      kind: constraints?.kind ?? null,
    }))
    .sort((a, b) => a.role.localeCompare(b.role)));
}

function normalizeDataViewMappings(dataViewMappings) {
  return (dataViewMappings || []).map((mapping, index) => {
    const shapeKinds = Object.keys(mapping || {}).filter((key) => key !== "conditions");
    const conditionSets = normalizeConditions(mapping?.conditions);
    const roleNames = [...collectRoleNames(mapping)].sort();
    const dataReductionAlgorithms = [...collectDataReductionAlgorithms(mapping)].sort();
    return {
      index,
      shapeKinds,
      conditionSets,
      conditionCount: conditionSets.length,
      roleNames,
      dataReductionAlgorithms,
      rawKeys: Object.keys(mapping || {}).sort(),
    };
  });
}

function normalizeBehaviorFlags(capabilities) {
  const behavior = {};
  for (const [key, value] of Object.entries(capabilities || {})) {
    if (["dataRoles", "objects", "dataViewMappings"].includes(key)) {
      continue;
    }
    const sanitized = sanitize(value);
    if (sanitized !== undefined) {
      behavior[key] = sanitized;
    }
  }
  return behavior;
}

function buildAnalysisManifest({ bundlePath, visuals }) {
  const analysisVisuals = {};
  for (const [visualType, record] of Object.entries(visuals)) {
    const capabilities = record.capabilities || {};
    analysisVisuals[visualType] = {
      visualType,
      plugin: {
        name: record.plugin?.name || visualType,
        titleKey: record.plugin?.titleKey || null,
        watermarkKey: record.plugin?.watermarkKey || null,
      },
      dataRoles: normalizeDataRoles(record.dataRoles),
      objects: normalizeObjectDefinitions(capabilities.objects || {}),
      dataViewMappings: normalizeDataViewMappings(capabilities.dataViewMappings || []),
      behavior: normalizeBehaviorFlags(capabilities),
    };
  }
  return {
    meta: {
      generatedAt: new Date().toISOString(),
      bundlePath: path.resolve(bundlePath),
      visualCount: Object.keys(analysisVisuals).length,
    },
    visuals: analysisVisuals,
  };
}

function extractLocalSymbolSnippet(moduleSource, localSymbol) {
  if (!moduleSource || !localSymbol) {
    return null;
  }
  const fnPattern = new RegExp(`function ${escapeRegExp(localSymbol)}\\(`);
  const fnMatch = fnPattern.exec(moduleSource);
  if (fnMatch) {
    const bodyStart = moduleSource.indexOf("{", fnMatch.index);
    const bodyEnd = findMatchingDelimiter(moduleSource, bodyStart, "{", "}");
    if (bodyEnd !== -1) {
      return shortenSnippet(moduleSource.slice(fnMatch.index, bodyEnd + 1));
    }
  }

  const objectPattern = new RegExp(`\\b${escapeRegExp(localSymbol)}\\s*=\\s*\\{`);
  const objectMatch = objectPattern.exec(moduleSource);
  if (objectMatch) {
    const bodyStart = moduleSource.indexOf("{", objectMatch.index);
    const bodyEnd = findMatchingDelimiter(moduleSource, bodyStart, "{", "}");
    if (bodyEnd !== -1) {
      return shortenSnippet(moduleSource.slice(objectMatch.index, bodyEnd + 1));
    }
  }

  const genericPattern = new RegExp(`\\b${escapeRegExp(localSymbol)}\\b`);
  const genericMatch = genericPattern.exec(moduleSource);
  if (!genericMatch) {
    return null;
  }
  const start = Math.max(0, genericMatch.index - 120);
  const end = Math.min(moduleSource.length, genericMatch.index + 1080);
  return shortenSnippet(moduleSource.slice(start, end));
}

function extractImportedReferences(snippet, providerModuleSource) {
  if (!snippet || !providerModuleSource) {
    return [];
  }
  const imports = parseModuleImports(providerModuleSource);
  const references = new Map();
  const refRegex = /\b([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)(\.[A-Za-z_$][\w$]*)*/g;
  let match = refRegex.exec(snippet);
  while (match) {
    const importAlias = match[1];
    const moduleId = imports[importAlias];
    if (moduleId === undefined) {
      match = refRegex.exec(snippet);
      continue;
    }
    const exportName = match[2];
    const memberPath = match[3] ? match[3].slice(1).split(".") : [];
    const rawRef = match[0];
    if (!references.has(rawRef)) {
      references.set(rawRef, {
        rawRef,
        importAlias,
        moduleId,
        exportName,
        memberPath,
      });
    }
    match = refRegex.exec(snippet);
  }
  return [...references.values()].sort((a, b) => a.rawRef.localeCompare(b.rawRef));
}

function buildTraceManifest({ bundlePath, modules, registryInfo, visuals }) {
  const registryModuleSource = getModuleSource(modules, registryInfo.moduleId);
  const registryExports = parseModuleExports(registryModuleSource || "");
  const registryImports = parseModuleImports(registryModuleSource || "");
  const registryLocalSymbol = registryInfo.exportKey
    ? registryExports[registryInfo.exportKey] || null
    : null;
  const capabilitiesLiteral = findBestVisualObjectLiteral(registryModuleSource || "", registryLocalSymbol);
  const registryEntries = capabilitiesLiteral?.entries || {};

  const traceVisuals = {};
  for (const visualType of Object.keys(visuals).sort()) {
    const expression = registryEntries[visualType] || null;
    const providerRef = parseProviderReference(expression);
    let provider = {
      kind: providerRef.kind,
      moduleId: null,
      exportName: null,
      localSymbol: null,
      importAlias: providerRef.importAlias || null,
      snippet: null,
    };

    if (providerRef.kind === "moduleExport") {
      const moduleId = registryImports[providerRef.importAlias] ?? null;
      const providerModuleSource = moduleId !== null ? getModuleSource(modules, moduleId) : null;
      const providerExports = providerModuleSource ? parseModuleExports(providerModuleSource) : {};
      const localSymbol = providerExports[providerRef.exportName] || null;
      const snippet = extractLocalSymbolSnippet(providerModuleSource, localSymbol);
      provider = {
        kind: providerRef.kind,
        moduleId,
        exportName: providerRef.exportName,
        localSymbol,
        importAlias: providerRef.importAlias,
        snippet,
        importedReferences: extractImportedReferences(snippet, providerModuleSource),
      };
    } else if (providerRef.kind === "localSymbol") {
      const snippet = extractLocalSymbolSnippet(registryModuleSource, providerRef.localSymbol);
      provider = {
        kind: providerRef.kind,
        moduleId: registryInfo.moduleId,
        exportName: null,
        localSymbol: providerRef.localSymbol,
        importAlias: null,
        snippet,
        importedReferences: extractImportedReferences(snippet, registryModuleSource),
      };
    } else {
      provider.importedReferences = [];
    }

    traceVisuals[visualType] = {
      registryEntry: {
        expression,
        snippet: expression ? shortenSnippet(`${visualType}:${expression}`) : null,
      },
      provider,
    };
  }

  return {
    meta: {
      generatedAt: new Date().toISOString(),
      bundlePath: path.resolve(bundlePath),
      registryModuleId: registryInfo.moduleId,
      registryExportKey: registryInfo.exportKey,
      registryLocalSymbol,
      capabilitiesLocalSymbol: capabilitiesLiteral?.symbol || null,
      visualCount: Object.keys(traceVisuals).length,
    },
    visuals: traceVisuals,
  };
}

function formatTraceReport(visualType, traceManifest) {
  const trace = traceManifest.visuals[visualType];
  if (!trace) {
    const available = Object.keys(traceManifest.visuals).sort().join(", ");
    throw new Error(`Unknown visual type "${visualType}". Available: ${available}`);
  }
  const lines = [
    `Visual: ${visualType}`,
    `Registry module: ${traceManifest.meta.registryModuleId}`,
    `Registry export: ${traceManifest.meta.registryExportKey || "(direct export)"}`,
    `Registry symbol: ${traceManifest.meta.registryLocalSymbol || "(unresolved)"}`,
    `Capabilities symbol: ${traceManifest.meta.capabilitiesLocalSymbol || "(unresolved)"}`,
    "",
    "Registry entry:",
    `  ${trace.registryEntry.expression || "(unresolved)"}`,
    "",
    "Provider:",
    `  kind: ${trace.provider.kind}`,
    `  moduleId: ${trace.provider.moduleId ?? "(unresolved)"}`,
    `  export: ${trace.provider.exportName || "(n/a)"}`,
    `  localSymbol: ${trace.provider.localSymbol || "(unresolved)"}`,
    `  importAlias: ${trace.provider.importAlias || "(n/a)"}`,
    "",
    "Snippet:",
    trace.provider.snippet || "(unresolved)",
  ];
  if (Array.isArray(trace.provider.importedReferences) && trace.provider.importedReferences.length) {
    lines.push("", "Imported references:");
    for (const reference of trace.provider.importedReferences.slice(0, 12)) {
      lines.push(`  ${reference.rawRef} -> module ${reference.moduleId}`);
    }
  }
  return lines.join("\n");
}

module.exports = {
  buildAnalysisManifest,
  KNOWN_VISUAL_KEYS,
  buildTraceManifest,
  buildVisualRecord,
  createRuntime,
  findRegistry,
  formatTraceReport,
  writeJson,
};
