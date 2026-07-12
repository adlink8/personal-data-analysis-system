import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_HOST = process.env.HOST || "127.0.0.1";
const DEFAULT_PORT = Number.parseInt(process.env.PORT || "8789", 10);
const DEFAULT_REST_BASE_URL = process.env.PERSONAL_DATA_REST_URL || "http://127.0.0.1:8000";
const PROTOCOL_VERSION = "2025-06-18";

const WIDGETS = {
  graph: {
    uri: "ui://personal-data/memory-graph-widget.html",
    file: path.join(__dirname, "public", "memory-graph-widget.html"),
    name: "Memory graph widget",
    description: "Read-only visualization for bounded memory graph results."
  },
  review: {
    uri: "ui://personal-data/relation-review-widget.html",
    file: path.join(__dirname, "public", "relation-review-widget.html"),
    name: "Relation review widget",
    description: "Read-only table for memory relation review queue results."
  },
  data: {
    uri: "ui://personal-data/data-browser-widget.html",
    file: path.join(__dirname, "public", "data-browser-widget.html"),
    name: "Data browser widget",
    description: "Read-only browser for /data event, memory, relation, aggregate, timeline, export, and quality tools."
  }
};

const noAuth = [{ type: "noauth" }];
const readOnlyAnnotations = {
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: false
};

const textContent = (text) => [{ type: "text", text }];

const objectSchema = (properties, required = []) => ({
  type: "object",
  properties,
  required,
  additionalProperties: true
});

const graphOutputSchema = objectSchema({
  ok: { type: "boolean" },
  scope: { type: "object" },
  counts: { type: "object" },
  nodes: { type: "array", items: { type: "object" } },
  edges: { type: "array", items: { type: "object" } },
  truncated: { type: "boolean" },
  error: { type: "string" }
}, ["ok"]);

const reviewOutputSchema = objectSchema({
  ok: { type: "boolean" },
  count: { type: "number" },
  items: { type: "array", items: { type: "object" } },
  truncated: { type: "boolean" },
  error: { type: "string" }
}, ["ok"]);

const dataListOutputSchema = objectSchema({
  ok: { type: "boolean" },
  scope: { type: "object" },
  counts: { type: "object" },
  count: { type: "number" },
  total: { type: "number" },
  limit: { type: "number" },
  offset: { type: "number" },
  fields: { type: "array", items: { type: "string" } },
  filters: { type: "object" },
  available: { type: "boolean" },
  items: { type: "array", items: { type: "object" } },
  truncated: { type: "boolean" },
  error: { type: "string" }
}, ["ok"]);

const dataAggregateOutputSchema = objectSchema({
  ok: { type: "boolean" },
  scope: { type: "object" },
  counts: { type: "object" },
  count: { type: "number" },
  limit: { type: "number" },
  group_by: { type: "array", items: { type: "string" } },
  filters: { type: "object" },
  rows: { type: "array", items: { type: "object" } },
  error: { type: "string" }
}, ["ok"]);

const dataExportOutputSchema = objectSchema({
  ok: { type: "boolean" },
  scope: { type: "object" },
  counts: { type: "object" },
  format: { type: "string" },
  text: { type: "string" },
  content: {},
  fields: { type: "array", items: { type: "string" } },
  filters: { type: "object" },
  hard_cap: { type: "number" },
  truncated: { type: "boolean" },
  error: { type: "string" }
}, ["ok"]);

const dataQualityOutputSchema = objectSchema({
  ok: { type: "boolean" },
  generated_at: { type: "string" },
  tables: { type: "object" },
  events: { type: "object" },
  memories: { type: "object" },
  relations: { type: "object" },
  judgments: { type: "object" },
  warnings: { type: "array", items: { type: "string" } },
  error: { type: "string" }
}, ["ok"]);

