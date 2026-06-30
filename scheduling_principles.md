# Agronous Scheduling Principles

These five principles govern every template, resolver, and scheduler
change made under ADR-0007. They are the plain-language form of that
ADR's Architectural Invariants — read this for the "why," read the ADR
for the formal contract.

---

### Principle 1 — Time is evidence, not authority.

Calendar dates are expected windows, not facts. Observations determine
biological milestones; DAS only proposes when to go look.

### Principle 2 — Milestones are biological facts.

Milestones represent observed (or, until observed, estimated) crop
events. They are not schedule entries, and a schedule entry is never
mistaken for the milestone itself.

### Principle 3 — Schedulers are pure projections.

Given templates, anchors, and offsets, produce activities. No crop logic.
No physiology. No recommendations. If `services/schedule_engine.py` ever
needs to know what crop it's scheduling for, something upstream has
leaked.

### Principle 4 — Every abstraction must have an immediate consumer.

Infrastructure is introduced only when an existing workflow requires it.
No event buses, queues, or version chains until a second real consumer
exists — see ADR-0007 §5 and §8 for what this currently rules out.

### Principle 5 — Biology owns the calendar.

Never move a biological event to satisfy a schedule boundary. Adjust the
schedule to reflect biological reality. This is the principle the
original Bhindi v3 DAS-overlap fix violated — it moved the *number*
because the *plant* was inconvenient to the stage table, not the other
way around. It is the one most worth defending in future review.

---

## Vocabulary

See ADR-0007 §4 for the canonical glossary (Evidence, Milestone, Anchor,
Projection, Resolver, Synchronizer, Scheduler). Use these terms precisely;
they are not interchangeable.
