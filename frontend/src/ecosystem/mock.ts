// In-memory ecosystem engine for ?mock=1: same shapes as the backend, partners "call back" after 2 s.
import type {
  ConsentGrant, ConsentsResponse, DataField, EcosystemOverview, EventRow, Goal, GoalCandidate, GoalsResponse,
  PlaybookSummary, ProductRef, ProviderPublic, SourcesResponse, SourceView, Step, StepDecision, WinTotals,
} from "./types";

const VET_PARTNER = ["Licensed and registered with the FSMA", "GDPR data-processing agreement signed with KBC", "Security review passed (ISO 27001)", "Customer satisfaction ≥ 4.3/5 over the last 12 months"];
const VET_KBC = ["KBC product, regulated by the NBB", "Your data stays inside KBC"];

function kbc(id: string, name: string, blurb: string): ProviderPublic {
  return { id, name, kind: "kbc", blurb, vetting: VET_KBC, integration: "KBC core banking" };
}
function partner(id: string, name: string, blurb: string, integration: string): ProviderPublic {
  return { id, name, kind: "partner", blurb, vetting: VET_PARTNER, integration };
}

const P = {
  kbcLoan: kbc("kbc_home_loan", "KBC Home Loan", "Mortgages and renovation loans, decided in the app."),
  kbcInsurance: kbc("kbc_insurance", "KBC Home Insurance", "Fire and home insurance, linked to your loan."),
  immoscoop: partner("immoscoop", "Immoscoop", "Property search platform with verified listings.", "KBC Open API · listings webhook"),
  setle: partner("setle", "Setle", "Independent property valuation within 48 h.", "KBC Open API · valuation webhook"),
  energy: partner("energyscan", "EnergyScan", "Certified energy auditors (EPC).", "KBC Open API · audit webhook"),
  reno: partner("renopartners", "RenoPartners", "Vetted renovation contractors, fixed-price quotes.", "KBC Open API · quotes webhook"),
  premie: partner("mijn_verbouwpremie", "Subsidy desk", "Files the Flemish renovation premium for you.", "KBC Open API · subsidy webhook"),
};

const prod = (id: string, name: string, ecosystem: string, p: string | null = null): ProductRef => ({ id, name, ecosystem, partner: p });
const f = (field: string, label: string, sensitive = false): DataField => ({ field, label, sensitive });

function step(order: number, step_id: string, title: string, provider: ProviderPublic, extra: Partial<Step>): Step {
  return {
    step_id, order, title, description: "", provider, why_this_provider: "", products: [], status: "proposed",
    data_shared: [], data_not_shared: ["Your income", "Your account balances", "Your transactions"], consent_days: 90,
    win: { customer: "", kbc: "", partner: "" },
    estimates: { customer_eur: 0, hours_saved: 0, kbc_revenue_eur: 0, partner_fee_eur: 0 },
    result: "", ref: "", grant_id: null, updated_at: null, already_held: false, ...extra,
  };
}

const RESULTS: Record<string, string> = {
  find_home: "3 homes match your budget in Gent-Oost. First viewing booked Thu 18:00.",
  valuation: "Valuation €312.000 (asking price €329.000): room to negotiate ~€15.000.",
  energy_scan: "EPC estimate D (312 kWh/m²). Biggest win: roof insulation, then heat pump.",
  quotes: "2 fixed-price quotes: roof insulation €8.900 (start in 3 weeks) or €9.400 (start next week).",
  subsidy: "Renovation premium filed: €2.700 expected within 8 weeks.",
};