const toolDescriptors = [
  {
    name: "search",
    title: "Search personal data",
    description: "Use this when the user asks to search their local personal event history or memory-adjacent records.",
    inputSchema: objectSchema({
      query: { type: "string", description: "Natural-language search query." },
      top_k: { type: "integer", minimum: 1, maximum: 20, default: 5 },
      source: { type: "string", description: "Optional source filter." }
    }, ["query"]),
    outputSchema: objectSchema({
      ok: { type: "boolean" },
      query: { type: "string" },
      count: { type: "number" },
      results: { type: "array", items: { type: "object" } },
      error: { type: "string" }
    }, ["ok"]),
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Searching personal data",
      "openai/toolInvocation/invoked": "Search complete"
    }
  },
  {
    name: "fetch",
    title: "Fetch personal data record",
    description: "Use this when the user asks to open one local event id or memory subject returned by a prior search.",
    inputSchema: objectSchema({
      id: { type: "string", description: "Event id or memory subject." },
      kind: { type: "string", enum: ["auto", "event", "memory"], default: "auto" },
      neighbors: { type: "integer", minimum: 0, maximum: 5, default: 2 }
    }, ["id"]),
    outputSchema: objectSchema({
      ok: { type: "boolean" },
      id: { type: "string" },
      kind: { type: "string" },
      item: { type: "object" },
      error: { type: "string" }
    }, ["ok", "id"]),
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Fetching record",
      "openai/toolInvocation/invoked": "Record fetched"
    }
  },
  {
    name: "show_memory_graph",
    title: "Show memory graph",
    description: "Use this when the user asks to inspect a bounded long-term memory graph or compare rule and LLM judgment edges.",
    inputSchema: objectSchema({
      subject: { type: "string", description: "Optional subject focus." },
      hops: { type: "integer", minimum: 0, maximum: 3, default: 1 },
      include_llm: { type: "boolean", default: true },
      limit: { type: "integer", minimum: 1, maximum: 200, default: 80 }
    }),
    outputSchema: graphOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      ui: { resourceUri: WIDGETS.graph.uri },
      "openai/outputTemplate": WIDGETS.graph.uri,
      "openai/toolInvocation/invoking": "Loading memory graph",
      "openai/toolInvocation/invoked": "Memory graph ready"
    }
  },
  {
    name: "show_memory_subject",
    title: "Show memory subject",
    description: "Use this when the user asks to inspect one memory subject and its local neighbors.",
    inputSchema: objectSchema({
      subject: { type: "string", description: "Memory subject to inspect." },
      neighbors: { type: "integer", minimum: 0, maximum: 5, default: 2 }
    }, ["subject"]),
    outputSchema: graphOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      ui: { resourceUri: WIDGETS.graph.uri },
      "openai/outputTemplate": WIDGETS.graph.uri,
      "openai/toolInvocation/invoking": "Loading memory subject",
      "openai/toolInvocation/invoked": "Memory subject ready"
    }
  },
  {
    name: "show_relation_review_queue",
    title: "Show relation review queue",
    description: "Use this when the user asks to list memory relation candidates or LLM judgments that need human review.",
    inputSchema: objectSchema({
      limit: { type: "integer", minimum: 1, maximum: 100, default: 50 },
      status: { type: "string", enum: ["review", "accepted", "rejected", "all"], default: "review" }
    }),
    outputSchema: reviewOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      ui: { resourceUri: WIDGETS.review.uri },
      "openai/outputTemplate": WIDGETS.review.uri,
      "openai/toolInvocation/invoking": "Loading review queue",
      "openai/toolInvocation/invoked": "Review queue ready"
    }
  },
  {
    name: "get_system_stats",
    title: "Get system stats",
    description: "Use this when the user asks for current local personal data system counts or health summary.",
    inputSchema: objectSchema({}),
    outputSchema: objectSchema({
      ok: { type: "boolean" },
      stats: { type: "object" },
      error: { type: "string" }
    }, ["ok"]),
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Loading stats",
      "openai/toolInvocation/invoked": "Stats ready"
    }
  },
  {
    name: "data_list_events",
    title: "Data.list_events",
    description: "Page through local personal events with bounded filters. Defaults to compact fields without full content.",
    inputSchema: objectSchema({
      limit: { type: "integer", minimum: 1, maximum: 500, default: 100 },
      offset: { type: "integer", minimum: 0, default: 0 },
      source: { type: "string" },
      service: { type: "string" },
      category: { type: "string" },
      category_v2: { type: "string", description: "Alias for category, matching REST /data/events category_v2." },
      start_time: { type: "string" },
      end_time: { type: "string" },
      keyword: { type: "string" },
      fields: { type: "string", description: "Comma-separated event fields. Content fields are returned only when requested." },
      order: { type: "string", enum: ["desc", "asc"], default: "desc" }
    }),
    outputSchema: dataListOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Loading events",
      "openai/toolInvocation/invoked": "Events loaded"
    }
  },
  {
    name: "data_list_memories",
    title: "Data.list_memories",
    description: "Page through long-term memory records with type and subject filters.",
    inputSchema: objectSchema({
      limit: { type: "integer", minimum: 1, maximum: 500, default: 100 },
      offset: { type: "integer", minimum: 0, default: 0 },
      memory_type: { type: "string" },
      subject_like: { type: "string" }
    }),
    outputSchema: dataListOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Loading memories",
      "openai/toolInvocation/invoked": "Memories loaded"
    }
  },
  {
    name: "data_list_relations",
    title: "Data.list_relations",
    description: "Page through rule and LLM long-term memory relations.",
    inputSchema: objectSchema({
      limit: { type: "integer", minimum: 1, maximum: 500, default: 100 },
      offset: { type: "integer", minimum: 0, default: 0 },
      relation_type: { type: "string" },
      subject: { type: "string" },
      from_memory_id: { type: "string" },
      to_memory_id: { type: "string" },
      status: { type: "string", enum: ["review", "accepted", "rejected", "all"], default: "all" }
    }),
    outputSchema: dataListOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Loading relations",
      "openai/toolInvocation/invoked": "Relations loaded"
    }
  },
  {
    name: "data_aggregate",
    title: "Data.aggregate",
    description: "Aggregate local events, memories, or relations by month, source, service, category, memory_type, or relation_type.",
    inputSchema: objectSchema({
      group_by: { type: "string", default: "month", description: "Single group field. Kept for backward compatibility." },
      group_by_fields: {
        type: "array",
        items: { type: "string", enum: ["month", "source", "service", "category", "memory_type", "relation_type"] },
        description: "Preferred multi-field grouping, for example [\"source\", \"service\"]. Overrides group_by when provided."
      },
      metric: { type: "string", enum: ["count"], default: "count" },
      source: { type: "string" },
      service: { type: "string" },
      category: { type: "string" },
      category_v2: { type: "string" },
      keyword: { type: "string" },
      start_time: { type: "string" },
      end_time: { type: "string" },
      limit: { type: "integer", minimum: 1, maximum: 500, default: 100 }
    }),
    outputSchema: dataAggregateOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Aggregating data",
      "openai/toolInvocation/invoked": "Aggregation ready"
    }
  },
  {
    name: "data_timeline",
    title: "Data.timeline",
    description: "Return a day/month/year timeline for a subject or keyword across event titles/content and memory evidence.",
    inputSchema: objectSchema({
      subject: { type: "string" },
      bucket: { type: "string", enum: ["day", "month", "year"], default: "month" },
      keyword: { type: "string", description: "Alias for subject; filters titles/content when subject is not provided." },
      source: { type: "string" },
      service: { type: "string" },
      category: { type: "string" },
      category_v2: { type: "string" },
      start_time: { type: "string" },
      end_time: { type: "string" },
      limit: { type: "integer", minimum: 1, maximum: 500, default: 100 }
    }),
    outputSchema: dataAggregateOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Building timeline",
      "openai/toolInvocation/invoked": "Timeline ready"
    }
  },
  {
    name: "data_export_all",
    title: "Data.export_all",
    description: "Export a bounded slice of local events as JSONL or CSV for offline analysis.",
    inputSchema: objectSchema({
      format: { type: "string", enum: ["jsonl", "csv", "json"], default: "jsonl" },
      limit: { type: "integer", minimum: 1, maximum: 5000, default: 500 },
      offset: { type: "integer", minimum: 0, default: 0 },
      source: { type: "string" },
      service: { type: "string" },
      category: { type: "string" },
      category_v2: { type: "string" },
      start_time: { type: "string" },
      end_time: { type: "string" },
      keyword: { type: "string" },
      fields: { type: "string" },
      order: { type: "string", enum: ["desc", "asc"], default: "desc" }
    }),
    outputSchema: dataExportOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Exporting data",
      "openai/toolInvocation/invoked": "Export ready"
    }
  },
  {
    name: "data_export_query",
    title: "Data.export_query",
    description: "Export a bounded filtered query as JSONL or CSV.",
    inputSchema: objectSchema({
      query: { type: "string", description: "Keyword query applied to title/content." },
      format: { type: "string", enum: ["jsonl", "csv", "json"], default: "jsonl" },
      limit: { type: "integer", minimum: 1, maximum: 5000, default: 500 },
      offset: { type: "integer", minimum: 0, default: 0 },
      source: { type: "string" },
      service: { type: "string" },
      category: { type: "string" },
      category_v2: { type: "string" },
      keyword: { type: "string" },
      start_time: { type: "string" },
      end_time: { type: "string" },
      fields: { type: "string" },
      order: { type: "string", enum: ["desc", "asc"], default: "desc" }
    }),
    outputSchema: dataExportOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Exporting query",
      "openai/toolInvocation/invoked": "Query export ready"
    }
  },
  {
    name: "data_get_event_by_id",
    title: "Data.get_event_by_id",
    description: "Fetch one event by exact event_id without auto-detecting memory subjects.",
    inputSchema: objectSchema({
      event_id: { type: "string" },
      fields: { type: "string" }
    }, ["event_id"]),
    outputSchema: objectSchema({
      ok: { type: "boolean" },
      event_id: { type: "string" },
      found: { type: "boolean" },
      fields: { type: "array", items: { type: "string" } },
      item: { type: "object" },
      error: { type: "string" }
    }, ["ok"]),
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Fetching event",
      "openai/toolInvocation/invoked": "Event fetched"
    }
  },
  {
    name: "data_get_memory_by_id",
    title: "Data.get_memory_by_id",
    description: "Fetch one long-term memory by exact memory_id without subject matching.",
    inputSchema: objectSchema({
      memory_id: { type: "string" },
      include_evidence: { type: "boolean", default: true }
    }, ["memory_id"]),
    outputSchema: objectSchema({
      ok: { type: "boolean" },
      memory_id: { type: "string" },
      found: { type: "boolean" },
      item: { type: "object" },
      evidence: { type: "array", items: { type: "object" } },
      error: { type: "string" }
    }, ["ok"]),
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Fetching memory",
      "openai/toolInvocation/invoked": "Memory fetched"
    }
  },
  {
    name: "data_quality_report",
    title: "Data.data_quality_report",
    description: "Return read-only quality checks for event, memory, relation, and LLM judgment data.",
    inputSchema: objectSchema({}),
    outputSchema: dataQualityOutputSchema,
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      "openai/toolInvocation/invoking": "Checking data quality",
      "openai/toolInvocation/invoked": "Quality report ready"
    }
  },
  {
    name: "show_data_browser",
    title: "Show Data browser",
    description: "Render the read-only Data browser widget. The widget uses the MCP Apps bridge to call the Data.* tools backed by /data/* endpoints.",
    inputSchema: objectSchema({
      view: { type: "string", enum: ["events", "memories", "relations", "aggregate", "timeline", "quality"], default: "events" },
      query: { type: "string", description: "Optional initial keyword or subject." },
      source: { type: "string" },
      service: { type: "string" },
      category: { type: "string" }
    }),
    outputSchema: objectSchema({
      ok: { type: "boolean" },
      view: { type: "string" },
      actions: { type: "array", items: { type: "string" } },
      error: { type: "string" }
    }, ["ok"]),
    annotations: readOnlyAnnotations,
    securitySchemes: noAuth,
    _meta: {
      securitySchemes: noAuth,
      ui: { resourceUri: WIDGETS.data.uri },
      "openai/outputTemplate": WIDGETS.data.uri,
      "openai/toolInvocation/invoking": "Opening Data browser",
      "openai/toolInvocation/invoked": "Data browser ready"
    }
  }
];

