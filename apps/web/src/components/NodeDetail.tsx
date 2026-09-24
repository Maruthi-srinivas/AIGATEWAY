import { useLayer } from "./LayerToggle";
import { edges, nodeById } from "../model/architecture";

export function NodeDetail({ nodeId }: { nodeId: string | null }) {
  const [layer] = useLayer();
  const node = nodeId ? nodeById(nodeId) : undefined;
  if (!node) {
    return <aside className="detail empty">Select a box to see what it owns and what it must not own.</aside>;
  }
  const related = edges.filter((edge) => edge.from === node.id || edge.to === node.id);
  return (
    <aside className="detail">
      <h2>{node.title}</h2>
      <div className="badges">
        {node.ghost ? <span>Not in this slice</span> : null}
        {node.stub ? <span>Health stub</span> : null}
        {node.dashed ? <span>Dashed until live</span> : null}
        {node.onRequestPath ? <span>On the chat path</span> : <span>Off the chat path</span>}
      </div>
      <p>{layer === "developer" ? node.developer : node.plain}</p>
      <h3>Owns</h3>
      <p>{node.owns}</p>
      <h3>Does not own</h3>
      <p>{node.doesNotOwn}</p>
      {layer === "developer" && (node.container || node.code) ? (
        <dl className="dev-meta">
          {node.container ? (
            <>
              <dt>Container</dt>
              <dd>{node.container}</dd>
            </>
          ) : null}
          {node.code ? (
            <>
              <dt>Code</dt>
              <dd>{node.code}</dd>
            </>
          ) : null}
        </dl>
      ) : null}
      {related.length > 0 ? (
        <>
          <h3>Links</h3>
          <ul className="edge-list">
            {related.map((edge) => (
              <li key={`${edge.from}-${edge.to}`}>
                {edge.from} → {edge.to}
                <span>{edge.style === "dashed" ? "dashed" : "always"}</span>
                {edge.label}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </aside>
  );
}
