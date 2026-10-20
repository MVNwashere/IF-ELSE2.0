import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import type { Account } from "../accounts/accounts";
import { useEur } from "../privacy";

/** Counts up to `value` when it first shows or changes (a new customer, a time-travel date). */
function useCountUp(value: number): number {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);
  const from = useRef(reduce ? value : 0);
  useEffect(() => {
    if (reduce) { setShown(value); return; }
    const controls = animate(from.current, value, { duration: 0.9, ease: [0.2, 0.8, 0.2, 1], onUpdate: setShown });
    from.current = value;
    return () => controls.stop();
  }, [value, reduce]);
  return shown;
}

/** The KBC symbol: a light-blue ball resting in a rising band, with the primary account inside the ball. */
export default function AccountLogo({ account }: { account: Account }) {
  const eur = useEur();
  const balance = useCountUp(account.balance_eur);
  const settled = Math.abs(balance - account.balance_eur) < 0.005;
  return (
    <div className="account-logo">
      <svg className="account-logo-wave" viewBox="0 0 360 100" preserveAspectRatio="none" aria-hidden="true">
        <path d="M0 52 C70 40 130 24 200 13 C260 5 320 3 360 2 V100 H0Z" />
      </svg>
      <div className="hero account-orb">
        <div className="account-orb-content">
          <span className="account-name">{account.name}</span>
          <span className="account-number">•••• {account.last4}</span>
          <span className="account-divider" aria-hidden="true" />
          <strong className="account-balance" aria-label={eur(account.balance_eur)}>
            {eur(settled ? account.balance_eur : Math.round(balance))}
          </strong>
          <span className="account-available">Available balance</span>
        </div>
      </div>
    </div>
  );
}
