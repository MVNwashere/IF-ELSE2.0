export default function CaughtUp({ hiddenCount, empty }: { hiddenCount: number; empty: boolean }) {
  return (
    <div className={`caught-up ${empty ? "empty" : ""}`}>
      <div className="okmark">✓</div>
      <b>You're all caught up</b>
      {empty
        ? <span>Nothing needs your attention today.</span>
        : hiddenCount > 0
          ? <span>{hiddenCount} {hiddenCount === 1 ? "item" : "items"} hidden: snoozed, dismissed, or not worth your time right now.</span>
          : <span>No infinite scroll here. Enjoy your day.</span>}
      {empty && hiddenCount > 0 && <span className="sub">{hiddenCount} {hiddenCount === 1 ? "item" : "items"} hidden</span>}
    </div>
  );
}