const DATA_TOOL_NAMES = new Set([
  "data_list_events",
  "data_list_memories",
  "data_list_relations",
  "data_aggregate",
  "data_timeline",
  "data_export_all",
  "data_export_query",
  "data_get_event_by_id",
  "data_get_memory_by_id",
  "data_quality_report"
]);

for (const tool of toolDescriptors) {
  if (DATA_TOOL_NAMES.has(tool.name)) {
    tool._meta.ui = { ...(tool._meta.ui || {}), visibility: ["model", "app"] };
    tool._meta["openai/widgetAccessible"] = true;
  }
}

function clampInt(value, fallback, min, max) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
}

function buildUrl(baseUrl, pathname, params = {}) {
  const url = new URL(pathname, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

async function readJsonResponse(response) {
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`REST returned non-JSON HTTP ${response.status}: ${text.slice(0, 160)}`);
  }
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `REST HTTP ${response.status}`);
  }
  return payload?.data ?? payload;
}

function makeRestClient(baseUrl, fetchImpl = fetch) {
  return {
    async get(pathname, params) {
      const response = await fetchImpl(buildUrl(baseUrl, pathname, params), {
        method: "GET",
        headers: { Accept: "application/json" }
      });
      return readJsonResponse(response);
    },
    async post(pathname, body) {
      const response = await fetchImpl(buildUrl(baseUrl, pathname), {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      });
      return readJsonResponse(response);
    }
  };
}

