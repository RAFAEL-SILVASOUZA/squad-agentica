import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { authOptions } from "@/auth-options";

/**
 * GET /api/session-token
 *
 * Returns the API access token for the current session.
 * The client calls this to obtain the JWT for REST and WebSocket calls.
 * Never uses localStorage/sessionStorage (contract §5).
 */
export async function GET() {
  const session = await getServerSession(authOptions);

  if (!session) {
    return NextResponse.json(
      { error: "unauthorized", code: "not_authenticated" },
      { status: 401 }
    );
  }

  if (session.authError) {
    return NextResponse.json(
      { error: "unauthorized", code: "session_expired" },
      { status: 401 }
    );
  }

  return NextResponse.json({
    accessToken: session.accessToken,
    tokenType: "Bearer",
  });
}
