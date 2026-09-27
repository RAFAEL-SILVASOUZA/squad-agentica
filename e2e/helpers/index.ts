/**
 * Helpers compartilhados da suíte E2E (nó qa-e2e).
 *
 * - `api.ts`: cliente REST direto (registro/login/CRUD) para o usuário de teste,
 *   independente da sessão do navegador (o navegador loga por NextAuth).
 * - `db.ts`: ponte para e2e/tools/db.py (psycopg) — seed de pipelines/aprovações
 *   e limpeza, já que CRUD de pipeline e HITL estão quebrados (F9, F1/F6).
 * - `mcp.ts`: servidor MCP fake rodando como container na rede do compose,
 *   reutilizando `tests/integration/fake_mcp_server.py`.
 */
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import fs from "node:fs";
import crypto from "node:crypto";

const pexecFile = promisify(execFile);

export const BASE_URL = process.env.E2E_BASE_URL || "http://localhost";
export const EMAIL_PREFIX = "qa-e2e-";
export const PASSWORD = "QaE2e1234!";

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const PYTHON = path.join(
  REPO_ROOT,
  "tests",
  "integration",
  ".venv",
  "Scripts",
  "python.exe"
);
const DB_SCRIPT = path.join(REPO_ROOT, "e2e", "tools", "db.py");
const FAKE_MCP = path.join(REPO_ROOT, "tests", "integration", "fake_mcp_server.py");

export interface TestUser {
  email: string;
  id: string;
  name: string;
  accessToken: string;
  refreshToken: string;
}

/** Cliente REST mínimo (fetch nativo do Node 18+). */
export class Api {
  private base: string;
  token: string | null = null;

  constructor(base = BASE_URL) {
    this.base = base;
  }

  async request(
    method: string,
    urlPath: string,
    body?: unknown,
    headers: Record<string, string> = {}
  ): Promise<{ status: number; body: any; text: string }> {
    const res = await fetch(this.base + urlPath, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let parsed: any = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }
    return { status: res.status, body: parsed, text };
  }

  get(p: string) {
    return this.request("GET", p);
  }
  post(p: string, body?: unknown) {
    return this.request("POST", p, body);
  }
  put(p: string, body?: unknown) {
    return this.request("PUT", p, body);
  }
  delete(p: string) {
    return this.request("DELETE", p);
  }

  async login(email: string, password: string = PASSWORD): Promise<void> {
    // Rate limit do login: 5/min por IP (contrato §8). Espera o retryAfter.
    for (let attempt = 0; attempt < 5; attempt++) {
      const r = await this.post("/api/auth/login", { email, password });
      if (r.status === 429) {
        const wait = (r.body?.details?.retryAfter as number) ?? 12;
        await sleep(Math.min(wait + 2, 65) * 1000);
        continue;
      }
      if (r.status !== 200) {
        throw new Error(`login falhou: ${r.status} ${r.text.slice(0, 300)}`);
      }
      this.token = r.body.accessToken;
      return;
    }
    throw new Error("login: esgotou tentativas por 429");
  }

