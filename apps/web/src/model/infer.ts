export const IDK = "I don't know based on the available documents.";

export type ChatSnapshot = {
  status: number;
  code?: string | null;
  answer?: string | null;
  groundedness?: number | null;
  citationCount?: number | null;
  ruleIds?: string[];
};

export type Inference = {
  summary: string;
};

export function inferChat(snapshot: ChatSnapshot): Inference {
  const code = snapshot.code ?? "";
  if (snapshot.status === 401 || code === "unauthenticated") {
    return { summary: "Inferred from the response: auth failed before a request event." };
  }
  if (snapshot.status === 403 || code === "forbidden") {
    return {
      summary: "Inferred from the response: the role or tenant check stopped the call. This is not a guardrail security event by itself.",
    };
  }
  if (snapshot.status === 429 || code === "rate_limited") {
    return { summary: "Inferred from the response: the token bucket refused the call." };
  }
  if (code === "rate_limiter_unavailable") {
    return { summary: "Inferred from the response: Redis did not answer, so the limiter failed closed." };
  }
  if (code === "guardrails_unavailable") {
    return { summary: "Inferred from the response: guardrails missed the 2 second budget." };
  }
  if (code === "rag_unavailable") {
    return { summary: "Inferred from the response: retrieval missed the 2 second budget. The model was not used as a fallback." };
  }
  if (code === "llm_unavailable") {
    return { summary: "Inferred from the response: the live model did not answer. Fixture mode does not take this branch." };
  }
  if (snapshot.status === 400 && code === "input_blocked") {
    return { summary: "Inferred from the response: an input rule blocked the message. No conversation was created." };
  }
  if (snapshot.status !== 200) {
    return { summary: `Inferred from the response: HTTP ${snapshot.status}${code ? ` ${code}` : ""}.` };
  }
  const citations = snapshot.citationCount ?? 0;
  const rules = snapshot.ruleIds ?? [];
  if (snapshot.answer === IDK && snapshot.groundedness === 0) {
    return {
      summary: "Inferred from the response: every checked sentence was dropped, so the fixed I-don't-know sentence was returned.",
    };
  }
  if (snapshot.answer === IDK && (snapshot.groundedness === null || snapshot.groundedness === undefined) && citations === 0) {
    return { summary: "Inferred from the response: no passage cleared the score floor, so the model was not called." };
  }
  if (citations > 0 && snapshot.groundedness === 1) {
    const extra = rules.length ? ` Rule ids: ${rules.join(", ")}.` : "";
    return { summary: `Inferred from the response: grounded answer with ${citations} supporting citation id${citations === 1 ? "" : "s"}.${extra}` };
  }
  if (citations > 0 && typeof snapshot.groundedness === "number") {
    return {
      summary: `Inferred from the response: some sentences were kept (groundedness ${snapshot.groundedness}) and ${citations} citation ids support them.`,
    };
  }
  if ((snapshot.groundedness === null || snapshot.groundedness === undefined) && citations === 0) {
    return { summary: "Inferred from the response: no citation check ran. That matches chitchat, which skips retrieval." };
  }
  return { summary: "Inferred from the response: the call finished. Internal hops are not observed from this payload." };
}
