// component name → React component. Unknown names are skipped (never crash).
import type { Component } from "../api";
import type { SectionComponent } from "./types";
import AdvisorContact from "./AdvisorContact";
import BalanceHero from "./BalanceHero";
import FamilyBudgetHero from "./FamilyBudgetHero";
import ForYouFeed from "./ForYouFeed";
import InvoiceTracker from "./InvoiceTracker";
import KateTile from "./KateTile";
import PensionHero from "./PensionHero";
import QuickActions from "./QuickActions";
import RunwayHero from "./RunwayHero";
import SavingsGoal from "./SavingsGoal";
import ScamShield from "./ScamShield";
import SpendingByCategory from "./SpendingByCategory";
import SplitBills from "./SplitBills";
import SubscriptionsTile from "./SubscriptionsTile";
import TaxReserveHero from "./TaxReserveHero";
import UpcomingBills from "./UpcomingBills";

export const registry: Record<Component, SectionComponent> = {
  BalanceHero,
  RunwayHero,
  FamilyBudgetHero,
  TaxReserveHero,
  PensionHero,
  ForYouFeed,
  QuickActions,
  UpcomingBills,
  SplitBills,
  InvoiceTracker,
  SavingsGoal,
  ScamShield,
  AdvisorContact,
  SpendingByCategory,
  KateTile,
  SubscriptionsTile,
};

const warned = new Set<string>();

export function resolve(name: string): SectionComponent | null {
  const c = (registry as Record<string, SectionComponent>)[name];
  if (!c) {
    if (!warned.has(name)) {
      warned.add(name);
      console.warn(`[registry] unknown component "${name}" ignored`);
    }
    return null;
  }
  return c;
}
