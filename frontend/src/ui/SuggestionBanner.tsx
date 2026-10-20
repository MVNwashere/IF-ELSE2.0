import { motion } from "framer-motion";
import type { Component, TileSuggestion } from "../api";

interface Props {
  suggestion: TileSuggestion;
  onDecide: (component: Component, decision: "accept" | "dismiss") => void;
}

export default function SuggestionBanner({ suggestion, onDecide }: Props) {
  return (
    <motion.div
      className="suggestion"
      layout
      initial={{ opacity: 0, y: -10, height: 0 }}
      animate={{ opacity: 1, y: 0, height: "auto" }}
      exit={{ opacity: 0, y: -10, height: 0, marginBottom: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 32 }}
    >
      <div className="suggestion-inner">
        <div className="suggestion-text">
          <b>💡 {suggestion.title}</b>
          <span>{suggestion.reason}</span>
        </div>
        <div className="suggestion-actions">
          <button type="button" className="btn-primary small" onClick={() => onDecide(suggestion.component, "accept")}>
            {suggestion.as_hero ? "Use as main tile" : "Add"}
          </button>
          <button type="button" className="btn-ghost small" onClick={() => onDecide(suggestion.component, "dismiss")}>Not now</button>
        </div>
      </div>
    </motion.div>
  );
}