function normalizeGraph(data, scope = {}) {
  const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
  const edges = Array.isArray(data?.edges) ? data.edges : [];
  return {
    ok: data?.ok ?? true,
    scope: data?.scope || scope,
    counts: data?.counts || { nodes: nodes.length, edges: edges.length, truncated: Boolean(data?.truncated) },
    nodes,
    edges,
    truncated: Boolean(data?.truncated || data?.counts?.truncated)
  };
}

function normalizeReview(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  return {
    ok: data?.ok ?? true,
    count: Number.isFinite(data?.count) ? data.count : items.length,
    items,
    truncated: Boolean(data?.truncated)
  };
}

function subjectToGraph(data, subject, neighbors) {
  const root = data?.memory || data;
  const neighborRows = Array.isArray(data?.neighbors) ? data.neighbors : [];
  const rootId = String(root?.id || root?.memory_id || root?.subject || subject);
  const nodes = [
    {
      id: rootId,
      subject: root?.subject || subject,
      memory_type: root?.memory_type || root?.type || "memory",
      memory_subtype: root?.memory_subtype || root?.subtype || "",
      summary: root?.summary || root?.description || root?.content || ""
    },
    ...neighborRows.map((row, index) => ({
      id: String(row.id || row.memory_id || row.subject || `neighbor_${index}`),
      subject: row.subject || row.target_subject || row.source_subject || `neighbor_${index}`,
      memory_type: row.memory_type || row.type || "memory",
      memory_subtype: row.memory_subtype || row.subtype || "",
      summary: row.summary || row.description || row.content || ""
    }))
  ];
  const edges = neighborRows.map((row, index) => ({
    source: rootId,
    target: String(row.id || row.memory_id || row.subject || `neighbor_${index}`),
    relation: row.relation || row.relation_type || "neighbor",
    edge_source: row.edge_source || "rule",
    confidence: row.confidence,
    gate_status: row.gate_status
  }));
  return normalizeGraph({
    scope: { subject, neighbors },
    nodes,
    edges,
    truncated: neighborRows.length >= neighbors
  });
}

