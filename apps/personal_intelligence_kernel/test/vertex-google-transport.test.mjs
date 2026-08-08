import test from "node:test";
import assert from "node:assert/strict";

import { createVertexGoogleTransport } from "../src/models/vertex-google-transport.mjs";

test("Vertex Gemini transport sends a bearer request and returns safe receipt payload", async () => {
  let call;
  const transport = createVertexGoogleTransport({
    project: "project-test",
    location: "global",
    tokenProvider: () => "test-token",
    fetchImpl: async (url, options) => {
      call = { url, options, body: JSON.parse(options.body) };
      return {
        ok: true,
        status: 200,
        async json() {
          return { modelVersion: "gemini-3.5-flash", candidates: [{ finishReason: "STOP", content: { parts: [{ text: JSON.stringify({ ready: true }) }] } }], usageMetadata: { promptTokenCount: 4, candidatesTokenCount: 3, totalTokenCount: 7 } };
        },
      };
    },
  });
  const result = await transport({ prompt: "return a compact JSON object", model: "gemini-3.5-flash", max_output_tokens: 32 }, { timeout_ms: 1000 });
  assert.equal(call.url, "https://aiplatform.googleapis.com/v1/projects/project-test/locations/global/publishers/google/models/gemini-3.5-flash:generateContent");
  assert.equal(call.options.headers.authorization, "Bearer test-token");
  assert.equal(call.body.contents[0].parts[0].text, "return a compact JSON object");
  assert.deepEqual(result.usage, { input_tokens: 4, output_tokens: 3 });
  assert.equal(result.payload.text, "{\"ready\":true}");
  assert.equal(result.provider, "vertex_google");
});
