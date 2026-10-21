const { test, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const originalFetch = global.fetch;
async function client() {
  const storage = new Map();
  global.sessionStorage = {
    getItem: (k) => storage.get(k) || null,
    setItem: (k, v) => storage.set(k, v),
    removeItem: (k) => storage.delete(k),
  };
  return import("../lib/client.ts");
}
afterEach(() => {
  global.fetch = originalFetch;
});
test("browser calls include cookies and no bearer secret", async () => {
  const api = await client();
  global.fetch = async (url, options) => {
    assert.equal(url, "http://localhost:8000/api/v1/auth/me");
    assert.equal(options.credentials, "include");
    assert.equal(options.headers.Authorization, undefined);
    return new Response(JSON.stringify({ subject: "reader" }), { status: 200 });
  };
  assert.equal((await api.request("/auth/me")).subject, "reader");
});
test("network-uncertain retry keeps idempotency key; success clears it", async () => {
  const api = await client();
  let attempt = 0;
  const keys = [];
  global.fetch = async (url, options) => {
    keys.push(options.headers["Idempotency-Key"]);
    if (attempt++ === 0) throw new Error("offline");
    return new Response("{}", { status: 201 });
  };
  await assert.rejects(() => api.mutation("/test", { value: 1 }));
  await api.mutation("/test", { value: 1 });
  await api.mutation("/test", { value: 1 });
  assert.equal(keys[0], keys[1]);
  assert.notEqual(keys[1], keys[2]);
});
test("execution conflict exposes recorded failure reason", async () => {
  const api = await client();
  global.fetch = async () =>
    new Response(
      JSON.stringify({ status: "FAILED", failure_reason: "Proposal expired." }),
      { status: 409 },
    );
  await assert.rejects(
    () => api.request("/execution", {}),
    (e) =>
      e.status === 409 &&
      e.message === "Proposal expired." &&
      e.payload.status === "FAILED",
  );
});
test("logout accepts empty response", async () => {
  const api = await client();
  global.fetch = async () => new Response(null, { status: 204 });
  assert.equal(await api.request("/auth/logout", {}), null);
});

test("proposal conflict includes evidence reasons", async () => {
  const api = await client();
  global.fetch = async () => new Response(JSON.stringify({
    detail: { message: "No usable transfer proposal.", issues: [
      { reference: "PLANT", message: "Inventory evidence is stale." }
    ]}
  }), { status: 409 });
  await assert.rejects(() => api.request("/proposal", {}), e =>
    e.status === 409 && e.message.includes("PLANT: Inventory evidence is stale."));
});
