import type { ReactNode } from "react";
import type { TileGridPrefs } from "../api";

export interface GridTile {
  id: string;
  title: string;
  description: string;
  span: 1 | 2;
  eligible: boolean;
  content: ReactNode;
  cardKey?: string;
}
export interface GridCell {
  tile?: GridTile;
  id: string;
  slot: number;
  span: 1 | 2;
  pinned: boolean;
}

/** Suggestions fill only the first rows; rows the customer adds stay free for their own choices. */
const AUTO_SLOTS = 12;
export const emptyGrid = (): TileGridPrefs => ({ placements: {}, hidden: [], slotCount: AUTO_SLOTS });
const fits = (slot: number, span: number, taken: Set<number>) =>
  (span === 1 || slot % 2 === 0) && !taken.has(slot) && (span === 1 || !taken.has(slot + 1));

/** User placements reserve their cells first; suggestions only occupy the remaining cells. */
export function composeGrid(tiles: GridTile[], prefs: TileGridPrefs): GridCell[] {
  const taken = new Set<number>();
  const used = new Set<string>();
  const cells: GridCell[] = [];
  const occupy = (id: string, slot: number, span: 1 | 2, pinned: boolean, tile?: GridTile) => {
    cells.push({ id, slot, span, pinned, tile });
    taken.add(slot);
    if (span === 2) taken.add(slot + 1);
    used.add(id);
  };
  for (const [id, place] of Object.entries(prefs.placements)) {
    if (!prefs.hidden.includes(id)) occupy(id, place.slot, place.span, true, tiles.find((t) => t.id === id));
  }
  const candidates = tiles.filter((t) => t.eligible && !used.has(t.id) && !prefs.hidden.includes(t.id));
  // Every suggested tile gets a place: the automatic area grows with them (a fixed 12-slot area silently dropped
  // tiles). Slots past it, up to the stored slotCount ("+ Add row"), stay free for the customer's own choices.
  const need = taken.size + candidates.reduce((n, t) => n + t.span, 0);
  let auto = Math.max(AUTO_SLOTS, need + (need % 2));
  for (let slot = 0; slot < Math.max(auto, prefs.slotCount); slot++) {
    // a wide tile can't start on an odd slot: grow by a row rather than leave a tile out
    if (slot === auto - 1 && (candidates.length > 1 || candidates.some((t) => t.span === 2))) auto += 2;
    if (taken.has(slot)) continue;
    const total = Math.max(auto, prefs.slotCount);
    const index = slot >= auto ? -1 : candidates.findIndex((t) => slot + t.span <= total && fits(slot, t.span, taken));
    if (index >= 0) {
      const tile = candidates.splice(index, 1)[0];
      occupy(tile.id, slot, tile.span, false, tile);
    } else {
      occupy(`empty:${slot}`, slot, 1, false);
    }
  }
  return cells.sort((a, b) => a.slot - b.slot);
}

/** Move a tile without discarding other pins. Any displaced pins move to the first free cells. */
export function placeTile(prefs: TileGridPrefs, id: string, desired: number, span: 1 | 2): TileGridPrefs {
  const next = structuredClone(prefs);
  const slot = span === 2 ? desired - desired % 2 : desired;
  delete next.placements[id];
  next.hidden = next.hidden.filter((key) => key !== id);
  const overlaps = Object.entries(next.placements).filter(([, p]) => p.slot < slot + span && p.slot + p.span > slot);
  overlaps.forEach(([key]) => { delete next.placements[key]; });
  next.placements[id] = { slot, span };
  const taken = new Set<number>();
  Object.values(next.placements).forEach((p) => { taken.add(p.slot); if (p.span === 2) taken.add(p.slot + 1); });
  for (const [key, p] of overlaps) {
    let available = 0;
    while (!fits(available, p.span, taken)) available++;
    next.placements[key] = { slot: available, span: p.span };
    taken.add(available);
    if (p.span === 2) taken.add(available + 1);
  }
  const end = Math.max(next.slotCount, ...Object.values(next.placements).map((p) => p.slot + p.span));
  next.slotCount = Math.ceil(end / 2) * 2;
  return next;
}
