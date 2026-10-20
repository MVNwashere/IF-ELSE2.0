// Balance curve on the blue tile. Touch or hover to read the balance on any day.
import { useState, type PointerEvent } from "react";
import { shortDate } from "../format";
import { useEur } from "../privacy";
import type { Point } from "./history";

const W = 330;
const H = 64;
const PAD = 4;

export default function BalanceChart({ points }: { points: Point[] }) {
  const eur = useEur();
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return null;

  const last = points.length - 1;
  const values = points.map((p) => p.balance_eur);
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const xy = points.map((p, i) => ({
    x: PAD + (i / last) * (W - PAD * 2),
    y: H - PAD - ((p.balance_eur - min) / span) * (H - PAD * 2 - 8),
  }));
  const line = xy.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area = `M${xy[0].x.toFixed(1)},${H} L${line} L${xy[last].x.toFixed(1)},${H} Z`;

  const at = hover ?? last;
  const shown = points[at];

  const scrub = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    if (r.width === 0) return;
    setHover(Math.min(last, Math.max(0, Math.round(((e.clientX - r.left) / r.width) * last))));
  };

  return (
    <div className="zb-chart">
      <div className="zb-chart-head">
        <span>{hover === null ? `Balance · last ${last} days` : shortDate(shown.date)}</span>
        {hover !== null && <b>{eur(shown.balance_eur)}</b>}
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Balance over the last ${last} days, now ${eur(points[last].balance_eur)}`}
        onPointerDown={scrub}
        onPointerMove={scrub}
        onPointerLeave={() => setHover(null)}
        onPointerCancel={() => setHover(null)}
      >
        <path d={area} fill="rgba(255,255,255,.18)" />
        <polyline points={line} fill="none" stroke="#fff" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {hover !== null && <line x1={xy[at].x} x2={xy[at].x} y1={0} y2={H} stroke="rgba(255,255,255,.55)" strokeWidth="1" />}
        <circle cx={xy[at].x} cy={xy[at].y} r="3.5" fill="#fff" />
      </svg>
    </div>
  );
}
