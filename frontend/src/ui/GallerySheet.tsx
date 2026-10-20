import type { Component, GalleryItem } from "../api";
import Sheet from "./Sheet";

interface Props {
  gallery: GalleryItem[];
  onAdd: (component: Component) => void;
  onClose: () => void;
}

function Row({ item, onAdd }: { item: GalleryItem; onAdd: (c: Component) => void }) {
  return (
    <div className={`gallery-row ${item.state}`}>
      <div className="gallery-text">
        <b>{item.label}{item.is_hero && <span className="tag">main tile</span>}</b>
        <span>{item.description}</span>
        {item.reason && <span className="reason">{item.reason}</span>}
      </div>
      {item.state === "shown" ? (
        <span className="gallery-state">✓ shown</span>
      ) : (
        <button type="button" className="btn-primary small" onClick={() => onAdd(item.component)}>
          {item.is_hero ? "Use as main tile" : item.state === "hidden" ? "Show again" : "Add"}
        </button>
      )}
    </div>
  );
}

export default function GallerySheet({ gallery, onAdd, onClose }: Props) {
  const items = gallery.filter((g) => g.component !== "ForYouFeed");
  const suggested = items.filter((g) => g.suggested);
  const more = items.filter((g) => !g.suggested);
  return (
    <Sheet title="Add a tile" onClose={onClose}>
      {suggested.length > 0 && (
        <>
          <h4 className="sheet-group">Suggested for you</h4>
          {suggested.map((g) => <Row key={g.component} item={g} onAdd={onAdd} />)}
        </>
      )}
      <h4 className="sheet-group">More tiles</h4>
      {more.map((g) => <Row key={g.component} item={g} onAdd={onAdd} />)}
      {items.length === 0 && <div className="muted-note">No tiles available.</div>}
    </Sheet>
  );
}
