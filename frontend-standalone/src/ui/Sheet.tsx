// A bottom sheet that lives inside the phone frame (the .phone root is position: relative).
import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { NAV_ICONS } from "../components/icons";

interface Props {
  title: ReactNode;
  onClose: () => void;
  full?: boolean;
  headerExtra?: ReactNode;
  className?: string;
  children: ReactNode;
}

export default function Sheet({ title, onClose, full, headerExtra, className, children }: Props) {
  return (
    <>
      <motion.div
        className="sheet-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      />
      <motion.div
        className={`sheet ${full ? "full" : ""} ${className ?? ""}`}
        role="dialog"
        aria-modal="true"
        initial={{ y: "100%" }}
        animate={{ y: 0 }}
        exit={{ y: "100%" }}
        transition={{ type: "spring", stiffness: 380, damping: 38 }}
      >
        <div className="sheet-grip" aria-hidden="true" />
        <div className="sheet-head">
          <h2>{title}</h2>
          {headerExtra}
          <button type="button" className="sheet-close" aria-label="Close" onClick={onClose}><NAV_ICONS.close /></button>
        </div>
        <div className="sheet-body">{children}</div>
      </motion.div>
    </>
  );
}
