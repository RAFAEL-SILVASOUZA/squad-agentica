import { describe, it, expect } from "vitest";
import { relativeTime } from "./relative-time";

const now = new Date("2026-09-29T12:00:00Z");

describe("relativeTime", () => {
  it.each([
    ["2026-09-29T11:59:40Z", "agora"],
    ["2026-09-29T11:48:00Z", "há 12 min"],
    ["2026-09-29T09:00:00Z", "há 3 h"],
    ["2026-09-27T12:00:00Z", "há 2 dias"],
  ])("%s → %s", (iso, out) => expect(relativeTime(iso, now)).toBe(out));
});