function buyHomeSteps(): Step[] {
  return [
    step(1, "budget", "Know your budget", P.kbcLoan, {
      description: "A personal borrowing estimate based on your income and savings.",
      why_this_provider: "KBC already knows your income: no documents to upload.",
      products: [prod("home-loan", "Home loan", "Housing")],
      win: { customer: "Budget in 2 minutes instead of a bank meeting", kbc: "Mortgage relationship", partner: "" },
      estimates: { customer_eur: 0, hours_saved: 3, kbc_revenue_eur: 1800, partner_fee_eur: 0 },
      data_not_shared: [], consent_days: 0,
    }),
    step(2, "find_home", "Find homes that fit", P.immoscoop, {
      description: "Listings filtered on your real budget and wishes.",
      why_this_provider: "Largest verified listing base in Flanders; no fake listings policy.",
      products: [prod("property-search", "Property search", "Housing", "Immoscoop")],
      data_shared: [f("budget_range", "Your budget range"), f("region", "Preferred region"), f("household_size", "Household size")],
      win: { customer: "Only homes you can afford", kbc: "Earlier in the journey", partner: "Qualified lead" },
      estimates: { customer_eur: 0, hours_saved: 12, kbc_revenue_eur: 0, partner_fee_eur: 40 },
    }),
    step(3, "valuation", "Independent valuation", P.setle, {
      description: "Know what the house is really worth before you make an offer.",
      why_this_provider: "Independent of the seller, accepted by KBC for your loan.",
      products: [prod("valuation", "Property valuation", "Housing", "Setle")],
      data_shared: [f("property_address", "The address of the house"), f("asking_price", "The asking price")],
      win: { customer: "Negotiate with facts", kbc: "Loan risk known upfront", partner: "Paid valuation" },
      estimates: { customer_eur: 6000, hours_saved: 4, kbc_revenue_eur: 0, partner_fee_eur: 120 },
    }),
    step(4, "mortgage", "Your home loan", P.kbcLoan, {
      description: "Loan offer pre-filled with the valuation.",
      why_this_provider: "Your bank, with the valuation already attached.",
      products: [prod("home-loan", "Home loan", "Housing")],
      win: { customer: "Offer in 48 h", kbc: "Home loan", partner: "" },
      estimates: { customer_eur: 1200, hours_saved: 6, kbc_revenue_eur: 2400, partner_fee_eur: 0 },
      data_not_shared: [], consent_days: 0,
    }),
    step(5, "insurance", "Fire insurance", P.kbcInsurance, {
      description: "Required for the loan, linked automatically.",
      why_this_provider: "Bundled discount with your KBC home loan.",
      products: [prod("home-insurance", "Home insurance", "Housing")],
      win: { customer: "One less thing to arrange", kbc: "Insurance policy", partner: "" },
      estimates: { customer_eur: 180, hours_saved: 2, kbc_revenue_eur: 220, partner_fee_eur: 0 },
      data_not_shared: [], consent_days: 0,
    }),
  ];
}

function renoSteps(): Step[] {
  return [
    step(1, "energy_scan", "Energy scan of your home", P.energy, {
      description: "A certified auditor estimates your EPC and the best upgrades.",
      why_this_provider: "Certified EPC auditor, 4.7/5 from KBC customers.",
      products: [prod("energy-audit", "Energy audit", "Housing", "EnergyScan")],
      data_shared: [f("property_address", "The address of your home"), f("build_year", "Year your home was built")],
      win: { customer: "Know where your energy money goes", kbc: "Green loan opportunity", partner: "Paid audit" },
      estimates: { customer_eur: 0, hours_saved: 3, kbc_revenue_eur: 0, partner_fee_eur: 90 },
      status: "done", result: RESULTS.energy_scan, ref: "es-77812", grant_id: 1,
    }),
    step(2, "quotes", "Fixed-price quotes", P.reno, {
      description: "Two vetted contractors quote the roof insulation.",
      why_this_provider: "Contractors with a KBC quality guarantee and fixed prices.",
      products: [prod("renovation-services", "Renovation services", "Housing", "RenoPartners")],
      data_shared: [f("property_address", "The address of your home"), f("phone", "Your phone number", true), f("audit_summary", "The energy scan summary")],
      win: { customer: "No chasing contractors", kbc: "Renovation loan", partner: "Qualified job" },
      estimates: { customer_eur: 900, hours_saved: 10, kbc_revenue_eur: 0, partner_fee_eur: 150 },
    }),
    step(3, "subsidy", "Claim your renovation premium", P.premie, {
      description: "We file the Flemish renovation premium for you.",
      why_this_provider: "Specialist in subsidy files: no rejected applications for missing papers.",
      products: [prod("subsidy-service", "Subsidy service", "Housing", "Subsidy desk")],
      data_shared: [f("name", "Your name"), f("property_address", "The address of your home"), f("national_id", "Your national register number", true)],
      win: { customer: "Premium without paperwork", kbc: "", partner: "Fee per file" },
      estimates: { customer_eur: 2700, hours_saved: 8, kbc_revenue_eur: 0, partner_fee_eur: 60 },
    }),
    step(4, "green_loan", "Green renovation loan", P.kbcLoan, {
      description: "Low-rate loan for the insulation, paid out to the contractor.",
      why_this_provider: "Lower rate for energy renovations.",
      products: [prod("renovation-loan", "Renovation loan", "Housing")],
      win: { customer: "Lower rate than a personal loan", kbc: "Green loan", partner: "Paid on time" },
      estimates: { customer_eur: 650, hours_saved: 2, kbc_revenue_eur: 480, partner_fee_eur: 0 },
      data_not_shared: [], consent_days: 0,
    }),
    step(5, "insurance", "Home insurance updated", P.kbcInsurance, {
      description: "Your policy covers the renovated value.",
      why_this_provider: "You already have this at KBC.",
      products: [prod("home-insurance", "Home insurance", "Housing")],
      status: "done", already_held: true, data_not_shared: [], consent_days: 0,
    }),
  ];
}