function errorResult(error, fallback = {}) {
  return {
    ok: false,
    error: error instanceof Error ? error.message : String(error),
    ...fallback
  };
}

function eventFilterParams(args = {}) {
  return {
    limit: args.limit,
    offset: args.offset,
    source: args.source,
    service: args.service,
    category: args.category || args.category_v2,
    category_v2: args.category_v2,
    start_time: args.start_time,
    end_time: args.end_time,
    keyword: args.keyword,
    fields: args.fields,
    order: args.order
  };
}

function listCount(data) {
  if (Number.isFinite(data?.counts?.returned)) return data.counts.returned;
  if (Number.isFinite(data?.count)) return data.count;
  if (Array.isArray(data?.items)) return data.items.length;
  if (Array.isArray(data?.rows)) return data.rows.length;
  return 0;
}

function normalizeDataList(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  return {
    ...data,
    counts: data?.counts || {
      total: Number.isFinite(data?.total) ? data.total : items.length,
      returned: Number.isFinite(data?.count) ? data.count : items.length,
      limit: data?.limit,
      offset: data?.offset
    },
    items,
    truncated: Boolean(data?.truncated)
  };
}

function normalizeDataRows(data) {
  const rows = Array.isArray(data?.rows) ? data.rows : Array.isArray(data?.items) ? data.items : [];
  return {
    ...data,
    counts: data?.counts || {
      returned: Number.isFinite(data?.count) ? data.count : rows.length,
      limit: data?.limit
    },
    rows
  };
}

function normalizeExport(data) {
  const text = data?.text ?? data?.content ?? "";
  return {
    ...data,
    text,
    content: data?.content ?? text,
    counts: data?.counts || {
      total: data?.total,
      returned: Number.isFinite(data?.count) ? data.count : undefined,
      limit: data?.limit,
      offset: data?.offset
    },
    truncated: Boolean(data?.truncated)
  };
}

