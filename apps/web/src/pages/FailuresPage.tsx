import { useState } from "react";

import { ArchitectureMap } from "../components/ArchitectureMap";
import { Guide, toneForFailure } from "../components/Guide";
import { NodeDetail } from "../components/NodeDetail";
import { useLayer } from "../components/LayerToggle";
import { failures } from "../model/architecture";

export function FailuresPage() {
  const [layer] = useLayer();
  const [failureId, setFailureId] = useState(failures[0]?.id ?? "unauthenticated");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const failure = failures.find((item) => item.id === failureId) ?? failures[0];
  const tone = failure ? toneForFailure(failure.id) : "idle";
  return (
    <div className="page">
      <h1>Where chat stops</h1>
      <Guide
        screen="Missing credentials, the wrong tenant, and a down dependency fail closed. Kafka after ready is the exception: the HTTP status stays whatever the caller already earned, so that case glows green."
        first="Pick a status code. The map lights the services involved in that color."
      />
      <div className="seed-row">
        {failures.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={item.id === failure?.id}
            onClick={() => {
              setFailureId(item.id);
              setSelectedId(null);
            }}
          >
            {item.status} {item.title}
          </button>
        ))}
      </div>
      {failure ? (
        <p>
          <code>{failure.code}</code> — {layer === "developer" ? failure.developer : failure.plain}
        </p>
      ) : null}
      <div className="workspace">
        <ArchitectureMap
          activeIds={failure?.nodeIds ?? []}
          selectedId={selectedId}
          onSelect={setSelectedId}
          tone={tone}
        />
        <NodeDetail nodeId={selectedId ?? failure?.nodeIds[0] ?? null} />
      </div>
    </div>
  );
}
