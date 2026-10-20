import { useEffect, useLayoutEffect, useRef, useState, type HTMLAttributes, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { TileGridPrefs } from "../api";
import Sheet from "../ui/Sheet";
import { composeGrid, emptyGrid, placeTile, type GridCell, type GridTile } from "./tileGrid";

interface Props {
  tiles: GridTile[];
  editing: boolean;
  onEditing: (value: boolean) => void;
  initialPins: string[];
  resetVersion: number;
  saved: TileGridPrefs | null;               // the arrangement as stored (null: never arranged)
  onSave: (prefs: TileGridPrefs) => void;     // persist a new arrangement
  onPlace?: (tile: GridTile) => void;         // a tile was placed (the home may need to load its data)
}

type Drag = { id: string; slot: number; x: number; y: number; dx: number; dy: number; scale: number; active: boolean; over: number | null };

const DRAG_START_PX = 6;
const EDGE_SCROLL_PX = 64;

/** Tiles are whole multiples of a square unit: half the grid width wide, as many units tall as the content needs. */
function TileCell({ unit, gap, span, attrs, children }: {
  unit: number; gap: number; span: 1 | 2; attrs: HTMLAttributes<HTMLDivElement> & Record<string, unknown>; children: ReactNode;
}) {
  const content = useRef<HTMLDivElement>(null);
  const [rows, setRows] = useState(1);
  useLayoutEffect(() => {
    const el = content.current;
    if (!el || !unit) return;
    const measure = () => {
      el.style.height = "auto"; // the natural height, not the height stretched to the cell
      const natural = el.offsetHeight;
      el.style.height = "";
      setRows(Math.max(1, Math.ceil((natural + gap) / (unit + gap) - 0.01)));
    };
    measure();
    const watch = new MutationObserver(measure);
    watch.observe(el, { childList: true, subtree: true, characterData: true });
    return () => watch.disconnect();
  }, [unit, gap, span]);
  return <div {...attrs} style={{ gridColumn: `span ${span}`, gridRow: `span ${rows}`, ...attrs.style }}>
    <div ref={content} className="grid-cell-body">{children}</div>
  </div>;
}

export default function HomeTileGrid({ tiles, editing, onEditing, initialPins, resetVersion, saved, onSave, onPlace }: Props) {
  const [prefs, setPrefs] = useState<TileGridPrefs>(() => {
    if (saved) return structuredClone(saved);
    let initial = emptyGrid();
    initialPins.forEach((id) => {
      const tile = tiles.find((t) => t.id === id);
      if (tile) initial = placeTile(initial, id, Object.values(initial.placements).reduce((end, p) => Math.max(end, p.slot + p.span), 0), tile.span);
    });
    return initial;
  });
  const [filling, setFilling] = useState<number | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [message, setMessage] = useState("");
  const grid = useRef<HTMLDivElement>(null);
  const [unit, setUnit] = useState({ size: 0, gap: 10 });
  useLayoutEffect(() => {
    const el = grid.current;
    if (!el) return;
    const update = () => {
      const gap = parseFloat(getComputedStyle(el).columnGap) || 0;
      const size = (el.clientWidth - gap) / 2;
      setUnit((u) => (u.size === size && u.gap === gap ? u : { size, gap }));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const phone = document.querySelector<HTMLElement>(".phone");
  const save = (next: TileGridPrefs) => {
    onSave(next);
    setPrefs(next);
  };
  useEffect(() => {
    if (!resetVersion) return;
    setPrefs(emptyGrid());   // the layout reset already cleared the stored arrangement
  }, [resetVersion]);
  useEffect(() => { if (!editing) { setDrag(null); setFilling(null); } }, [editing]);

  const cells = composeGrid(tiles, prefs);
  // Outside edit mode only real tiles show; free spots and unavailable pins appear while editing.
  const shown = editing ? cells : cells.filter((c) => c.tile);
  const onGrid = new Set(cells.filter((c) => c.tile).map((c) => c.id));
  const put = (tile: GridTile, slot: number) => {
    save(placeTile(prefs, tile.id, slot, prefs.placements[tile.id]?.span ?? tile.span));
    onPlace?.(tile);
    setFilling(null);
    setMessage(`${tile.title} placed at position ${slot + 1}.`);
  };
  const remove = (cell: GridCell) => {
    const next = structuredClone(prefs);
    delete next.placements[cell.id];
    next.hidden = [...new Set([...next.hidden, cell.id])];
    save(next);
    setMessage(`${cell.tile?.title ?? "Tile"} removed.`);
  };

  // Drag a tile onto any free or taken spot; dropping pins it there.
  const dragRef = useRef<Drag | null>(null);
  dragRef.current = drag;
  const putRef = useRef(put);
  putRef.current = put;
  useEffect(() => {
    if (!drag) return;
    const scroller = grid.current?.closest<HTMLElement>(".phone-scroll");
    const move = (e: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const dx = (e.clientX - d.x) / d.scale, dy = (e.clientY - d.y) / d.scale;
      if (!d.active && Math.hypot(dx, dy) < DRAG_START_PX) return;
      e.preventDefault();
      const target = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>(".home-tile-grid > [data-slot]");
      const over = target && target.dataset.tileId !== d.id ? Number(target.dataset.slot) : null;
      if (scroller) {
        const r = scroller.getBoundingClientRect();
        if (e.clientY < r.top + EDGE_SCROLL_PX) scroller.scrollTop -= 10;
        else if (e.clientY > r.bottom - EDGE_SCROLL_PX) scroller.scrollTop += 10;
      }
      setDrag({ ...d, dx, dy, active: true, over });
    };
    const up = () => {
      const d = dragRef.current;
      setDrag(null);
      if (!d?.active || d.over === null) return;
      const tile = tiles.find((t) => t.id === d.id);
      if (tile) putRef.current(tile, d.over);
    };
    window.addEventListener("pointermove", move, { passive: false });
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  }, [drag !== null, tiles]);

  const startDrag = (e: React.PointerEvent<HTMLDivElement>, cell: GridCell) => {
    if (!editing || !cell.tile || e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
    const el = e.currentTarget;
    const scale = el.getBoundingClientRect().width / el.offsetWidth || 1; // PhoneScaler shrinks the phone with a CSS transform
    setDrag({ id: cell.id, slot: cell.slot, x: e.clientX, y: e.clientY, dx: 0, dy: 0, scale, active: false, over: null });
  };

  return (
    <section className="feed unified-feed" aria-label="For you">
      <div className="feed-head"><h2>For you</h2><button type="button" className="grid-edit-button" onClick={() => onEditing(!editing)}>{editing ? "Done editing" : "Edit tiles"}</button></div>
      <span className="sr-only" role="status">{message}</span>
      {editing && <p className="grid-edit-hint">Drag tiles to rearrange them. Tap a free spot to add a tile.</p>}
      <div ref={grid} className={`recommendation-grid home-tile-grid${editing ? " grid-editing" : ""}${drag?.active ? " grid-dragging" : ""}`}
        style={{ gridAutoRows: unit.size ? `${unit.size}px` : undefined }}>
        {shown.map((cell) => {
          const dragging = drag?.active && drag.id === cell.id;
          return (
            <TileCell key={cell.id} unit={unit.size} gap={unit.gap} span={cell.span} attrs={{
              className: `recommendation-cell section${cell.span === 2 ? " tile-wide" : ""}${cell.pinned ? " user-pinned" : ""}${dragging ? " grid-dragged" : ""}${drag?.active && drag.over === cell.slot ? " grid-drop" : ""}`,
              "data-tile-id": cell.id, "data-slot": cell.slot, "data-card-key": cell.tile?.cardKey,
              onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => startDrag(e, cell),
              style: dragging ? { transform: `translate(${drag.dx}px, ${drag.dy}px) scale(1.03)` } : undefined,
            }}>
              {cell.tile ? <>
                {editing && <>
                  <span className={`grid-state${cell.pinned ? " pinned" : ""}`}>{cell.pinned ? "Pinned" : "Suggested"}</span>
                  <button type="button" className="grid-remove" aria-label={`Remove ${cell.tile.title}`} onClick={() => remove(cell)}>×</button>
                </>}
                <div className="grid-tile-content" inert={editing}>{cell.tile.content}</div>
              </> : cell.pinned ? <div className="grid-unavailable"><b>Pinned tile</b><p>Unavailable for this date.</p>
                <button type="button" className="grid-remove" aria-label="Remove unavailable tile" onClick={() => { const next = structuredClone(prefs); delete next.placements[cell.id]; save(next); }}>×</button>
              </div> : <button type="button" className="grid-free" onClick={() => setFilling(cell.slot)} aria-label={`Fill free spot ${cell.slot + 1}`}>
                <span aria-hidden="true">+</span><small>Free spot</small>
              </button>}
            </TileCell>
          );
        })}
      </div>
      {editing && <div className="grid-edit-footer">
        <button type="button" className="btn-ghost" onClick={() => save({ ...prefs, slotCount: prefs.slotCount + 2 })}>+ Add row</button>
      </div>}
      {filling !== null && phone && createPortal(<Sheet title="Fill this spot" onClose={() => setFilling(null)}>
        <p className="ps-intro">Choose a tile for position {filling + 1}.</p>
        {[...tiles].sort((a, b) => Number(onGrid.has(a.id)) - Number(onGrid.has(b.id))).map((tile) => (
          <div className="gallery-row" key={tile.id}>
            <div className="gallery-text"><b>{tile.title}</b><span>{onGrid.has(tile.id) ? "On your home · moves here" : tile.description}</span></div>
            <button type="button" className="btn-primary small" aria-label={`Place ${tile.title}`} onClick={() => put(tile, filling)}>Place</button>
          </div>
        ))}
      </Sheet>, phone)}
    </section>
  );
}