function totals(steps: Step[], onlyDone: boolean): WinTotals {
  const t: WinTotals = { customer_eur: 0, hours_saved: 0, kbc_revenue_eur: 0, partner_fees_eur: 0, kbc_products: [], partner_leads: 0 };
  for (const s of steps) {
    if (onlyDone && s.status !== "done") continue;
    if (s.already_held) continue;
    t.customer_eur += s.estimates.customer_eur;
    t.hours_saved += s.estimates.hours_saved;
    t.kbc_revenue_eur += s.estimates.kbc_revenue_eur;
    t.partner_fees_eur += s.estimates.partner_fee_eur;
    if (s.provider.kind === "kbc" && s.estimates.kbc_revenue_eur > 0) t.kbc_products.push(s.products[0]?.name ?? s.title);
    if (s.provider.kind === "partner") t.partner_leads += 1;
  }
  return t;
}

function refresh(g: Goal): Goal {
  g.progress = { done: g.steps.filter((s) => s.status === "done").length, total: g.steps.length };
  g.outcome = totals(g.steps, true);
  g.potential = totals(g.steps, false);
  if (g.progress.done === g.progress.total) g.status = "completed";
  return g;
}

const PLAYBOOKS: PlaybookSummary[] = [
  { playbook_id: "buy_home", title: "Buy a home", icon: "🏡", tagline: "From search to keys, one journey", ecosystems: ["Housing"], steps: 5 },
  { playbook_id: "energy_renovation", title: "Make my home energy-efficient", icon: "🌱", tagline: "Lower bills, premium included", ecosystems: ["Housing", "Energy"], steps: 5 },
  { playbook_id: "grow_pension", title: "Build up my pension", icon: "🌅", tagline: "Tax-smart saving for later", ecosystems: ["Wealth"], steps: 4 },
];

const BUY_HOME_CANDIDATE: GoalCandidate = {
  playbook_id: "buy_home", title: "Buy a home", icon: "🏡", tagline: "From search to keys, one journey", ecosystems: ["Housing"],
  confidence: 0.82,
  evidence: [
    "You've saved €410/month for 14 months in a row",
    "Rent of €1.050/month: a loan could cost about the same",
    "Your household grew in 2024",
  ],
  why_now: "Your savings now cover the deposit and costs for a home up to about €300.000.",
  steps_preview: buyHomeSteps().map((s) => s.title),
  partners_preview: ["Immoscoop", "Setle", "KBC Home Loan", "KBC Home Insurance"],
  potential: totals(buyHomeSteps(), false),
};

let nextGoalId = 2;
let nextGrantId = 2;
let hiddenCandidates = new Set<string>();
let goals: Goal[] = [];
let grants: ConsentGrant[] = [];
const events: EventRow[] = [];