  async register(name: string, email: string): Promise<TestUser> {
    const r = await this.post("/api/auth/register", {
      email,
      password: PASSWORD,
      name,
    });
    if (r.status !== 201) {
      throw new Error(`registro falhou: ${r.status} ${r.text.slice(0, 300)}`);
    }
    const user: TestUser = {
      email,
      id: r.body.id,
      name,
      accessToken: "",
      refreshToken: "",
    };
    await this.login(email);
    user.accessToken = this.token as string;
    user.refreshToken = "";
    return user;
  }
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function uniqueEmail(label: string): string {
  return `${EMAIL_PREFIX}${label}-${crypto.randomUUID().slice(0, 8)}@example.com`;
}

/** Roda o helper de banco (db.py) e devolve o JSON. */
export async function db(
  command: string,
  ...args: string[]
): Promise<any> {
  const { stdout } = await pexecFile(PYTHON, [DB_SCRIPT, command, ...args], {
    timeout: 60_000,
    encoding: "utf-8",
  });
  const line = stdout.trim().split("\n").pop() ?? "";
  return JSON.parse(line);
}

export interface SeededPipeline {
  id: string;
  nodes: string[];
  name: string;
  entryNodeId: string;
}

/** Cria um agente direto no banco (o POST /api/agents funciona, mas este
 *  garante o snapshot exato que a suite de integração usa). */
export async function dbCreateAgent(
  ownerId: string,
  name: string,
  overrides: Record<string, unknown> = {}
): Promise<any> {
  return db(
    "create-agent",
    ownerId,
    name,
    JSON.stringify(overrides)
  );
}

export async function dbSeedPipeline(spec: {
  ownerId: string;
  agents: { id: string; name: string; [k: string]: unknown }[];
  name?: string;
  approvalOn?: number;
  rejectToSource?: boolean;
}): Promise<SeededPipeline> {
  return db("seed-pipeline", JSON.stringify(spec));
}

export async function dbSeedApproval(spec: {
  ownerId: string;
  pipelineId: string;
  nodeId: string;
  message?: string;
}): Promise<{ id: string; runId: string; pipelineId: string; nodeId: string }> {
  return db("seed-approval", JSON.stringify(spec));
}

export async function dbDeletePipeline(id: string): Promise<void> {
  await db("delete-pipeline", id);
}

export async function dbDeleteUser(id: string): Promise<void> {
  await db("delete-user", id);
}

/** Remove os agentes do usuário pela API (Garage) antes do cascade do banco. */
export async function purgeAgentsViaApi(api: Api, token: string): Promise<void> {
  api.token = token;
  for (let round = 0; round < 20; round++) {
    const r = await api.get("/api/agents?limit=100");
    const items = r.body?.items ?? [];
    if (!items.length) return;
    for (const a of items) {
      await api.delete(`/api/agents/${a.id}`);
    }
  }
}

// ---------------------------------------------------------------------------
// MCP fake (container na rede do compose, mesmo padrão da suite de integração)
// ---------------------------------------------------------------------------

const NETWORK = "squad-agentica_default";
const ORCH_IMAGE = "squad-agentica-orchestrator";

export class McpFake {
  readonly containerName: string;
  readonly url: string;

  private constructor(name: string, url: string) {
    this.containerName = name;
    this.url = url;
  }

  static async start(): Promise<McpFake> {
    const code = fs.readFileSync(FAKE_MCP, "utf-8");
    const name = `qa-e2e-mcp-${crypto.randomUUID().slice(0, 6)}`;
    await pexecFile(
      "docker",
      [
        "run", "-d", "--rm", "--name", name, "--network", NETWORK,
        "--entrypoint", "python", ORCH_IMAGE, "-c", code,
      ],
      { timeout: 60_000 }
    );
    await sleep(2000);
    return new McpFake(name, `http://${name}:8765/mcp`);
  }

  async stop(): Promise<void> {
    try {
      await pexecFile("docker", ["rm", "-f", this.containerName], {
        timeout: 30_000,
      });
    } catch {
      // container já foi removido (ex.: compose down)
    }
  }
}

export interface WsClient {
  frames: { channel: string; data: any }[];
  close(): Promise<void>;
}

/**
 * WebSocket cliente mínimo para espionar eventos (contrato §7).
 * Usado quando a UI não revela o que o WS publicou (ex.: nodeId de status).
 */
export async function connectWs(token: string): Promise<WsClient> {
  const url = BASE_URL.replace(/^http/, "ws") + `/api/ws?token=${encodeURIComponent(token)}`;
  const ws = new WebSocket(url);
  const frames: { channel: string; data: any }[] = [];
  await new Promise<void>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("ws: timeout de handshake")), 10_000);
    ws.onopen = () => {
      clearTimeout(t);
      resolve();
    };
    ws.onerror = () => {
      clearTimeout(t);
      reject(new Error("ws: erro de handshake"));
    };
  });
  ws.onmessage = (ev) => {
    try {
      const frame = JSON.parse(String(ev.data));
      if (frame && typeof frame.channel === "string") frames.push(frame);
    } catch {
      // frame não-JSON: ignora
    }
  };
  return {
    frames,
    close: () =>
      new Promise((resolve) => {
        ws.close();
        setTimeout(resolve, 300);
      }),
  };
}

export function ofChannel(
  frames: { channel: string; data: any }[],
  channel: string,
  pipelineId?: string
): any[] {
  return frames
    .filter((f) => f.channel === channel)
    .filter((f) => (pipelineId ? f.data?.pipelineId === pipelineId : true))
    .map((f) => f.data);
}
