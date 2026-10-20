import { NAV_ICONS } from "../components/icons";
import Sheet from "./Sheet";

interface Props {
  name: string;
  onClose: () => void;
  onSettings: () => void;
  onPermissions: () => void;
  onAboutYou: () => void;
  onEdit: () => void;
  masked: boolean;
  privacy: boolean;
  onReveal: () => void;
}

export default function ProfileSheet(p: Props) {
  return (
    <Sheet title="Your profile" onClose={p.onClose}>
      <div className="profile-intro">
        <span className="profile-avatar">{p.name.slice(0, 1)}</span>
        <div><h3>{p.name}</h3><p>Your banking, your preferences.</p></div>
      </div>
      <div className="profile-menu">
        <button type="button" onClick={p.onSettings}><span className="profile-menu-icon"><NAV_ICONS.more /></span><span><b>Settings & appearance</b><small>Text size, privacy and personalisation</small></span><span aria-hidden="true">›</span></button>
        <button type="button" onClick={p.onAboutYou}><span className="profile-menu-icon"><NAV_ICONS.user /></span><span><b>What KBC knows about you</b><small>What you told us, what we worked out, and what it may be used for</small></span><span aria-hidden="true">›</span></button>
        <button type="button" onClick={p.onPermissions}><span className="profile-menu-icon"><NAV_ICONS.eye /></span><span><b>Permissions & data</b><small>Manage partner access and connected sources</small></span><span aria-hidden="true">›</span></button>
        <button type="button" onClick={p.onEdit}><span className="profile-menu-icon"><NAV_ICONS.edit /></span><span><b>Edit home</b><small>Choose and arrange your tiles</small></span><span aria-hidden="true">›</span></button>
        {p.privacy && <button type="button" onClick={p.onReveal}><span className="profile-menu-icon"><NAV_ICONS.eyeOff /></span><span><b>{p.masked ? "Show amounts" : "Hide amounts"}</b><small>Revealed amounts hide again automatically</small></span></button>}
      </div>
    </Sheet>
  );
}