function initial(): void {
  hiddenCandidates = new Set();
  goals = [refresh({
    goal_id: 1, playbook_id: "energy_renovation", title: "Make my home energy-efficient", icon: "🌱",
    tagline: "Lower bills, premium included", ecosystems: ["Housing", "Energy"], status: "active",
    created_on: "2026-09-12", target_date: "2027-03-31", origin: "detected",
    evidence: ["Energy bills up 34% year on year", "Home built in 1978"],
    progress: { done: 0, total: 0 }, steps: renoSteps(),
    outcome: totals([], true), potential: totals([], false), next_goal: null,
  })];
  grants = [{
    grant_id: 1, partner_id: "energyscan", partner_name: "EnergyScan", goal_id: 1, goal_title: "Make my home energy-efficient",
    step_id: "energy_scan", step_title: "Energy scan of your home",
    fields: [f("property_address", "The address of your home"), f("build_year", "Year your home was built")],
    purpose: "Estimate your EPC and the best upgrades", granted_on: "2026-09-12", expires_on: "2026-12-11", status: "active", revoked_on: null,
  }];
  events.length = 0;
  pushEvent("energyscan", "outbound", "KBC → EnergyScan: start energy scan (2 fields)");
  pushEvent("energyscan", "done", "EnergyScan: EPC estimate D, report delivered");
}

function pushEvent(partner_id: string, kind: string, summary: string): void {
  events.unshift({ at: new Date().toISOString(), partner_id, kind, summary, verified: kind !== "outbound" });
  events.splice(40);
}

initial();

const blank = (): Goal => ({
  goal_id: 0, playbook_id: "", title: "", icon: "", tagline: "", ecosystems: [], status: "active", created_on: "2026-10-20",
  target_date: null, origin: "stated", evidence: [], progress: { done: 0, total: 0 }, steps: [],
  outcome: totals([], true), potential: totals([], false), next_goal: null,
});
const delay = <T>(v: T, ms = 250) => new Promise<T>((res) => window.setTimeout(() => res(structuredClone(v)), ms));

function findGoal(id: number): Goal {
  const g = goals.find((x) => x.goal_id === id);
  if (!g) throw new Error("Goal not found");
  return g;
}

const addDays = (iso: string, d: number) => { const t = new Date(iso + "T00:00:00"); t.setDate(t.getDate() + d); return t.toISOString().slice(0, 10); };

const mockSources: SourceView[] = [
  { source_id: "mypension", name: "mypension.be", provider: "Federal Pension Service", kind: "government", reads: ["Your estimated statutory pension"], goals: ["retire_well"], sensitivity: "high", needs_consent: true, consent_days: 365, why: "An exact pension gap instead of an estimate.", status: "available", connected_on: null, expires_on: null, purpose: "", playbook_id: null, values: {}, simulated: true },
  { source_id: "kbo", name: "Company register (KBO/CBE)", provider: "Crossroads Bank for Enterprises", kind: "public", reads: ["Your company number and start date"], goals: ["go_freelance"], sensitivity: "low", needs_consent: false, consent_days: 0, why: "Public register: no permission needed.", status: "public", connected_on: null, expires_on: null, purpose: "", playbook_id: null, values: {}, simulated: true },
];

