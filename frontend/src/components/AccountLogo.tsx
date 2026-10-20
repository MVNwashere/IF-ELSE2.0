import type { Account } from "../accounts/accounts";
import { useEur } from "../privacy";

/** The KBC symbol: a light-blue ball resting in a rising band, with the primary account inside the ball. */
export default function AccountLogo({ account }: { account: Account }) {
  const eur = useEur();
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
          <strong className="account-balance">{eur(account.balance_eur)}</strong>
          <span className="account-available">Available balance</span>
        </div>
      </div>
    </div>
  );
}
