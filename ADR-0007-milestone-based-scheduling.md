# ADR-0007: Milestone-Based Scheduling Architecture

**Status:** Accepted
**Date:** 2026-06-30
**Supersedes:** Implicit calendar-only scheduling model in place since v1
**Related docs:** `docs/architecture/scheduling_principles.md`,
`docs/architecture/milestone_architecture.md` (to follow in PR-1A),
`seed/bhendi_v3_final_design.md` (the catalyst for this ADR)

---

## 1. Context

Agronous schedules cultivation activities by projecting `ActivityTemplate`
rows onto a calendar using `sowing_date + day_offset`
(`services/schedule_engine.py`). This model assumes every agronomically
significant event in a crop's life — flowering, fruit set, first harvest,
senescence — occurs at a fixed, predictable number of days after sowing,
uniformly across varieties, seasons, and growing conditions.

That assumption does not hold. The catalyst for this ADR was a concrete
failure of it: Bhindi (Okra) v3 moved the first-harvest activity from
`day_offset=52` to `day_offset=63` to resolve an internal stage-boundary
inconsistency (see `bhendi_v3_final_design.md`, Part D). That change was
internally consistent — but real first-harvest timing for Bhindi ranges
roughly 40–65 DAS depending on variety, and the fix delayed the
farmer-visible harvest task by 11 days without re-validating against field
reality. The plant did not move. The number did.

This is not a Bhindi-specific defect. It's a structural property of a
scheduling model that has only one source of truth — elapsed time since
sowing — for events that are actually governed by biology. Every future
crop template will hit the same failure mode for flowering, transplant
recovery, ratooning, or any other DAS-anchored physiological event that
varies by variety, weather, or management practice.

## 2. Decision

Agronous adopts a **milestone-based scheduling architecture**. Biological
events ("milestones") become first-class domain entities, resolved from
field evidence, with DAS demoted from *authority* to *expected window*.
The scheduler continues to be a pure, deterministic projection — it now
projects from milestone anchor dates instead of exclusively from
`sowing_date`.

```
Templates
        │
        ▼
Evidence
        │
        ▼
Milestones
        │
        ▼
Scheduler
        │
        ▼
Activities
        │
        ▼
Recommendations
```

Templates declare what they need (an anchor milestone + offset +
recurrence). Evidence, captured through existing Layer 1.5 assessments and
farmer observations, resolves milestones. Milestones carry dates. The
scheduler consumes those dates exactly as it consumes `sowing_date` today
— it does not infer, estimate, or validate biology itself.

## 3. Architectural Invariants

These are non-negotiable contracts. Any future PR — for any crop, not
just Bhindi — that violates one of these should be rejected at review,
not debated on its individual merits.

**Invariant 1 — Schedulers never infer biology.**
Schedulers consume milestone dates. They never estimate or resolve them.

**Invariant 2 — Milestones are biological facts.**
Milestones represent observed or estimated crop events. They are not
schedule entries, and they are not owned by any one crop's template file.

**Invariant 3 — Templates are declarative.**
Templates declare an anchor, an offset, and a recurrence. They never
contain crop-specific scheduling logic (e.g. no
`if crop == "Bhindi": first_harvest = sowing_date + timedelta(days=55)`,
anywhere, ever).

**Invariant 4 — Evidence precedes milestones.**
Evidence may change as more observations arrive. Milestones are derived
from evidence, not the reverse — a milestone is never asserted without a
traceable evidence path that produced it.

**Invariant 5 — Time is advisory.**
DAS defines an expected window, used to prompt scouting and to provide a
fallback estimate when no evidence exists yet. It never overrides a
confirmed biological observation. Biology owns the calendar — schedules
adjust to reflect biological reality; biological events are never shifted
to satisfy schedule boundaries.

## 4. Stable Vocabulary

Established by this ADR, used consistently in all subsequent design and
code:

| Term | Meaning |
|---|---|
| **Evidence** | A farmer- or AI-derived observation tied to a Layer 1.5 assessment or other source, describing what was seen in the field. |
| **Milestone** | A biological event in a season's life (e.g. `FIRST_HARVEST`, `FLOWERING_ONSET`), resolved from evidence or estimated from a DAS fallback. |
| **Anchor** | The specific date a resolved (or estimated) milestone provides, which a template's `day_offset` is measured relative to. |
| **Projection** | The deterministic act of turning templates + anchors + offsets into dated `ScheduleActivity` rows. The scheduler's only job. |
| **Resolver** | The service that evaluates evidence against milestone definitions and writes resolved milestone records. |
| **Synchronizer** | The service that reacts to a milestone resolution/change and triggers schedule regeneration for affected templates. |
| **Scheduler** | `services/schedule_engine.py`. Pure projection engine. Never infers, never resolves, never estimates. |

