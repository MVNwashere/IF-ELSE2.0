---
title: Finals Guide summary
type: context          # context | spec | decision | notes
status: final          # draft | review | final | outdated
incorporated: n/a      # no | partial | yes | n/a
code_refs: []
owner: Henri Lemahieu
created: 2026-10-20
updated: 2026-10-20
source: docs/Tectonic Hackathon - Finals Guide-1.pdf
---

# Finals Guide: Summary

Condensed from the 17-page organiser PDF. The wifi credentials are deliberately left out; see the PDF.

## Day schedule (20 Oct 2026)

| Time        | What                                              | Where                |
|-------------|---------------------------------------------------|----------------------|
| 08:00-08:40 | Arrival and breakfast                             | Vooruit Concertzaal  |
| 08:40-09:00 | Welcome by partners                               | Vooruit Concertzaal  |
| 09:00-16:00 | Hacking (lunch 12:30)                             | Vooruit Concertzaal  |
| **16:00**   | **Submissions close**                             | Builderbase          |
| 16:15-17:35 | Semi-final pitches                                | Wintercircus         |
| 18:00-19:20 | Finals: KBC and SD Worx finalists, Wonderful pitch, winner announced | Vooruit Theaterzaal |
| 19:20-21:00 | Reception with food                               | Club Wintercircus    |
| 21:15       | Tecnotonic party                                  | Wintercircus         |

Vooruit and Wintercircus are connected by a bridge. Follow Tectonic staff to the pitches.

**Our slot: 17:05-17:15, Room 1 (KBC).** Be there 10 minutes early (16:55). Teams in the same room: Dynamate before us, In4matics after us.

## Pitch format

- In person, **3 minutes pitch + 5 minutes questions**, strictly timed.
- You can't use your own device, so plan how the demo is shown (slides or video; pitch decks must be ppt or pdf).
- Partner staff are on site for questions and feedback.

## Submission (Builderbase, due 16:00)

One team member submits:

1. Short project description
2. Pitch presentation (under 3 minutes)
3. GitHub repo link
4. Screenshots of the Aikido scan

## Judging weights

| Criterion         | Weight | Question                       |
|-------------------|--------|--------------------------------|
| Creativity        | 25%    | How original is the idea?      |
| Pitch quality     | 25%    | How well did you present?      |
| Technical ability | 20%    | Does it work?                  |
| Fit               | 20%    | Did you solve the challenge?   |
| Security          | 10%    | How secure is it? (Aikido)     |

The Builderbase screenshot shows a different split (Originality 30 / Technical 30 / Fit 30 / Security 10). The written list above is what the guide's text says; this is worth checking with the organisers.

## Challenges

**KBC: design a scalable ecosystem that moves customers from intent to successful action.**
Guiding question: *How can KBC help customers achieve important life and business goals before they realise they need help?*

- The solution should recognise emerging needs, understand context, activate KBC capabilities and partners, keep the customer in control, and deliver a measurable triple win (customer, KBC, partners).
- Principles: bold and differentiated, personalised yet scalable to millions, trustworthy and privacy-conscious, commercially viable, and grounded in a believable journey shown through a proof of concept.
- Suggested domains: energy and sustainability, entrepreneurship and business growth, travel.
- Building blocks are listed in [kbc-ecosystems-summary.md](kbc-ecosystems-summary.md).

**SD Worx follow-up: "Can your solution stay trusted without becoming another task?"**
This extends the earlier challenge of turning fragmented organisational knowledge into a trusted shared resource.

- Keep it useful, reliable and up to date without making people document or maintain it.
- Invisible UI: automate in the background, verify only where human judgement adds value, minimise effort, fit existing workflows, and be understandable when people need to act.
- Think beyond documents: surface *who* has dealt with this, who really knows the customer or topic, and why things are done this way.
- Show how: what happens automatically, when human verification matters, how maintenance doesn't become a burden, how it fits the workflow, how it stays transparent. The goal is zero *unnecessary* effort, not zero human involvement.

## Technical partners

- **Aikido (security audit, 10% of score):** push the project to GitHub, create a free account at app.aikido.dev with GitHub, connect the repo and scan, fix vulnerabilities, push, and rescan. Submit a repo link and screenshots of the final scan showing the repo name and remaining vulnerabilities. Must be the same project built at the hackathon. Start early to leave time for fixes.
- **ElevenLabs:** text-to-speech and synthetic voices. Credits via the partner Discord `#coupon-codes` channel ("Start Redemption", use the registration email).
- **Cursor:** coding agent. Credits through the same Discord coupon flow.
- **Google Cloud:** use the team link in Builderbase (or `goo.gle/<your-code>`), enter your email to get GCP credentials, **valid for 1 week only**.

## Rules and fair play

- Build within the hackathon time slot, and submit one project per team.
- **Final means final:** no code or submission edits after the final submission.
- Keep the GitHub repo **public** until judging is done, and include a short README (what it is, how to run it, what's unfinished).
- Check that judges can open every link.
- Never upload passwords, API keys or confidential data.
- No plagiarism or cheating. Judges' decisions are final, and violations may lead to disqualification.
