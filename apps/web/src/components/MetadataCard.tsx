import type { SampleMetadata } from "../model/architecture";

export function MetadataCard({ metadata }: { metadata: SampleMetadata }) {
  return (
    <section className="meta-card">
      <h3>Sample metadata</h3>
      <p className="note">Labeled sample only. No chunk text, prompt, or answer.</p>
      <dl>
        <dt>Status</dt>
        <dd>{metadata.status}</dd>
        <dt>Code</dt>
        <dd>{metadata.code ?? "—"}</dd>
        <dt>Groundedness</dt>
        <dd>{metadata.groundedness === null ? "null" : metadata.groundedness}</dd>
        <dt>Citation count</dt>
        <dd>{metadata.citationCount === null ? "null" : metadata.citationCount}</dd>
        <dt>Rule ids</dt>
        <dd>{metadata.ruleIds.length ? metadata.ruleIds.join(", ") : "none"}</dd>
        <dt>Kafka topics</dt>
        <dd>{metadata.kafkaTopics.join(", ")}</dd>
      </dl>
    </section>
  );
}
