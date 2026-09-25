import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

/**
 * Internal URL to the orchestrator API (from inside the portal container).
 * Defined in docker-compose.yml as ORCHESTRATOR_API_URL (default http://nginx:80).
 */
const ORCHESTRATOR_API_URL =
  process.env.ORCHESTRATOR_API_URL ?? "http://nginx:80";

/** Access token lifetime in seconds (15 min per contract §5). */
const ACCESS_TOKEN_LIFETIME = 15 * 60;

/**
 * Decode the `exp` claim from a JWT without verifying the signature.
 * We only need to know if the token is expired to trigger a refresh.
 */
function getTokenExp(token: string): number {
  try {
    const payload = JSON.parse(
      Buffer.from(token.split(".")[1], "base64").toString("utf-8")
    );
    return payload.exp ?? 0;
  } catch {
    return 0;
  }
}

export const authOptions: NextAuthOptions = {
  secret: process.env.NEXTAUTH_SECRET,
  session: {
    strategy: "jwt",
  },
  pages: {
    signIn: "/login",
  },
  providers: [
    CredentialsProvider({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          return null;
        }

        try {
          const res = await fetch(
            `${ORCHESTRATOR_API_URL}/api/auth/login`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                email: credentials.email,
                password: credentials.password,
              }),
            }
          );

          if (!res.ok) {
            return null;
          }

          const data = await res.json();
          // Backend returns camelCase: { accessToken, refreshToken, tokenType, expiresIn }
          return {
            id: "", // will be set from /me or JWT claims
            email: credentials.email,
            name: "",
            accessToken: data.accessToken,
            refreshToken: data.refreshToken,
          };
        } catch {
          return null;
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      // On sign-in: store API tokens in the JWT.
      if (user) {
        token.id = user.id;
        token.email = user.email;
        token.name = user.name;
        token.accessToken = (user as unknown as { accessToken: string }).accessToken;
        token.refreshToken = (user as unknown as { refreshToken: string }).refreshToken;
        return token;
      }

      // On subsequent requests: check if access token is expired and refresh.
      const exp = getTokenExp(token.accessToken);
      const now = Math.floor(Date.now() / 1000);

      if (exp - now < 60) {
        // Token is expired or about to expire (60s buffer).
        try {
          const res = await fetch(
            `${ORCHESTRATOR_API_URL}/api/auth/refresh`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ refreshToken: token.refreshToken }),
            }
          );

          if (!res.ok) {
            // Refresh failed: mark session with error, force re-login.
            token.authError = "refresh_failed";
            return token;
          }

          const data = await res.json();
          token.accessToken = data.accessToken;
          // Backend may return a new refreshToken (rotation).
          if (data.refreshToken) {
            token.refreshToken = data.refreshToken;
          }
        } catch {
          token.authError = "refresh_failed";
        }
      }

      return token;
    },

    async session({ session, token }) {
      session.user.id = token.id;
      session.user.email = token.email;
      session.user.name = token.name;
      session.accessToken = token.accessToken;
      session.refreshToken = token.refreshToken;
      session.authError = token.authError;
      return session;
    },
  },
};