async function callTool(name, args = {}, options = {}) {
  const rest = options.restClient || makeRestClient(options.restBaseUrl || DEFAULT_REST_BASE_URL, options.fetchImpl);

  try {
    if (name === "search") {
      const query = String(args.query || "").trim();
      if (!query) throw new Error("query is required");
      const topK = clampInt(args.top_k, 5, 1, 20);
      const results = await rest.post("/search/semantic", { query, top_k: topK, source: args.source });
      return {
        structuredContent: {
          ok: true,
          query,
          count: Array.isArray(results) ? results.length : 0,
          results: Array.isArray(results) ? results : []
        },
        content: textContent(`Found ${Array.isArray(results) ? results.length : 0} result(s) for "${query}".`)
      };
    }

    if (name === "fetch") {
      const id = String(args.id || "").trim();
      if (!id) throw new Error("id is required");
      const kind = args.kind || "auto";
      const neighbors = clampInt(args.neighbors, 2, 0, 5);
      let item;
      let resolvedKind = kind;
      if (kind === "event") {
        item = await rest.get(`/event/${encodeURIComponent(id)}`);
      } else if (kind === "memory") {
        item = await rest.get(`/memory/${encodeURIComponent(id)}`, { neighbors });
      } else {
        try {
          item = await rest.get(`/event/${encodeURIComponent(id)}`);
          resolvedKind = "event";
        } catch {
          item = await rest.get(`/memory/${encodeURIComponent(id)}`, { neighbors });
          resolvedKind = "memory";
        }
      }
      return {
        structuredContent: { ok: true, id, kind: resolvedKind, item },
        content: textContent(`Fetched ${resolvedKind} record ${id}.`)
      };
    }

    if (name === "show_memory_graph") {
      const scope = {
        subject: args.subject || undefined,
        hops: clampInt(args.hops, 1, 0, 3),
        include_llm: args.include_llm !== false,
        limit: clampInt(args.limit, 80, 1, 200)
      };
      const data = await rest.get("/memory/graph", scope);
      const structuredContent = normalizeGraph(data, scope);
      return {
        structuredContent,
        content: textContent(`Memory graph has ${structuredContent.nodes.length} node(s) and ${structuredContent.edges.length} edge(s).`),
        _meta: { ui: { resourceUri: WIDGETS.graph.uri }, "openai/outputTemplate": WIDGETS.graph.uri }
      };
    }

    if (name === "show_memory_subject") {
      const subject = String(args.subject || "").trim();
      if (!subject) throw new Error("subject is required");
      const neighbors = clampInt(args.neighbors, 2, 0, 5);
      const data = await rest.get(`/memory/${encodeURIComponent(subject)}`, { neighbors });
      const structuredContent = subjectToGraph(data, subject, neighbors);
      return {
        structuredContent,
        content: textContent(`Loaded memory subject "${subject}" with ${structuredContent.edges.length} neighbor edge(s).`),
        _meta: { ui: { resourceUri: WIDGETS.graph.uri }, "openai/outputTemplate": WIDGETS.graph.uri }
      };
    }

    if (name === "show_relation_review_queue") {
      const params = {
        limit: clampInt(args.limit, 50, 1, 100),
        status: args.status && args.status !== "all" ? args.status : undefined
      };
      const data = await rest.get("/memory/relation-review", params);
      const structuredContent = normalizeReview(data);
      return {
        structuredContent,
        content: textContent(`Relation review queue has ${structuredContent.count} item(s).`),
        _meta: { ui: { resourceUri: WIDGETS.review.uri }, "openai/outputTemplate": WIDGETS.review.uri }
      };
    }

    if (name === "get_system_stats") {
      const stats = await rest.get("/stats");
      return {
        structuredContent: { ok: true, stats },
        content: textContent("Loaded personal data system stats.")
      };
    }

    if (name === "data_list_events") {
      const data = normalizeDataList(await rest.get("/data/events", eventFilterParams(args)));
      return {
        structuredContent: data,
        content: textContent(`Loaded ${listCount(data)} event(s).`)
      };
    }

    if (name === "data_list_memories") {
      const data = normalizeDataList(await rest.get("/data/memories", {
        limit: args.limit,
        offset: args.offset,
        memory_type: args.memory_type,
        subject_like: args.subject_like
      }));
      return {
        structuredContent: data,
        content: textContent(`Loaded ${listCount(data)} memory record(s).`)
      };
    }

    if (name === "data_list_relations") {
      const data = normalizeDataList(await rest.get("/data/relations", {
        limit: args.limit,
        offset: args.offset,
        relation_type: args.relation_type,
        subject: args.subject,
        from_memory_id: args.from_memory_id,
        to_memory_id: args.to_memory_id,
        status: args.status && args.status !== "all" ? args.status : undefined
      }));
      return {
        structuredContent: data,
        content: textContent(`Loaded ${listCount(data)} relation record(s).`)
      };
    }

    if (name === "data_aggregate") {
      const groupBy = Array.isArray(args.group_by_fields) && args.group_by_fields.length
        ? args.group_by_fields.join(",")
        : (args.group_by || "month");
      const data = normalizeDataRows(await rest.get("/data/aggregate", {
        group_by: groupBy,
        metric: args.metric || "count",
        source: args.source,
        service: args.service,
        category: args.category || args.category_v2,
        category_v2: args.category_v2,
        keyword: args.keyword,
        start_time: args.start_time,
        end_time: args.end_time,
        limit: args.limit
      }));
      return {
        structuredContent: data,
        content: textContent(`Aggregation returned ${listCount(data)} row(s).`)
      };
    }

    if (name === "data_timeline") {
      const subject = String(args.subject || args.keyword || "").trim();
      const data = normalizeDataRows(await rest.get("/data/timeline", {
        subject: subject || undefined,
        bucket: args.bucket || "month",
        source: args.source,
        service: args.service,
        category: args.category || args.category_v2,
        category_v2: args.category_v2,
        start_time: args.start_time,
        end_time: args.end_time,
        limit: args.limit
      }));
      return {
        structuredContent: data,
        content: textContent(subject
          ? `Timeline for "${subject}" returned ${listCount(data)} bucket(s).`
          : `Timeline returned ${listCount(data)} bucket(s).`)
      };
    }

    if (name === "data_export_all") {
      const data = normalizeExport(await rest.get("/data/export", {
        ...eventFilterParams(args),
        format: args.format || "jsonl"
      }));
      return {
        structuredContent: data,
        content: textContent(`Exported ${listCount(data)} row(s) as ${data?.format || args.format || "jsonl"}.`)
      };
    }

    if (name === "data_export_query") {
      const query = String(args.query || "").trim();
      const data = normalizeExport(await rest.get("/data/export", {
        ...eventFilterParams({ ...args, keyword: args.keyword || query }),
        query,
        format: args.format || "jsonl"
      }));
      return {
        structuredContent: data,
        content: textContent(`Exported ${listCount(data)} query row(s) as ${data?.format || args.format || "jsonl"}.`)
      };
    }

    if (name === "data_get_event_by_id") {
      const eventId = String(args.event_id || "").trim();
      if (!eventId) throw new Error("event_id is required");
      const data = await rest.get(`/data/event/${encodeURIComponent(eventId)}`, { fields: args.fields });
      return {
        structuredContent: data,
        content: textContent(`Fetched event ${eventId}.`)
      };
    }

    if (name === "data_get_memory_by_id") {
      const memoryId = String(args.memory_id || "").trim();
      if (!memoryId) throw new Error("memory_id is required");
      const data = await rest.get(`/data/memory/${encodeURIComponent(memoryId)}`, {
        include_evidence: args.include_evidence !== false
      });
      return {
        structuredContent: data,
        content: textContent(`Fetched memory ${memoryId}.`)
      };
    }

    if (name === "data_quality_report") {
      const data = await rest.get("/data/quality");
      return {
        structuredContent: data,
        content: textContent("Loaded data quality report.")
      };
    }

    if (name === "show_data_browser") {
      const structuredContent = {
        ok: true,
        view: args.view || "events",
        initialFilters: {
          query: args.query,
          source: args.source,
          service: args.service,
          category: args.category
        },
        actions: [
          "data_list_events",
          "data_list_memories",
          "data_list_relations",
          "data_aggregate",
          "data_timeline",
          "data_export_all",
          "data_export_query",
          "data_get_event_by_id",
          "data_get_memory_by_id",
          "data_quality_report"
        ]
      };
      return {
        structuredContent,
        content: textContent("Opened read-only Data browser."),
        _meta: { ui: { resourceUri: WIDGETS.data.uri }, "openai/outputTemplate": WIDGETS.data.uri }
      };
    }

    throw new Error(`Unknown tool: ${name}`);
  } catch (error) {
    const descriptor = toolDescriptors.find((tool) => tool.name === name);
    const fallback = name === "show_memory_graph" || name === "show_memory_subject"
      ? { scope: {}, counts: { nodes: 0, edges: 0, truncated: false }, nodes: [], edges: [], truncated: false }
      : name === "show_relation_review_queue"
        ? { count: 0, items: [], truncated: false }
        : name === "show_data_browser"
          ? { view: args.view || "events", actions: [] }
        : {};
    return {
      isError: true,
      structuredContent: errorResult(error, fallback),
      content: textContent(`Tool ${name} failed: ${error instanceof Error ? error.message : String(error)}`),
      _meta: descriptor?._meta?.ui?.resourceUri
        ? { ui: { resourceUri: descriptor._meta.ui.resourceUri }, "openai/outputTemplate": descriptor._meta.ui.resourceUri }
        : undefined
    };
  }
}

