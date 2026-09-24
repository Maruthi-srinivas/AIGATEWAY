import type { ChatStep } from "../model/architecture";
import type { Tone } from "./Guide";
import { useLayer } from "./LayerToggle";

type Props = {
  steps: ChatStep[];
  index: number;
  onIndex: (index: number) => void;
  tone?: Tone;
};

export function StepPlayer({ steps, index, onIndex, tone = "idle" }: Props) {
  const [layer] = useLayer();
  const step = steps[index];
  if (!step) {
    return null;
  }
  return (
    <div className="stepper">
      <div className="stepper-bar">
        <button type="button" onClick={() => onIndex(index - 1)} disabled={index === 0}>
          Back
        </button>
        <span>
          {index + 1} / {steps.length}
        </span>
        <button type="button" onClick={() => onIndex(index + 1)} disabled={index >= steps.length - 1}>
          Next
        </button>
      </div>
      <ol className="step-list">
        {steps.map((item, itemIndex) => (
          <li key={item.id}>
            <button
              type="button"
              className={itemIndex === index ? `current${tone === "idle" ? "" : ` tone-${tone}`}` : undefined}
              aria-current={itemIndex === index ? "step" : undefined}
              onClick={() => onIndex(itemIndex)}
            >
              {item.title}
            </button>
          </li>
        ))}
      </ol>
      <p>{layer === "developer" ? step.developer : step.plain}</p>
    </div>
  );
}