"Anchor," "milestone," "trigger," and "event" are not interchangeable.
Using them precisely is part of keeping this contract legible to future
contributors.

## 5. Deferred Decisions

This ADR establishes the architecture and its invariants. It intentionally
does **not** define:

- Milestone resolution algorithms (how evidence maps to a resolved date)
- Scheduler regeneration behavior (when and how pending activities get rebuilt)
- Estimation heuristics (how DAS fallbacks are computed pre-evidence)
- Background processing or async infrastructure
- Event bus / publisher architecture
- Crop-specific milestone definitions (e.g. Bhindi's `FIRST_HARVEST`)
- Bhindi template migration to the new model

These are scoped to subsequent ADRs and implementation PRs (PR-2 through
PR-4, per the roadmap in section 7). A PR-1A/1B reviewer should treat any
of the above as explicitly out of scope for those PRs.

## 6. Rejected Alternatives

**Rejected: Add `first_harvest_date` (and similar) as nullable columns on `Season`.**
Doesn't scale past one or two milestones per crop. Couples the `Season`
schema to specific crops' physiology. Encourages unbounded nullable-column
growth as more milestones are added across more crops.

**Rejected: Let the scheduler compute/estimate milestone dates itself.**
Violates scheduler purity (Invariant 1). Reintroduces crop-specific logic
into a component whose entire value is being crop-agnostic. Makes
scheduling non-deterministic — the same templates could project different
dates depending on when the scheduler happened to run relative to
evidence arrival.

**Rejected: Continue with calendar-only (DAS-only) scheduling.**
The Bhindi case demonstrates the failure mode directly: biology varies by
variety, weather, and management practice in ways a single fixed DAS
number cannot capture. This produces schedules that are internally
consistent but factually wrong, and the error is silent — nothing in a
DAS-only model can detect or correct it.

## 7. Implementation Roadmap (informative, not binding)

```
ADR-0007 (this document)
    │
    ▼
PR-1A  Domain Infrastructure  (MilestoneDefinition, SeasonMilestone,
                                SeasonMilestoneHistory; models, migration,
                                enums, repository helpers, seed data only)
    │
    ▼
PR-1B  Validation Infrastructure  (anchor/definition integrity checks,
                                    circular-dependency detection,
                                    orphan detection)
    │
    ▼
PR-2   Resolution Infrastructure  (Resolver, Estimator,
                                    MilestoneResolutionResult)
    │
    ▼
PR-3   Synchronization + Scheduler  (anchor-aware projection, reactive
                                      regeneration, dependency validation)
    │
    ▼
PR-4   Bhindi Adoption  (FIRST_HARVEST milestone, harvest observation
                          capture, Stage 7 anchored to FIRST_HARVEST)
```

PR-1A and PR-1B are pure data-model and validation changes respectively,
with zero behavior change to existing seasons or the existing scheduler.
PR-2 through PR-4 introduce behavior change incrementally, each within the
contract this ADR establishes.

## 8. Consequences

**Positive:** Harvest (and later, flowering, transplant recovery,
ratooning, and other physiological events) becomes correct across
varieties, seasons, and growing conditions without crop-specific branching
anywhere in the scheduler. The domain model gains an auditable evidence
trail for every biological event a season passes through. The
architecture generalizes to every future crop template, not just Bhindi.

**Costs:** Three new tables and a resolution/synchronization layer where
today there is a single `day_offset` integer. Template authoring requires
understanding the anchor/offset model, not just a flat DAS number. Schema
and review complexity increase for the templates that adopt milestones
(Bhindi first; others as needed) until the new vocabulary is established
project-wide.

**Explicitly not a cost:** No event bus, background workers, or
async infrastructure are introduced by this ADR. Per Invariant-adjacent
governance (see `scheduling_principles.md`, Principle 4), that
infrastructure is deferred until a second independent consumer of
milestone changes actually exists.
