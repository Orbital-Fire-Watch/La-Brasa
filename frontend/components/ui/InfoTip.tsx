import { useId, useState } from "react";

/** Small "i" button with an explanation; opens on hover, focus and click (touch). */
export function InfoTip({ text, label = "Erklärung" }: { text: string; label?: string }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span className="infotip" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        className="infotip__button"
        aria-label={label}
        aria-describedby={id}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        i
      </button>
      <span id={id} role="tooltip" className="infotip__text" hidden={!open}>
        {text}
      </span>
    </span>
  );
}
