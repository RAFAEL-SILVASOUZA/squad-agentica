import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";

/**
 * Middleware protecting all routes except:
 * - /login, /register (auth pages)
 * - /api/auth/* (NextAuth routes)
 * - /api/session-token (token endpoint, handles its own auth)
 * - /_next/* (Next.js assets)
 * - /favicon.ico, /robots.txt (static files)
 */
export default withAuth(
  function middleware(req) {
    // If session has authError, redirect to login.
    const token = req.nextauth.token;
    if (token?.authError) {
      const url = new URL("/login", req.url);
      url.searchParams.set("error", "session_expired");
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  },
  {
    callbacks: {
      authorized: ({ token }) => !!token,
    },
    pages: {
      signIn: "/login",
    },
  }
);

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - /login, /register
     * - /api/auth (NextAuth)
     * - /api/session-token
     * - /_next (Next.js internals)
     * - static files
     */
    "/((?!login|register|api/auth|api/session-token|_next|favicon\.ico|robots\.txt).*)",
  ],
};
