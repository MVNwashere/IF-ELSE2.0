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
          onConnectSource={(sourceId) => {
            void goals.connectSource(sourceId, goal.playbook_id).then((r) => { if (r) notify("Connected with your OK. Revoke it any time in your passport."); });
          }}
          onStartNext={(pid) => startGoal(pid)}
          onInvite={(username) => {
            void goals.invite(goal.goal_id, username).then((r) => { if (r) notify(`Invitation sent to ${username}`); });
          }}
          onStall={(answer) => {
            void goals.answerStall(goal.goal_id, answer).then((r) => {
              if (!r) return;
              notify(answer === "keep" ? "Okay, we keep going" : answer === "pause" ? "Paused. No reminders." : answer === "resume" ? "Welcome back" : "Goal stopped");
              if (answer === "stop") close();
            });
          }}
        />
      );
    }
    case "consent": {
      const goal = goals.goal(sheet.goalId);
      const step = goal?.steps.find((s) => s.step_id === sheet.stepId);
      if (!goal || !step) return null;
      const back = () => setSheet({ kind: "journey", goalId: goal.goal_id });
      const decide = (d: "approve" | "decline", partnerId?: string) => {
        void goals.decide(goal.goal_id, step.step_id, d, partnerId).then((r) => {
          if (!r) return;
          const name = step.alternatives?.find((o) => o.provider.id === partnerId)?.provider.name ?? step.provider.name;
          notify(d === "decline" ? "Declined. Nothing was shared."
            : step.provider.kind === "advisor" ? "Meeting booked. Your advisor has your file."
            : step.provider.kind === "kbc" ? "Done by KBC" : `Approved. ${name} is on it.`);
          back();
        });
      };
      return (
        <ConsentSheet key="eco-consent" step={step} asOf={asOf} busy={goals.busy}
          onApprove={(pid) => decide("approve", pid)} onDecline={() => decide("decline")} onClose={back} />
      );
    }
    case "passport":
      return (
        <PassportSheet
          key="eco-passport"
          asOf={asOf}
          playbookIds={(goals.data?.goals ?? []).filter((g) => g.status !== "cancelled").map((g) => g.playbook_id)}
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
