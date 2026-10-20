import { useEffect, useState, type ReactNode } from "react";

const PHONE_W = 390;
const PHONE_H = 844;
const MARGIN = 40;

function computeScale(): number {
  if (typeof window === "undefined") return 1;
  return Math.min(1, (window.innerHeight - MARGIN) / (PHONE_H + 36));
}

/** Scales the phone frame so it always fits the viewport height, reserving the scaled box so nothing overflows. */
export default function PhoneScaler({ children }: { children: ReactNode }) {
  const [scale, setScale] = useState(computeScale);
  useEffect(() => {
    const onResize = () => setScale(computeScale());
    window.addEventListener("resize", onResize);
    onResize();
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return (
    <div className="phone-scaler" style={{ width: PHONE_W * scale, height: PHONE_H * scale }}>
      <div style={{ transform: `scale(${scale})`, transformOrigin: "top center", width: PHONE_W, height: PHONE_H, marginLeft: (PHONE_W * scale - PHONE_W) / 2 }}>
        {children}
      </div>
    </div>
  );
}
