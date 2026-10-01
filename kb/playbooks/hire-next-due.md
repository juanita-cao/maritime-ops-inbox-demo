---
id: hire-next-due
title: Next hire payment date
when: When the next hire payment is due, or what the hire status of a vessel is.
mode: evidence_reasoning
status: draft
source: "Drafted by Claude 2026-10-01 from the owner's review (column V, question 10); not yet reviewed by the owner."
requires:
  - the latest hire statement or SOA (period and amount)
  - the CP hire clause (payment interval, in advance or in arrears)
steps:
  - {id: s1, primitive: Select, text: "Find the latest hire statement or SOA of the vessel (emails and attachment names)."}
  - {id: s2, primitive: Extract, text: "Extract the current period (start, end) and the amount, from the email body or, if read, the attachment."}
  - {id: s3, primitive: Select, text: "Find the CP hire clause: payment interval (for example every 15 days) and whether payment is in advance."}
  - {id: s4, primitive: Transform, text: "Compute the next due date from the period and the interval; state the dates you used."}
  - {id: s5, primitive: Generate, text: "Give the date, or say which input is missing."}
---
Never assume an interval. If the period or the clause is missing, say which, and give the last
period end that is known. A hire statement with a bank confirmation means that payment was made:
it is not an unpaid invoice. The due list holds only dates that were entered as tasks; an empty due
list does not mean no hire is due.
