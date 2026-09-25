import { signIn, signOut } from "next-auth/react";

/**
 * Client-side auth helpers.
 *
 * - register(): calls POST /api/auth/register on the orchestrator API,
 *   then triggers NextAuth credentials sign-in.
 * - logout(): signs out of NextAuth.
 *
 * Token retrieval for API/WS calls: use GET /api/session-token (server route).
 * Never localStorage/sessionStorage (contract §5).
 */

const ORCHESTRATOR_API_URL =
  typeof window !== "undefined"
    ? "" // In the browser, use relative URL (NGINX proxies /api/* to orchestrator).
    : process.env.ORCHESTRATOR_API_URL ?? "http://nginx:80";

export interface RegisterInput {
  email: string;
  password: string;
  name: string;
}

export interface RegisterResult {
  ok: boolean;
  error?: string;
}

/**
 * Register a new user via the orchestrator API, then sign in.
 * Returns { ok: true } on success, { ok: false, error } on failure.
 */
export async function register(input: RegisterInput): Promise<RegisterResult> {
  try {
    const res = await fetch(`${ORCHESTRATOR_API_URL}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      let message = "Registration failed";
      try {
        const data = await res.json();
        if (data.error) {
          message = data.error;
        }
      } catch {
        // ignore parse error
      }
      return { ok: false, error: message };
    }

    // Registration succeeded; now sign in with credentials.
    const signInResult = await signIn("credentials", {
      email: input.email,
      password: input.password,
      redirect: false,
    });

    if (signInResult?.error) {
      return { ok: false, error: "Sign-in failed after registration" };
    }

    return { ok: true };
  } catch {
    return { ok: false, error: "Network error during registration" };
  }
}

/**
 * Sign out the current user.
 */
export async function logout(): Promise<void> {
  await signOut({ callbackUrl: "/login" });
}
