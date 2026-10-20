import CardStack from "../feed/CardStack";
import type { SectionProps } from "./types";

export default function ForYouFeed({ ctx }: SectionProps) {
  const feed = ctx.home.feed;
  return (
    <CardStack
      cards={feed.cards}
      caughtUp={feed.caught_up}
      hiddenCount={feed.hidden_count}
      asOf={ctx.asOf}
      onFeedback={ctx.onFeedback}
      onCta={ctx.onCta}
      onAskKate={(key) => ctx.openKate(key)}
    />
  );
}
