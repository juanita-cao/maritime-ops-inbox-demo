---
id: port-arrival-checklist
title: Port arrival checklist
when: What to watch, prepare or confirm for a port call (arrival, berthing, cargo operations).
mode: hybrid
status: draft
source: "Drafted by Claude 2026-10-01 from the owner's review (column V, question 17); not yet reviewed by the owner."
requires:
  - the voyage stage and the next port with its ETA
  - the company's records on that port (agent, earlier problems, instructions)
steps:
  - {id: s1, primitive: Select, text: "Read the voyage stage, the next port and the ETA from the vessel facts and the latest reports."}
  - {id: s2, primitive: Select, text: "Find the company's records on the port: the agent, instructions, earlier issues, arrival notices."}
  - {id: s3, primitive: Detect, text: "List the pre-arrival information still open: ETB, draft and water-density limits, berth or anchorage, ship's or shore cranes, gangs, ISPS level, garbage rules, documents."}
  - {id: s4, primitive: Generate, text: "Give the checklist: company-specific items first, general practice second and labelled as such."}
  - {id: s5, primitive: Detect, text: "Mark what needs current confirmation (weather, port restrictions, routing); no live source is connected."}
---
What is useful depends on the stage. Before the voyage starts, a general overview of the port is
enough. Once a voyage is under way, lead with what the company's own records say (ETA and its
different bases, the agent, redelivery or survey arrangements, cash to master) and keep generic
advice short. The agent's reply to the master's nine pre-arrival questions (berthing prospects,
discharge rate, draft and density, air draft, shore or ship's gear, gangs, ISPS, garbage, special
requirements) is the model for the open-items list.
