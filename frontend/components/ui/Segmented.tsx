import { useId } from "react";

interface Option<T extends string | number> {
  value: T;
  label: string;
  title?: string;
  disabled?: boolean;
}

interface SegmentedProps<T extends string | number> {
  label: string;
  value: T;
  options: readonly Option<T>[];
  onChange: (value: T) => void;
  hideLabel?: boolean;
  size?: "normal" | "small";
}

/** A group of radio buttons that looks like a segmented control (keyboard: arrow keys, like native radios). */
export function Segmented<T extends string | number>({ label, value, options, onChange, hideLabel, size = "normal" }: SegmentedProps<T>) {
  const name = useId();
  return (
    <fieldset className={`segmented segmented--${size}`}>
      <legend className={hideLabel ? "visually-hidden" : "segmented__legend"}>{label}</legend>
      <div className="segmented__options">
        {options.map((o) => (
          <label key={String(o.value)} className="segmented__option" title={o.title} data-disabled={o.disabled || undefined}>
            <input
              type="radio"
              name={name}
              value={String(o.value)}
              checked={o.value === value}
              disabled={o.disabled}
              onChange={() => onChange(o.value)}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