function jsonRpcResult(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function jsonRpcError(id, code, message) {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}

async function handleRpc(request, options = {}) {
  const { id, method, params } = request || {};
  if (!method) return jsonRpcError(id, -32600, "Invalid JSON-RPC request");

  if (method === "initialize") {
    return jsonRpcResult(id, {
      protocolVersion: PROTOCOL_VERSION,
      capabilities: { tools: {}, resources: {} },
      serverInfo: { name: "personal-data-chatgpt-app", version: "0.1.0" },
      instructions: "Read-only local personal data tools. Do not claim write or approval actions are available."
    });
  }

  if (method === "notifications/initialized") {
    return null;
  }

  if (method === "tools/list") {
    return jsonRpcResult(id, { tools: toolDescriptors });
  }

  if (method === "tools/call") {
    const name = params?.name;
    const args = params?.arguments || {};
    const result = await callTool(name, args, options);
    return jsonRpcResult(id, result);
  }

  if (method === "resources/list") {
    return jsonRpcResult(id, {
      resources: Object.values(WIDGETS).map((widget) => ({
        uri: widget.uri,
        name: widget.name,
        description: widget.description,
        mimeType: "text/html;profile=mcp-app"
      }))
    });
  }

  if (method === "resources/read") {
    const uri = params?.uri;
    const widget = Object.values(WIDGETS).find((candidate) => candidate.uri === uri);
    if (!widget) return jsonRpcError(id, -32602, `Unknown resource: ${uri}`);
    const text = await readFile(widget.file, "utf8");
    return jsonRpcResult(id, {
      contents: [{
        uri: widget.uri,
        mimeType: "text/html;profile=mcp-app",
        text,
        _meta: {
          ui: {
            prefersBorder: true,
            csp: { connect_domains: [], resource_domains: [] }
          },
          "openai/widgetPrefersBorder": true,
          "openai/widgetCSP": { connect_domains: [], resource_domains: [] }
        }
      }]
    });
  }

  return jsonRpcError(id, -32601, `Method not found: ${method}`);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

function sendJson(res, statusCode, body) {
  const payload = JSON.stringify(body);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(payload),
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, MCP-Protocol-Version, Mcp-Session-Id"
  });
  res.end(payload);
}