export const mockEco = {
  goals(asOf?: string): Promise<GoalsResponse> {
    const active = new Set(goals.filter((g) => g.status !== "cancelled").map((g) => g.playbook_id));
    const candidates = [BUY_HOME_CANDIDATE].filter((c) => !active.has(c.playbook_id) && !hiddenCandidates.has(c.playbook_id));
    return delay({
      as_of: asOf ?? "2026-10-20",
      candidates,
      goals: goals.filter((g) => g.status !== "cancelled"),
      holdings: [prod("home-insurance", "Home insurance", "Housing"), prod("current-account", "Current account", "Daily banking")],
      playbooks: PLAYBOOKS,
    });
  },
  startGoal(playbook_id: string): Promise<Goal> {
    const existing = goals.find((g) => g.playbook_id === playbook_id && g.status !== "cancelled");
    if (existing) return delay(existing);
    const pb = PLAYBOOKS.find((p) => p.playbook_id === playbook_id) ?? PLAYBOOKS[0];
    const g = blank();
    Object.assign(g, {
      goal_id: nextGoalId++, playbook_id, title: pb.title, icon: pb.icon, tagline: pb.tagline, ecosystems: pb.ecosystems,
      status: "active", created_on: "2026-10-20", target_date: null,
      origin: playbook_id === "buy_home" ? "detected" : "stated",
      evidence: playbook_id === "buy_home" ? BUY_HOME_CANDIDATE.evidence : ["You told us this is your goal"],
      steps: playbook_id === "buy_home" ? buyHomeSteps() : renoSteps().map((s) => ({ ...s, status: s.already_held ? "done" : "proposed", result: "", grant_id: null })),
    });
    goals.push(refresh(g));
    return delay(g);
  },
  stepDecision(goalId: number, stepId: string, decision: StepDecision): Promise<Goal> {
    const g = findGoal(goalId);
    const s = g.steps.find((x) => x.step_id === stepId);
    if (!s) throw new Error("Step not found");
    const now = new Date().toISOString();
    if (decision === "decline") s.status = "declined";
    else if (decision === "reset") { s.status = "proposed"; s.result = ""; }
    else if (s.provider.kind === "kbc") {
      s.status = "done"; s.result = s.step_id === "budget" ? "You can borrow up to €285.000 (monthly €1.090 over 25 years)." : "Arranged by KBC.";
    } else {
      const grant: ConsentGrant = {
        grant_id: nextGrantId++, partner_id: s.provider.id, partner_name: s.provider.name, goal_id: g.goal_id, goal_title: g.title,
        step_id: s.step_id, step_title: s.title, fields: s.data_shared, purpose: s.description,
        granted_on: "2026-10-20", expires_on: addDays("2026-10-20", s.consent_days), status: "active", revoked_on: null,
      };
      grants.push(grant);
      s.grant_id = grant.grant_id;
      s.status = "in_progress";
      s.ref = `${s.provider.id.slice(0, 4)}-${Math.floor(Math.random() * 90000 + 10000)}`;
      pushEvent(s.provider.id, "outbound", `KBC → ${s.provider.name}: ${s.title} (${s.data_shared.length} fields)`);
      window.setTimeout(() => {
        if (s.status !== "in_progress") return;
        s.status = "done";
        s.result = RESULTS[s.step_id] ?? "Completed by partner.";
        s.updated_at = new Date().toISOString();
        refresh(g);
        pushEvent(s.provider.id, "done", `${s.provider.name}: ${s.result}`);
      }, 2000);
    }
    s.updated_at = now;
    return delay(refresh(g));
  },
  cancelGoal(goalId: number): Promise<{ ok: boolean }> {
    findGoal(goalId).status = "cancelled";
    return delay({ ok: true });
  },
  consents(): Promise<ConsentsResponse> {
    const active = grants.filter((g) => g.status === "active");
    return delay({
      grants,
      partners_with_access: new Set(active.map((g) => g.partner_id)).size,
      fields_shared: active.reduce((n, g) => n + g.fields.length, 0),
    });
  },
  revokeConsent(grantId: number): Promise<ConsentsResponse> {
    const grant = grants.find((g) => g.grant_id === grantId);
    if (grant && grant.status === "active") {
      grant.status = "revoked"; grant.revoked_on = "2026-10-20";
      const g = goals.find((x) => x.goal_id === grant.goal_id);
      const s = g?.steps.find((x) => x.step_id === grant.step_id);
      if (g && s && s.status !== "done") { s.status = "blocked"; refresh(g); }
      pushEvent(grant.partner_id, "revoked", `Customer revoked ${grant.partner_name}'s access`);
    }
    return mockEco.consents();
  },
  sources(): Promise<SourcesResponse> {
    return delay({ sources: mockSources, connected: mockSources.filter((x) => x.status === "connected").length, note: "Simulated values." });
  },
  connectSource(sourceId: string, playbookId: string): Promise<SourcesResponse> {
    const src = mockSources.find((x) => x.source_id === sourceId);
    if (src && src.needs_consent) Object.assign(src, { status: "connected", connected_on: "2026-10-20", expires_on: addDays("2026-10-20", src.consent_days), playbook_id: playbookId, purpose: `${src.name} for your goal`, values: { simulated_value: 1 } });
    return mockEco.sources();
  },
  disconnectSource(sourceId: string): Promise<SourcesResponse> {
    const src = mockSources.find((x) => x.source_id === sourceId);
    if (src && src.needs_consent) Object.assign(src, { status: "available", connected_on: null, expires_on: null, values: {} });
    return mockEco.sources();
  },
  goalsReset(): Promise<{ ok: boolean }> { initial(); goals = []; grants = []; return delay({ ok: true }); },
  hideCandidate(id: string): void { hiddenCandidates.add(id); },
  overview(): Promise<EcosystemOverview> {
    const realised = goals.reduce<WinTotals>((t, g) => {
      t.customer_eur += g.outcome.customer_eur; t.hours_saved += g.outcome.hours_saved;
      t.kbc_revenue_eur += g.outcome.kbc_revenue_eur; t.partner_fees_eur += g.outcome.partner_fees_eur;
      t.partner_leads += g.outcome.partner_leads; t.kbc_products.push(...g.outcome.kbc_products);
      return t;
    }, { customer_eur: 0, hours_saved: 0, kbc_revenue_eur: 0, partner_fees_eur: 0, kbc_products: [], partner_leads: 0 });
    return delay({
      catalogue_items: 148, ecosystems: 9, building_blocks_used: 23, partners: 6,
      funnel: [
        { playbook_id: "buy_home", title: "Buy a home", icon: "🏡", detected: 412, started: 37, steps_done: 96, completed: 4, projected_2_3m: 94_600 },
        { playbook_id: "energy_renovation", title: "Make my home energy-efficient", icon: "🌱", detected: 655, started: 58, steps_done: 141, completed: 9, projected_2_3m: 150_650 },
        { playbook_id: "grow_pension", title: "Build up my pension", icon: "🌅", detected: 880, started: 61, steps_done: 120, completed: 22, projected_2_3m: 202_400 },
      ],
      partner_rows: [
        { partner_id: "immoscoop", name: "Immoscoop", ecosystems: ["Housing"], value_share: { model: "lead_fee", amount_eur: 40, pct: 0, note: "" }, leads: 31, completed: 18, fees_eur: 1240, avg_response_s: 2.1 },
        { partner_id: "setle", name: "Setle", ecosystems: ["Housing"], value_share: { model: "fee_per_completed_step", amount_eur: 120, pct: 0, note: "" }, leads: 14, completed: 11, fees_eur: 1320, avg_response_s: 2.4 },
        { partner_id: "energyscan", name: "EnergyScan", ecosystems: ["Energy"], value_share: { model: "fee_per_completed_step", amount_eur: 90, pct: 0, note: "" }, leads: 44, completed: 39, fees_eur: 3510, avg_response_s: 1.8 },
        { partner_id: "renopartners", name: "RenoPartners", ecosystems: ["Housing", "Energy"], value_share: { model: "revenue_share", amount_eur: 0, pct: 0.03, note: "3% of the job" }, leads: 27, completed: 12, fees_eur: 4180, avg_response_s: 3.0 },
        { partner_id: "mijn_verbouwpremie", name: "Subsidy desk", ecosystems: ["Energy"], value_share: { model: "subscription", amount_eur: 950, pct: 0, note: "per month" }, leads: 19, completed: 15, fees_eur: 950, avg_response_s: null },
      ],
      events: structuredClone(events),
      realised,
      projection: { customer_eur: 412_000_000, hours_saved: 9_800_000, kbc_revenue_eur: 186_000_000, partner_fees_eur: 38_000_000 },
      assumptions: [
        "Detection rates in the synthetic portfolio hold for 2.3M KBC customers",
        "10% of detected customers start a goal; 40% of those complete it",
        "Win estimates per step come from the playbooks and are illustrative",
      ],
      scoring_ms: 41.3,
    }, 150);
  },
};
