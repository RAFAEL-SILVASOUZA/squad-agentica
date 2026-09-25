import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      email: string;
      name: string;
    } & DefaultSession["user"];
    /** API access token (short-lived, 15 min). */
    accessToken: string;
    /** API refresh token (long-lived, 7 days). */
    refreshToken: string;
    /** Set to true when refresh fails; forces re-login. */
    authError?: string;
  }

  interface User {
    id: string;
    email: string;
    name: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    id: string;
    email: string;
    name: string;
    /** API access token. */
    accessToken: string;
    /** API refresh token. */
    refreshToken: string;
    /** Set to true when refresh fails; forces re-login. */
    authError?: string;
  }
}
