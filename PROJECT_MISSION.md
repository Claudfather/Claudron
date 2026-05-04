# Project Mission — Claudfather

## What this project is

Claudfather is an open-source ecosystem of four interlocking repositories for building, distributing, and evolving Claude Code agent infrastructure. It exists because running a serious multi-bot fleet today requires gluing together a dozen ad-hoc decisions — how skills are distributed, how bots store and retrieve knowledge, how skill quality is evaluated, how bots coordinate. Claudfather provides opinionated answers to all four questions, designed to work independently or together.

The four repositories:

- **clauDNA** — the canonical champion skills, hooks, and agents, distributed as a Claude Code marketplace plugin
- **Claudosseum** — the promotion engine: an arena where skills are evaluated and evolved, deciding what belongs in clauDNA
- **Claudlobby** — the always-on multi-bot fleet framework, the reference runtime for operating Claude Code bots in production
- **Claudron** — the markdown-based knowledge graph that bots query for context and write to as they accumulate experience

Each repo is independently useful. Used together they form a closed loop where bots run on canonical skills, capture knowledge from operation, feed real-world signal back into the arena, and the arena promotes evolved skills into the next canonical release.

## What it's becoming

A self-improving agent platform. The current state is four repos that work but don't yet talk to each other in the loops described below. The trajectory:

- clauDNA matures from a skill repo into a published marketplace plugin with versioned releases
- Claudosseum refocuses from "centralized distribution platform" to "promotion engine for clauDNA," with public arena leaderboards and community submission flows
- Claudlobby integrates clauDNA as its skill source and emits telemetry back to Claudosseum
- Claudron ships v1 with markdown vault, MCP server, and pack subscription model
- The loops close: Claudron context grounds Claudosseum battles in real scenarios, Claudosseum promotions ship via clauDNA, Claudlobby bots get smarter on each release

The ambition is that anyone running an agent fleet — solo dev or company — can adopt the entire stack or any subset, with no hosted dependencies required for basic use, and with a clear contribution path back into the canonical skills if their work is broadly useful.

## North star

The place where Claude Code agents are raised, equipped, and continuously improved.

## Guiding principles

- **Local-first by default.** Anyone can run the entire ecosystem on their own hardware with no hosted dependencies. The one exception is Claudosseum's hosted arena, which is opt-in and does not gate any other repo.
- **Tight, defensible repo boundaries.** Each repo has one job. clauDNA distributes, Claudosseum evaluates, Claudlobby runs, Claudron stores. When a feature could plausibly live in two repos, it lives in the one whose mission it best serves.
- **Bots are distinct entities.** Each bot in a Claudlobby fleet has its own GitHub App identity, Telegram bot, persona, and isolated state. The system never collapses bots back into a single shared identity.
- **Procedural vs. referential is a real distinction.** Skills (procedural, how-to) live in clauDNA. Knowledge (referential, what-we-know) lives in Claudron. They never blur.
- **Promotion to canonical is high-bar.** Anything that ships as part of clauDNA has earned it through arena evaluation and real-world telemetry. The bar is high precisely because users trust the canonical set.
- **Multi-tenant by design.** Claudron vaults are owned by their tenant. Claudosseum supports private arenas. Public packs and public arenas are opt-in. Nothing leaks across tenants without explicit publication.
- **Open source with a sustainable hosted layer.** Everything is OSS. The hosted infrastructure (Claudosseum's arena and registry) is provided as a public service but is replaceable — anyone can self-host.

## The ecosystem

```
┌───────────────────────────────────────────────────────────────┐
│                         Claudfather                           │
│                                                               │
│   ┌───────────┐    promotes    ┌──────────────┐               │
│   │  clauDNA  │ ◄────────────  │ Claudosseum  │               │
│   │ (plugin)  │                │   (arena)    │               │
│   └─────┬─────┘                └──────▲───────┘               │
│         │ installed                   │ telemetry,            │
│         │ on bots                     │ scenarios             │
│         ▼                             │                       │
│   ┌─────────────┐    queries    ┌─────┴─────────┐             │
│   │ Claudlobby  │ ────────────► │   Claudron    │             │
│   │   (fleet)   │ ◄──────────── │  (knowledge)  │             │
│   └─────────────┘    writes     └───────────────┘             │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

**The promotion loop:** Skills are submitted to or evolved within Claudosseum. They battle in the arena, with telemetry from real Claudlobby deployments contributing to their score alongside ELO. Champions get promoted into clauDNA on a release cadence. Users install the next clauDNA version and their bots get smarter.

**The knowledge loop:** Claudlobby bots write findings, decisions, and patterns to Claudron during operation. Future bots query Claudron before acting, gaining context that shapes their judgment. Mature reference content stays in Claudron and may be published as public packs. Recurring patterns become candidates for new skills, which enter Claudosseum for evaluation.

**The grounding loop:** Claudosseum battles draw scenarios from Claudron content (local for personal evaluation, public packs for community evaluation). Skills are evaluated against problems bots have actually encountered, not synthetic test cases.

## What we choose not to build

- **Hosted bot orchestration.** Claudlobby is a framework users run themselves. We will not become a SaaS that runs bots on people's behalf.
- **A single monolithic repo.** The four-repo split is intentional. Combining them would make each piece harder to adopt independently.
- **Forced telemetry.** Telemetry from Claudlobby to Claudosseum is opt-in, scrubbed, and never required for any other capability.
- **A central knowledge hub for everyone.** Claudron is local-first. There is no plan for a hosted shared brain that all deployments query. Federation via public packs is the substitute.
- **Skill marketplace transactions.** clauDNA is distributed free. We are not building monetization, paid skills, or skill licensing.

## Open questions

These are deliberately unresolved as of this writing — recorded so future development can either close them or note their continued openness.

- The exact promotion criteria from Claudosseum into clauDNA: pure ELO, ELO + telemetry threshold, ELO + maintainer review, or some weighted combination?
- Claudron's pack discovery model in v1: GitHub topics + word of mouth, or a lightweight central registry?
- Whether evolved skills in Claudosseum get a staging tier before becoming eligible for promotion, and what the promotion gate looks like.
- The right cadence for clauDNA releases (weekly, monthly, on-demand when champions change).
- The federation story for Claudron — whether opt-in instance-to-instance queries are a v2 feature or never built.

## Where this lives

This umbrella mission lives at the org level (in `Claudfather/.github` or a dedicated `Claudfather/claudfather` repo). Each sibling repo carries its own `PROJECT_MISSION.md` that derives from this one and scopes to that repo's specific role.
