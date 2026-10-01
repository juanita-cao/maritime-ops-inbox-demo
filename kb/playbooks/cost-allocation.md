---
id: cost-allocation
title: Who bears a cost, owners or charterers
when: Which party, owners or charterers, should bear a cost or expense under the charter party.
mode: proposal_reasoning
status: draft
source: "Drafted by Claude 2026-10-01 from the owner's review (column V, question 2); not yet reviewed by the owner."
requires:
  - the cost itself (what, how much, which voyage or event)
  - the CP clause that governs it
  - the correspondence with the charterers about it
steps:
  - {id: s1, primitive: Detect, text: "Identify the cost: item, amount, voyage or event, parties, dates. If the question does not make it clear which cost, that is missing and no conclusion is given."}
  - {id: s2, primitive: Select, text: "Find the CP clauses that may govern it and the emails with the charterers about it."}
  - {id: s3, primitive: Extract, text: "Extract the clause conditions and the facts that bear on them."}
  - {id: s4, primitive: Compare, text: "Check whether the facts satisfy the clause conditions."}
  - {id: s5, primitive: Allocation, text: "Propose which party bears the cost, as a proposal for review."}
  - {id: s6, primitive: Generate, text: "Give the proposal with the clause cited, the counter-evidence, and the missing information."}
---
In practice cash to master (CTM) is arranged by the owners. For other costs, for example a
pre-loading survey of a cargo that needs one, or tallying of a cargo, the answer
depends on what the charter party says: cite the clause. If no clause was read, say so and give no
conclusion; a complaint in the charterers' email is not a clause. This is a proposal: OP,
chartering or legal reviews it before anyone acts.
