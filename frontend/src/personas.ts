// The demo customers, with the one-line story the login screen and the demo panel show.
export interface DemoPersona { username: string; name: string; hint: string }

export const DEMO_PERSONAS: DemoPersona[] = [
  { username: "lotte", name: "Lotte", hint: "student → freelancer, time travel 2018–2026" },
  { username: "sara", name: "Sara", hint: "freelancer and young mother" },
  { username: "jan", name: "Jan", hint: "retiree, 71" },
  { username: "marc", name: "Marc", hint: "the 52-year-old investor" },
  { username: "tom", name: "Tom", hint: "employee with a side business" },
  { username: "els", name: "Els", hint: "kids at uni, mother in care" },
  { username: "amir", name: "Amir", hint: "newcomer, 4 months of data" },
  { username: "pieter", name: "Pieter", hint: "SME owner, clients abroad" },
  { username: "nina", name: "Nina", hint: "BNPL and bounced debits" },
];
export const ADVISOR = { username: "advisor", name: "KBC console", hint: "the ecosystem console for advisors" };
