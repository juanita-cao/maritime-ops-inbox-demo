---
id: uwi-uwc-arrangement
title: Arrange an underwater inspection (UWI) or underwater cleaning (UWC)
when: Whether, where or how to arrange an underwater inspection or hull/propeller cleaning (UWI, UWC) for a vessel on a voyage.
mode: hybrid
status: draft
source: "Drafted by Claude 2026-10-01 from the owner's review (eval/e16_v1_to_v5_comparison.xlsx, column V, question 5); not yet reviewed by the owner."
requires:
  - the voyage's ports and schedule
  - vessel particulars (LOA, breadth moulded, last dry-docking) - not held this round
  - the CP off-hire clause and the hire rate (SOA / hire statement)
steps:
  - {id: s1, primitive: Select, text: "Read the voyage's coming ports and their ETA/ETB/ETD from the vessel facts and recent reports."}
  - {id: s2, primitive: Select, text: "Look in the company's records for diver or hull-cleaning companies at or near those ports. Public sources only with the website URL cited; none are connected, say so."}
  - {id: s3, primitive: Detect, text: "Establish the purpose: class or condition inspection, biofouling cleaning, redelivery condition, performance. If the question does not say, it is missing."}
  - {id: s4, primitive: Detect, text: "If a class inspection is needed, whether the provider holds the class society's approval; this goes into the inquiry."}
  - {id: s5, primitive: Ranking, text: "Rank the candidate ports by convenience: schedule slack, whether work at anchorage or berth is possible, timing against redelivery or the next employment."}
  - {id: s6, primitive: Generate, text: "Draft the inquiry email to the provider, with placeholders for what is not known."}
  - {id: s7, primitive: Detect, text: "Off-hire: time lost may be off-hire under the CP. Give a rough range from the hire rate in the latest SOA or hire statement, or say the rate is missing."}
---
Give a next step, not a list of questions. Name a port as convenient only from the voyage records;
a port the vessel has already left is not an option. UWC is often restricted by port environmental
rules and needs a permit; UWI is usually easier. Do not state vessel particulars you did not read:
use placeholders.

Inquiry email (placeholders in brackets; keep the language of the officer's question for the
covering line, the email itself in English):

```
Subject: M/V [vessel] - UWI/UWC enquiry at [port], ETA [date]

Dear Sirs,

Please advise whether you can attend M/V [vessel] at [port].
- ETA / ETD: [date] / [date]
- LOA / Breadth moulded: [m] / [m]
- Estimated arrival draft: [m]
- Last dry-docking: [date]
- Service: [UWI / UWC]

Please confirm: whether the work can be done, the time required, whether at anchorage or berth,
whether night work is allowed, and the class approval you hold for inspection reports [class
society]. Please also advise any port permit needed and your quotation.

Best regards,
[name]
```
