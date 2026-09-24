import { describe, expect, it } from "vitest";

import { chatSteps, failures, nodes, scenarios, stepsFor } from "./architecture";
import { inferChat } from "./infer";

const nodeIds = new Set(nodes.map((node) => node.id));
const stepIds = new Set(chatSteps.map((step) => step.id));

describe("architecture model", () => {
  it("points every chat step at a real node", () => {
    for (const step of chatSteps) {
      expect(step.nodeIds.length).toBeGreaterThan(0);
      for (const id of step.nodeIds) {
        expect(nodeIds.has(id)).toBe(true);
      }
    }
  });

  it("keeps ghost nodes off the request path", () => {
    const ghosts = nodes.filter((node) => node.ghost);
    expect(ghosts.length).toBeGreaterThan(0);
    for (const node of ghosts) {
      expect(node.onRequestPath).toBe(false);
      expect(node.column).toBe("later");
    }
  });

  it("uses only known steps in scenarios", () => {
    for (const scenario of scenarios) {
      expect(scenario.steps.length).toBeGreaterThan(0);
      expect(stepsFor(scenario.steps).map((step) => step.id)).toEqual(scenario.steps);
      for (const id of scenario.steps) {
        expect(stepIds.has(id)).toBe(true);
      }
    }
  });

  it("points failure cases at real nodes", () => {
    for (const failure of failures) {
      expect(failure.nodeIds.length).toBeGreaterThan(0);
      for (const id of failure.nodeIds) {
        expect(nodeIds.has(id)).toBe(true);
      }
    }
  });
});

describe("inferChat", () => {
  it("reads fail-closed codes", () => {
    expect(inferChat({ status: 503, code: "rag_unavailable" }).summary).toContain("retrieval");
    expect(inferChat({ status: 400, code: "input_blocked" }).summary).toContain("blocked");
    expect(inferChat({ status: 403, code: "forbidden" }).summary).toContain("not a guardrail");
  });

  it("separates no-chunk, citation drop, chitchat, and grounded", () => {
    expect(
      inferChat({
        status: 200,
        answer: "I don't know based on the available documents.",
        groundedness: null,
        citationCount: 0,
      }).summary,
    ).toContain("score floor");
    expect(
      inferChat({
        status: 200,
        answer: "I don't know based on the available documents.",
        groundedness: 0,
        citationCount: 0,
      }).summary,
    ).toContain("dropped");
    expect(inferChat({ status: 200, answer: "Stub: hello", groundedness: null, citationCount: 0 }).summary).toContain(
      "chitchat",
    );
    expect(inferChat({ status: 200, groundedness: 1, citationCount: 2, ruleIds: [] }).summary).toContain("grounded");
  });
});
