// Small chevrons for the hero tile hint and the accounts screen.
const common = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2.4,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  viewBox: "0 0 24 24",
  width: 16,
  height: 16,
};

export function ChevronRight() {
  return (<svg {...common} aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>);
}

export function ChevronLeft() {
  return (<svg {...common} aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>);
}
