import { useState } from "react";

import { ArchitectureMap } from "../components/ArchitectureMap";
import { Guide } from "../components/Guide";
import { NodeDetail } from "../components/NodeDetail";
import { edges } from "../model/architecture";

export function MapPage() {
  const [selectedId, setSelectedId] = useState<string | null>("gateway");
  return (
    <div className="page">
      <h1>Where a request can go</h1>
      <Guide
        screen="These boxes are the Version 8 system. Solid boxes are running. Dashed boxes are live providers that stay off in fixture mode. Ghost boxes are later versions. The gateway on port 8000 is the only public API. On this page the glow stays the theme color, because nothing has failed or succeeded yet."
        first="Click a box. The panel on the side says what that piece owns and what it must not own."
      />
      <div className="workspace">
        <ArchitectureMap activeIds={selectedId ? [selectedId] : []} selectedId={selectedId} onSelect={setSelectedId} />
        <NodeDetail nodeId={selectedId} />
      </div>
      <h2>Always-on and optional links</h2>
      <ul className="edge-list">
        {edges.map((edge) => (
          <li key={`${edge.from}-${edge.to}`}>
            {edge.from} → {edge.to}
            <span>{edge.style === "dashed" ? "dashed" : "always"}</span>
            {edge.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
