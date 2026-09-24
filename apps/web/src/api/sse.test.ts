import { describe, expect, it } from "vitest";

import { parseSseChunk } from "./sse";

describe("parseSseChunk", () => {
  it("reads meta, token, and done across chunks", () => {
    const first = parseSseChunk("", 'event: meta\ndata: {"conversation_id":"c1"}\n\nevent: token\ndata: {"text":"Hi"');
    expect(first.events).toEqual([{ event: "meta", data: '{"conversation_id":"c1"}' }]);
    const second = parseSseChunk(first.rest, '}\n\nevent: done\ndata: {"answer":"Hi"}\n\n');
    expect(second.events.map((item) => item.event)).toEqual(["token", "done"]);
    expect(second.rest).toBe("");
  });

  it("ignores heartbeat comments", () => {
    const parsed = parseSseChunk("", ": ping\n\nevent: token\ndata: {\"text\":\"a\"}\n\n");
    expect(parsed.events).toHaveLength(1);
    expect(parsed.events[0]?.event).toBe("token");
  });
});
