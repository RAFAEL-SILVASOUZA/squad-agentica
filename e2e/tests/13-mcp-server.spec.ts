import { test, expect } from "@playwright/test";
import { Api, BASE_URL, uniqueEmail, sleep } from "../helpers";
import crypto from "node:crypto";

function generateCodeVerifier() {
  return crypto.randomBytes(32).toString("base64url");
}

function generateCodeChallenge(verifier: string) {
  return crypto.createHash("sha256").update(verifier).digest("base64url");
}

test.describe("MCP Server E2E", () => {
  let api: Api;
  let userEmail: string;
  let userId: string;

  test.beforeEach(async ({ page }) => {
    api = new Api();
    userEmail = uniqueEmail("mcp-test");
    
    await page.goto('/register');
    await page.locator("#name").fill("MCP Test User");
    await page.locator("#email").fill(userEmail);
    await page.locator("#password").fill("QaE2e1234!");
    await page.locator("#confirmPassword").fill("QaE2e1234!");
    await page.locator('button[type="submit"]').click();
    await page.locator('nav[aria-label="Navegação principal"]').waitFor({ state: "visible", timeout: 30000 });
  });

  test.afterEach(async () => {
    // Cleanup user is typically done via DB helper if needed, 
    // but here we just let them be or use api.delete if available.
    // Since we have a unique email per test, it's fine for E2E.
  });

  test("Full MCP OAuth and Tools Flow", async ({ page }) => {
    // 1. POST /mcp/mcp without token -> 401
    const res401 = await page.request.post(`${BASE_URL}/mcp/mcp`, {
      data: {
        jsonrpc: "2.0",
        id: 1,
        method: "tools/list",
        params: {},
      },
    });
    expect(res401.status()).toBe(401);
    expect(res401.headers()["www-authenticate"]).toBeDefined();

    // 2. GET /.well-known/oauth-protected-resource
    const resResource = await api.get("/.well-known/oauth-protected-resource");
    expect(resResource.status).toBe(200);
    expect(resResource.body).toHaveProperty("resource");
    expect(resResource.body).toHaveProperty("authorization_servers");

    // 3. GET /.well-known/oauth-authorization-server
    const resAuthServer = await api.get("/.well-known/oauth-authorization-server");
    expect(resAuthServer.status).toBe(200);
    expect(resAuthServer.body).toHaveProperty("issuer");
    expect(resAuthServer.body).toHaveProperty("authorization_endpoint");
    expect(resAuthServer.body).toHaveProperty("token_endpoint");

    // 4. POST /oauth/register (DCR)
    const resRegister = await api.post("/oauth/register", {
      client_name: "MCP Test Client",
      redirect_uris: ["http://localhost:9999/callback"],
      grant_types: ["authorization_code"],
      response_types: ["code"],
      scope: "mcp:full",
    });
    expect([200, 201]).toContain(resRegister.status);
    const clientId = resRegister.body.client_id;
    expect(clientId).toBeDefined();

    // 5. GET /oauth/authorize (with browser session)
    const codeVerifier = generateCodeVerifier();
    const codeChallenge = generateCodeChallenge(codeVerifier);
    const state = crypto.randomBytes(16).toString("hex");
    const redirectUri = "http://localhost:9999/callback";
    const resource = "http://localhost/mcp/mcp";

    const authUrl = `${BASE_URL}/oauth/authorize?` + new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      scope: "mcp:full",
      code_challenge: codeChallenge,
      code_challenge_method: "S256",
      state: state,
      resource: resource,
    }).toString();

    // Intercept the callback redirect so the browser doesn't need a real server
    let capturedCode: string | null = null;
    await page.route((url: URL) => url.href.startsWith(redirectUri), (route) => {
      const u = new URL(route.request().url());
      capturedCode = u.searchParams.get("code");
      route.fulfill({ status: 200, body: "<html><body>Callback received</body></html>" });
    });

    await page.goto(authUrl);

    // Should redirect to /mcp-consent
    await page.waitForURL(/.*\/mcp-consent/);
    expect(page.url()).toContain("/mcp-consent");

    // QA Visual: Consent page
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.screenshot({ path: "e2e/test-results/artifacts/mcp-consent.png" });

    // Click Autorizar
    await page.click('button:has-text("Autorizar")');

    // Wait for the callback to be captured
    await page.waitForURL((url: URL) => url.href.startsWith(redirectUri), { timeout: 15000 });
    expect(capturedCode).toBeDefined();
    const code = capturedCode!;

    // 6. POST /oauth/token (with code + PKCE)
    const resToken = await api.post("/oauth/token", {
      grant_type: "authorization_code",
      code: code,
      client_id: clientId,
      redirect_uri: redirectUri,
      code_verifier: codeVerifier,
    });
    expect(resToken.status).toBe(200);
    const accessToken = resToken.body.access_token;
    expect(accessToken).toBeDefined();

    // 7. MCP streamable HTTP handshake: initialize -> tools/list -> tools/call
    const mcpBase = BASE_URL + "/mcp/mcp";
    const mcpAuth = { Authorization: `Bearer ${accessToken}` };
    const mcpAccept = { Accept: "application/json, text/event-stream" };

    // 7a. initialize
    const initRes = await fetch(mcpBase, {
      method: "POST",
      headers: { ...mcpAuth, ...mcpAccept, "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
          protocolVersion: "2025-03-26",
          capabilities: {},
          clientInfo: { name: "e2e-test", version: "1.0" },
        },
      }),
    });
    expect(initRes.status).toBe(200);
    const sessionId = initRes.headers.get("mcp-session-id");
    expect(sessionId).toBeDefined();

    // 7b. notifications/initialized
    const sessionHeaders = { ...mcpAuth, ...mcpAccept, "Content-Type": "application/json", "Mcp-Session-Id": sessionId! };
    await fetch(mcpBase, {
      method: "POST",
      headers: sessionHeaders,
      body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
    });

    // 7c. tools/list
    const toolsRes = await fetch(mcpBase, {
      method: "POST",
      headers: sessionHeaders,
      body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }),
    });
    expect(toolsRes.status).toBe(200);
    const toolsText = await toolsRes.text();
    const toolsDataLines = toolsText.split("\n").filter(l => l.startsWith("data:"));
    const toolsResponse = JSON.parse(toolsDataLines[0].replace("data:", "").trim());
    expect(toolsResponse.result.tools).toBeDefined();
    expect(Array.isArray(toolsResponse.result.tools)).toBe(true);

    // 8. tools/call create_agent
    const agentRes = await fetch(mcpBase, {
      method: "POST",
      headers: sessionHeaders,
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 3,
        method: "tools/call",
        params: { name: "create_agent", arguments: { name: "E2E Test Agent" } },
      }),
    });
    expect(agentRes.status).toBe(200);
    const agentText = await agentRes.text();
    const agentDataLines = agentText.split("\n").filter(l => l.startsWith("data:"));
    const agentResponse = JSON.parse(agentDataLines[0].replace("data:", "").trim());
    // The tool returns the created agent as JSON; verify the name round-trips.
    expect(agentResponse.result.content[0].text).toContain("E2E Test Agent");

    // QA Visual: MCP Management Page
    await page.goto(`${BASE_URL}/mcp/server`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "e2e/test-results/artifacts/mcp-server.png" });
  });

  test("Consent page direct navigation and authorization", async ({ page }) => {
    // User is already registered and logged in from beforeEach

    // Register a real client via DCR
    const redirectUri = "http://localhost:9999/callback";
    const resRegister = await api.post("/oauth/register", {
      client_name: "Consent Test Client",
      redirect_uris: [redirectUri],
      grant_types: ["authorization_code"],
      response_types: ["code"],
      scope: "mcp:full",
    });
    expect([200, 201]).toContain(resRegister.status);
    const clientId = resRegister.body.client_id;
    const state = "test-state";
    
    const consentUrl = `${BASE_URL}/mcp-consent?` + new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      scope: "mcp:full",
      code_challenge: "challenge",
      code_challenge_method: "S256",
      state: state,
      resource: "http://localhost/mcp/mcp",
    }).toString();

    // Intercept the callback redirect
    let capturedCode: string | null = null;
    await page.route((url: URL) => url.href.startsWith(redirectUri), (route) => {
      const u = new URL(route.request().url());
      capturedCode = u.searchParams.get("code");
      route.fulfill({ status: 200, body: "<html><body>Callback received</body></html>" });
    });

    await page.goto(consentUrl);
    expect(page.locator("text=Autorizar")).toBeVisible();
    await page.click('button:has-text("Autorizar")');

    await page.waitForURL((url: URL) => url.href.startsWith(redirectUri), { timeout: 15000 });
    expect(capturedCode).toBeDefined();
  });
});
