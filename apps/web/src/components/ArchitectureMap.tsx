import { columns, nodes, type ArchNode } from "../model/architecture";
import type { Tone } from "./Guide";

type Props = {
  activeIds: string[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  tone?: Tone;
};

function classes(node: ArchNode, active: boolean, selected: boolean, tone: Tone): string {
  const names = ["node"];
  if (active && tone !== "idle") {
    names.push(`tone-${tone}`);
  }
  if (selected) {
    names.push("selected");
  }
  if (node.ghost) {
    names.push("ghost");
  }
  if (node.dashed) {
    names.push("dashed");
  }
  if (node.stub) {
    names.push("stub");
  }
  return names.join(" ");
}

export function ArchitectureMap({ activeIds, selectedId, onSelect, tone = "idle" }: Props) {
  const active = new Set(activeIds);
  return (
    <div className="map">
      {columns.map((column) => (
        <section key={column.id} className="map-column" aria-label={column.title}>
          <h3>{column.title}</h3>
          {nodes
            .filter((node) => node.column === column.id)
            .map((node) => (
              <button
                key={node.id}
                type="button"
                className={classes(node, active.has(node.id), selectedId === node.id, tone)}
                aria-pressed={selectedId === node.id}
                onClick={() => onSelect(node.id)}
              >
                <span>{node.title}</span>
                {node.ghost ? <small>Not in this slice</small> : null}
                {node.stub ? <small>Health stub</small> : null}
                {node.dashed && !node.ghost ? <small>Fixture by default</small> : null}
              </button>
            ))}
        </section>
      ))}
    </div>
  );
}
