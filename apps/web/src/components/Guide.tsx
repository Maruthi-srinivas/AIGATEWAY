export type Tone = "idle" | "ok" | "block" | "down";

export function toneForScenario(id: string): Tone {
  if (id === "viewer" || id === "input_block") {
    return "block";
  }
  if (id.endsWith("_down")) {
    return "down";
  }
  return "ok";
}

export function toneForFailure(id: string): Tone {
  if (id === "kafka_later") {
    return "ok";
  }
  if (id === "unauthenticated" || id === "forbidden" || id === "rate_limited" || id === "input_blocked") {
    return "block";
  }
  return "down";
}

export function toneForHttp(status: number, code: string): Tone {
  if (status === 503 || code.endsWith("_unavailable") || code === "unready") {
    return "down";
  }
  if (status === 401 || status === 403 || status === 400 || status === 429) {
    return "block";
  }
  return "ok";
}

export function Guide({ screen, first }: { screen: string; first: string }) {
  return (
    <aside className="guide">
      <p>
        <strong>This screen. </strong>
        {screen}
      </p>
      <p>
        <strong>Click first. </strong>
        {first}
      </p>
      <ul className="legend" aria-label="What the glow colors mean">
        <li className="tone-ok">Green: the request continues</li>
        <li className="tone-block">Red: blocked, forbidden, or not signed in</li>
        <li className="tone-down">Orange: a dependency is down</li>
        <li>Neutral card: sample metadata, not a live call</li>
      </ul>
    </aside>
  );
}
