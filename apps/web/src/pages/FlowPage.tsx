import { useState } from "react";

import { ArchitectureMap } from "../components/ArchitectureMap";
import { Guide, toneForScenario } from "../components/Guide";
import { MetadataCard } from "../components/MetadataCard";
import { NodeDetail } from "../components/NodeDetail";
import { StepPlayer } from "../components/StepPlayer";
import { scenarios, stepsFor } from "../model/architecture";

export function FlowPage() {
  const [scenarioId, setScenarioId] = useState(scenarios[0]?.id ?? "grounded");
  const [index, setIndex] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const scenario = scenarios.find((item) => item.id === scenarioId) ?? scenarios[0];
  const steps = scenario ? stepsFor(scenario.steps) : [];
  const safeIndex = Math.min(index, Math.max(steps.length - 1, 0));
  const step = steps[safeIndex];
  const activeIds = step ? step.nodeIds : [];
  const tone = scenario ? toneForScenario(scenario.id) : "idle";

  function chooseScenario(id: string) {
    setScenarioId(id);
    setIndex(0);
    setSelectedId(null);
  }

  return (
    <div className="page">
      <h1>One chat, step by step</h1>
      <Guide
        screen="Each scenario is one chat. Green means the call continues, red means a role or a rule stops it, and orange means a dependency is down. The metadata card stays neutral because it is a labeled sample, not a live answer."
        first="Pick a scenario, then press Next. The pulsing box is the hop you are on."
      />
      <div className="seed-row">
        {scenarios.map((item) => (
          <button key={item.id} type="button" aria-pressed={item.id === scenario?.id} onClick={() => chooseScenario(item.id)}>
            {item.title}
          </button>
        ))}
      </div>
      {scenario ? <p>{scenario.summary}</p> : null}
      <div className="workspace">
        <div>
          <ArchitectureMap
            activeIds={activeIds}
            selectedId={selectedId}
            onSelect={setSelectedId}
            tone={tone}
          />
          <StepPlayer steps={steps} index={safeIndex} onIndex={setIndex} tone={tone} />
        </div>
        <div className="side">
          <NodeDetail nodeId={selectedId ?? step?.nodeIds[0] ?? null} />
          {scenario ? <MetadataCard metadata={scenario.metadata} /> : null}
        </div>
      </div>
    </div>
  );
}
