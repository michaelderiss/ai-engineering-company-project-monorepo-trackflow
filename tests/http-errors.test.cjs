const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("../uis/backoffice/node_modules/typescript");
const root = path.join(__dirname, "..");

function client(fetch) {
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync(path.join(root, "packages/shared/http.ts"), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(source, { exports, fetch, Headers, FormData, AbortSignal, Error });
  return exports;
}

test("offline errors are safe and actionable", async () => {
  const api = client(async () => { throw new TypeError("PRIVATE_NETWORK_DETAILS"); });
  await assert.rejects(api.requestJson("https://example.invalid"), (error) => error.message.includes("Check your connection") && !error.message.includes("PRIVATE"));
});

test("server errors do not expose response contents", async () => {
  const api = client(async () => new Response(JSON.stringify({message: "PRIVATE_SERVER_DETAILS"}), {status:500}));
  await assert.rejects(api.requestJson("https://example.invalid"), (error) => error.status === 500 && !error.message.includes("PRIVATE") && error.message.includes("try again"));
});

test("invalid JSON does not expose parser errors", async () => {
  const api = client(async () => new Response("broken json"));
  await assert.rejects(api.requestJson("https://example.invalid"), /unreadable response/);
});

test("null and malformed data are rejected before rendering", async () => {
  const api = client(async () => new Response("null"));
  await assert.rejects(api.requestJson("https://example.invalid"), /incomplete data/);
});

test("field errors are sanitized", async () => {
  const api = client(async () => new Response(JSON.stringify({errors:{title:"PRIVATE_FIELD_VALUE"}}), {status:400}));
  await assert.rejects(api.requestJson("https://example.invalid"), (error) => error.fields.title === "Please check this field." && !error.message.includes("PRIVATE"));
});

test("FormData keeps browser-controlled multipart headers", async () => {
  let contentType;
  const api = client(async (_, options) => { contentType = options.headers.get("Content-Type"); return new Response('{"ok":true}'); });
  await api.requestJson("https://example.invalid", {method:"POST",body:new FormData()});
  assert.equal(contentType, null);
});

test("dispatch JSON null produces a safe fallback", () => {
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync(path.join(root,"uis/backoffice/lib/milestone2.ts"), "utf8"), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  vm.runInNewContext(source, {exports, console:{warn(){}}, process:{cwd:()=>root}, require:(id)=>id === "node:fs" ? {readFileSync:()=>"null"} : require(id)});
  assert.equal(exports.readMilestone2Order().orderId, "Unavailable");
});

test("generator read failure exits nonzero without raw details", () => {
  const errors = [];
  const process = {argv:[],env:{},exitCode:0};
  const source = fs.readFileSync(path.join(root,"scripts/generate_milestone2_output.cjs"), "utf8");
  vm.runInNewContext(source, {__dirname:path.join(root,"scripts"),process,console:{error:(value)=>errors.push(value),log(){}},require:(id)=>id === "node:fs" ? {readFileSync:()=>{throw new Error("PRIVATE_PATH");}} : id === "../src/milestone2-output.js" ? require("../src/milestone2-output.js") : require(id)});
  assert.equal(process.exitCode, 1);
  assert.ok(errors[0].includes("try again"));
  assert.ok(!errors[0].includes("PRIVATE_PATH"));
});