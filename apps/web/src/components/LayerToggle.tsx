import { useSyncExternalStore } from "react";

export type Layer = "plain" | "developer";

const KEY = "aigw.layer";
const listeners = new Set<() => void>();

function read(): Layer {
  if (typeof sessionStorage === "undefined") {
    return "plain";
  }
  return sessionStorage.getItem(KEY) === "developer" ? "developer" : "plain";
}

let current: Layer = read();

function commit(next: Layer) {
  current = next;
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.setItem(KEY, next);
  }
  listeners.forEach((listener) => listener());
}

export function useLayer(): [Layer, (layer: Layer) => void] {
  const layer = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
    () => "plain" as Layer,
  );
  return [layer, commit];
}

export function LayerToggle() {
  const [layer, setLayer] = useLayer();
  return (
    <div className="layer-toggle" role="group" aria-label="Explanation depth">
      <span className="hint">Depth of the side panel</span>
      <button type="button" aria-pressed={layer === "plain"} onClick={() => setLayer("plain")}>
        Plain language
      </button>
      <button type="button" aria-pressed={layer === "developer"} onClick={() => setLayer("developer")}>
        Developer
      </button>
    </div>
  );
}
