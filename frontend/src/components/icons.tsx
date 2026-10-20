// Inline SVG icons (stroke-based, currentColor). Keys match the QuickActions icon vocabulary.
const common = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, viewBox: "0 0 24 24" };

export const ICONS: Record<string, () => React.JSX.Element> = {
  transfer: () => (<svg {...common}><path d="M7 7h11m0 0-3-3m3 3-3 3M17 17H6m0 0 3 3m-3-3 3-3" /></svg>),
  split: () => (<svg {...common}><circle cx="7" cy="7" r="3" /><circle cx="17" cy="17" r="3" /><path d="M14 5h4v4M10 19H6v-4" /></svg>),
  invoice: () => (<svg {...common}><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></svg>),
  scan: () => (<svg {...common}><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M4 12h16" /></svg>),
  call: () => (<svg {...common}><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" /></svg>),
  savings: () => (<svg {...common}><path d="M4 11a7 7 0 0 1 7-5h5l3-2v6l-1 1v3a3 3 0 0 1-3 3h-1l-1 2h-3l-1-2H8l-1 2H5l-1-4z" /><circle cx="15" cy="10" r="1" fill="currentColor" /></svg>),
  card: () => (<svg {...common}><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M3 10h18M7 15h3" /></svg>),
  insurance: () => (<svg {...common}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M9 12l2 2 4-4" /></svg>),
  budget: () => (<svg {...common}><path d="M4 20V10M10 20V4M16 20v-8M22 20H2" /></svg>),
  pension: () => (<svg {...common}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>),
};

export function Icon({ name }: { name: string }) {
  const C = ICONS[name] ?? ICONS.card;
  return <C />;
}

export const NAV_ICONS = {
  home: () => (<svg {...common}><path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" /></svg>),
  pay: () => (<svg {...common}><path d="M7 7h11m0 0-3-3m3 3-3 3M17 17H6m0 0 3 3m-3-3 3-3" /></svg>),
  cards: () => (<svg {...common}><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M3 10h18" /></svg>),
  more: () => (<svg {...common}><circle cx="5" cy="12" r="1.5" fill="currentColor" /><circle cx="12" cy="12" r="1.5" fill="currentColor" /><circle cx="19" cy="12" r="1.5" fill="currentColor" /></svg>),
  kate: () => (<svg {...common}><path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-9l-5 4v-4H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" /><path d="M8 10h.01M12 10h.01M16 10h.01" /></svg>),
  edit: () => (<svg {...common}><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M13.5 6.5l4 4" /></svg>),
  close: () => (<svg {...common}><path d="M6 6l12 12M18 6L6 18" /></svg>),
  send: () => (<svg {...common}><path d="M4 12l16-8-6 16-2-6z" /><path d="M12 14l8-10" /></svg>),
  eye: () => (<svg {...common}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>),
  eyeOff: () => (<svg {...common}><path d="M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.6 9.6 0 0 0 5.4-1.6" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></svg>),
};

export const FAMILY_ICON: Record<string, string> = {
  deadline: "⏰", anomaly: "🔍", forecast: "📉", opportunity: "💡", milestone: "🎉", protection: "🛡️",
};
