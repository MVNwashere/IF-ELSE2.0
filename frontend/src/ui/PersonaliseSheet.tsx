// "Personalise": the customer's own overrides on the adaptive theme. null = Auto (the engine decides).
import type { Accent, HomeResponse, StylePrefs } from "../api";
import { ACCENTS } from "../theme";
import Sheet from "./Sheet";

interface Props {
  home: HomeResponse;
  onStyle: (style: StylePrefs) => void;
  onClose: () => void;
}

export const AUTO_STYLE: StylePrefs = {
  density: null, contrast: null, tone: null, appearance: null, accent: null, reduce_motion: false, privacy: false,
};

type ChoiceKey = "density" | "contrast" | "appearance" | "tone";

const CHOICES: { key: ChoiceKey; label: string; options: { value: string; label: string }[] }[] = [
  { key: "density", label: "Text size", options: [{ value: "compact", label: "Compact" }, { value: "comfortable", label: "Comfortable" }, { value: "large", label: "Large" }] },
  { key: "contrast", label: "Contrast", options: [{ value: "normal", label: "Normal" }, { value: "high", label: "High" }] },
  { key: "appearance", label: "Appearance", options: [{ value: "light", label: "Light" }, { value: "dark", label: "Dark" }] },
  {
    key: "tone", label: "Tone", options: [
      { value: "casual", label: "Casual" }, { value: "neutral", label: "Neutral" }, { value: "warm", label: "Warm" },
      { value: "business", label: "Business" }, { value: "formal", label: "Formal" },
    ],
  },
];

const ACCENT_LABEL: Record<Accent, string> = { blue: "Blue", teal: "Teal", purple: "Purple", amber: "Amber", navy: "Navy" };

function Toggle({ label, hint, on, onChange }: { label: string; hint: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="ps-toggle">
      <div><b>{label}</b><span>{hint}</span></div>
      <button type="button" role="switch" aria-checked={on} aria-label={label} className={`sw ${on ? "on" : ""}`} onClick={() => onChange(!on)} />
    </div>
  );
}

export default function PersonaliseSheet({ home, onStyle, onClose }: Props) {
  const style = home.style;
  const theme = home.layout.theme;
  const why = home.layout.explanations["theme"];
  const set = (patch: Partial<StylePrefs>) => onStyle({ ...style, ...patch });
  const anyOverride = CHOICES.some((c) => style[c.key] !== null) || style.accent !== null || style.reduce_motion || style.privacy;

  return (
    <Sheet title="Personalise" onClose={onClose}>
      <p className="ps-intro">
        Your home adapts to you automatically. Anything you set here wins over the automatic choice.
      </p>
      {why && <div className="ps-why"><b>Auto chooses because:</b> {why}</div>}

      {CHOICES.map((c) => {
        const current = style[c.key];
        const autoValue = String(theme[c.key]);
        return (
          <div className="ps-group" key={c.key}>
            <div className="ps-label">{c.label}</div>
            <div className="seg" role="radiogroup" aria-label={c.label}>
              <button type="button" role="radio" aria-checked={current === null} className={current === null ? "on" : ""} onClick={() => set({ [c.key]: null })}>Auto</button>
              {c.options.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  role="radio"
                  aria-checked={current === o.value}
                  className={current === o.value ? "on" : ""}
                  onClick={() => set({ [c.key]: o.value } as Partial<StylePrefs>)}
                >
                  {o.label}
                </button>
              ))}
            </div>
            {current === null && <div className="ps-auto">Auto picks: {autoValue}</div>}
          </div>
        );
      })}

      <div className="ps-group">
        <div className="ps-label">Accent colour</div>
        <div className="swatches" role="radiogroup" aria-label="Accent colour">
          <button type="button" role="radio" aria-checked={style.accent === null} className={`swatch auto ${style.accent === null ? "on" : ""}`} onClick={() => set({ accent: null })}>Auto</button>
          {(Object.keys(ACCENTS) as Accent[]).map((a) => (
            <button
              key={a}
              type="button"
              role="radio"
              aria-checked={style.accent === a}
              aria-label={ACCENT_LABEL[a]}
              title={ACCENT_LABEL[a]}
              className={`swatch ${style.accent === a ? "on" : ""}`}
              style={{ background: `linear-gradient(135deg, ${ACCENTS[a][0]}, ${ACCENTS[a][1]})` }}
              onClick={() => set({ accent: a })}
            />
          ))}
        </div>
      </div>

      <div className="ps-group">
        <Toggle label="Reduce motion" hint="No sliding or morphing animations." on={style.reduce_motion} onChange={(v) => set({ reduce_motion: v })} />
        <Toggle label="Hide amounts" hint="Amounts show as € •••• until you tap." on={style.privacy} onChange={(v) => set({ privacy: v })} />
      </div>

      <button type="button" className="btn-ghost block" disabled={!anyOverride} onClick={() => onStyle(AUTO_STYLE)}>Reset all to Auto</button>
    </Sheet>
  );
}