function sendText(res, statusCode, text, contentType = "text/plain; charset=utf-8") {
  res.writeHead(statusCode, {
    "Content-Type": contentType,
    "Content-Length": Buffer.byteLength(text),
    "Access-Control-Allow-Origin": "*"
  });
  res.end(text);
}

export function createAppServer(options = {}) {
  const restBaseUrl = options.restBaseUrl || DEFAULT_REST_BASE_URL;
  const fetchImpl = options.fetchImpl;

  return createServer(async (req, res) => {
    try {
      const url = new URL(req.url || "/", `http://${req.headers.host || "127.0.0.1"}`);

      if (req.method === "OPTIONS") {
        res.writeHead(204, {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, MCP-Protocol-Version, Mcp-Session-Id"
        });
        res.end();
        return;
      }

      if (req.method === "GET" && url.pathname === "/health") {
        sendJson(res, 200, { ok: true, status: "ok", restBaseUrl });
        return;
      }

      if (req.method === "GET" && url.pathname.startsWith("/widgets/")) {
        const filename = path.basename(url.pathname);
        const file = path.join(__dirname, "public", filename);
        if (!file.startsWith(path.join(__dirname, "public")) || !existsSync(file)) {
          sendText(res, 404, "Not found");
          return;
        }
        const html = await readFile(file, "utf8");
        sendText(res, 200, html, filename.endsWith(".html") ? "text/html;profile=mcp-app; charset=utf-8" : "text/plain; charset=utf-8");
        return;
      }

      if (req.method === "POST" && url.pathname === "/mcp") {
        let body;
        try {
          body = JSON.parse(await readBody(req) || "{}");
        } catch {
          sendJson(res, 400, jsonRpcError(null, -32700, "Parse error"));
          return;
        }
        const rpcOptions = { restBaseUrl, fetchImpl, restClient: options.restClient };
        const result = Array.isArray(body)
          ? (await Promise.all(body.map((item) => handleRpc(item, rpcOptions)))).filter(Boolean)
          : await handleRpc(body, rpcOptions);
        if (result === null) {
          res.writeHead(204);
          res.end();
          return;
        }
        sendJson(res, 200, result);
        return;
      }

      if (url.pathname === "/mcp") {
        sendJson(res, 405, jsonRpcError(null, -32000, "Use POST /mcp for JSON-RPC requests"));
        return;
      }

      sendText(res, 404, "Not found");
    } catch (error) {
      sendJson(res, 500, jsonRpcError(null, -32603, error instanceof Error ? error.message : String(error)));
    }
  });
}

export { callTool, handleRpc, makeRestClient, toolDescriptors, WIDGETS };

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const server = createAppServer();
  server.listen(DEFAULT_PORT, DEFAULT_HOST, () => {
    console.log(`[apps] personal-data ChatGPT MCP server listening at http://${DEFAULT_HOST}:${DEFAULT_PORT}`);
    console.log(`[apps] MCP endpoint: http://${DEFAULT_HOST}:${DEFAULT_PORT}/mcp`);
    console.log(`[apps] REST backend: ${DEFAULT_REST_BASE_URL}`);
  });
}
