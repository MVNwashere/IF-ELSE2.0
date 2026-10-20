// The ecosystem sheets inside the phone: journey → consent preview → back, playbooks, consent passport.
import ConsentSheet from "./ConsentSheet";
import JourneySheet from "./JourneySheet";
import PassportSheet from "./PassportSheet";
import PlaybooksSheet from "./PlaybooksSheet";
import type { GoalsState } from "./useGoals";

export type EcoSheet =
  | { kind: "journey"; goalId: number }
  | { kind: "consent"; goalId: number; stepId: string }
  | { kind: "passport"; back?: number }
  | { kind: "playbooks" };

interface Props {
  sheet: EcoSheet;
  goals: GoalsState;
  asOf: string;
  setSheet: (s: EcoSheet | null) => void;
  startGoal: (playbookId: string) => void;
  notify: (msg: string) => void;
}

export default function EcoSheets({ sheet, goals, asOf, setSheet, startGoal, notify }: Props) {
  const close = () => setSheet(null);
  switch (sheet.kind) {
    case "journey": {
      const goal = goals.goal(sheet.goalId);
      if (!goal) return null;
      return (
        <JourneySheet
          key="eco-journey"
          goal={goal}
          busy={goals.busy}
          onReview={(s) => setSheet({ kind: "consent", goalId: goal.goal_id, stepId: s.step_id })}
          onReset={(s) => void goals.decide(goal.goal_id, s.step_id, "reset")}
          onPassport={() => setSheet({ kind: "passport", back: goal.goal_id })}
          onCancel={() => { void goals.cancel(goal.goal_id).then((r) => { if (r) { notify("Goal stopped"); close(); } }); }}
          onClose={close}
        />
      );
    }
    case "consent": {
      const goal = goals.goal(sheet.goalId);
      const step = goal?.steps.find((s) => s.step_id === sheet.stepId);
      if (!goal || !step) return null;
      const back = () => setSheet({ kind: "journey", goalId: goal.goal_id });
      const decide = (d: "approve" | "decline") => {
        void goals.decide(goal.goal_id, step.step_id, d).then((r) => {
          if (!r) return;
          notify(d === "decline" ? "Declined. Nothing was shared." : step.provider.kind === "kbc" ? "Done by KBC" : `Approved. ${step.provider.name} is on it.`);
          back();
        });
      };
      return (
        <ConsentSheet key="eco-consent" step={step} asOf={asOf} busy={goals.busy}
          onApprove={() => decide("approve")} onDecline={() => decide("decline")} onClose={back} />
      );
    }
    case "passport":
      return (
        <PassportSheet
          key="eco-passport"
          onClose={() => setSheet(sheet.back ? { kind: "journey", goalId: sheet.back } : null)}
          onChanged={() => { notify("Access revoked"); void goals.load(); }}
          onError={notify}
        />
      );
    case "playbooks":
      return (
        <PlaybooksSheet
          key="eco-playbooks"
          playbooks={goals.data?.playbooks ?? []}
          goals={goals.data?.goals ?? []}
          busy={goals.busy}
          onStart={startGoal}
          onOpenGoal={(id) => setSheet({ kind: "journey", goalId: id })}
          onClose={close}
        />
      );
  }
}
