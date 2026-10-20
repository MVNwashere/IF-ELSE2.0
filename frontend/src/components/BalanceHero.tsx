import { maskSeries, useEur, useMasked } from "../privacy";
import { arr, num, type SectionProps } from "./types";

function Sparkline({ values, flat }: { values: number[]; flat: boolean }) {
  if (values.length < 2) return null;
  const w = 300, h = 48, pad = 2;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2);
    const y = flat ? h / 2 : h - pad - ((v - min) / span) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const area = `M${pts[0]} L${pts.join(" L")} L${w - pad},${h} L${pad},${h} Z`;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={area} fill="rgba(255,255,255,.18)" />
      <polyline points={pts.join(" ")} fill="none" stroke="#fff" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export default function BalanceHero({ props }: SectionProps) {
  const eur = useEur();
  const masked = useMasked();
  const balance = num(props.balance_eur);
  const income = num(props.monthly_income_eur);
  const spend = num(props.monthly_spend_eur);
  const trend = num(props.trend_30d_eur);
  const spark = arr<number>(props.sparkline);
  return (
    <div className="hero">
      <h3>Current account</h3>
      <div className="amount">{eur(balance)}</div>
      <div className="line">
        {masked ? "•" : trend >= 0 ? "▲" : "▼"} {eur(Math.abs(trend))} over the last 30 days
      </div>
      {/* Hidden amounts: a flat line, so the trend can't be read from the shape. */}
      <Sparkline values={maskSeries(spark, masked)} flat={masked} />
      <div className="kv">
        <div>Income / month<b>{eur(income)}</b></div>
        <div>Spending / month<b>{eur(spend)}</b></div>
      </div>
    </div>
  );
}
