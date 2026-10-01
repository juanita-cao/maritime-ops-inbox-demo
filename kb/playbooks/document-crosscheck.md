---
id: document-crosscheck
title: Cross-check bill of lading, mate's receipt and letter of indemnity
when: Check whether the B/L, the mate's receipt (MR) and the LOI (or other cargo documents) agree with each other.
mode: evidence_reasoning
status: draft
source: "Drafted by Claude 2026-10-01 from the owner's review (column V, question 1); not yet reviewed by the owner."
requires:
  - the text of each document (attachments are stored as file names only this round)
steps:
  - {id: s1, primitive: Select, text: "Find the emails and attachment names for each document (B/L, MR, LOI) of the voyage."}
  - {id: s2, primitive: Extract, text: "From each document whose text you read, extract: vessel name, voyage, load and discharge ports, B/L number, shipper, consignee, cargo name and quantity, issue date."}
  - {id: s3, primitive: Compare, text: "Compare field by field. Reconcile quantities before calling them inconsistent (several B/Ls adding up to one total; a daily figure against a total)."}
  - {id: s4, primitive: Compare, text: "For an LOI, compare its wording with the P&I Club standard LOI wording, only if the LOI text was read."}
  - {id: s5, primitive: Detect, text: "List the documents whose content is not available. Never call documents consistent when one of them was not read."}
  - {id: s6, primitive: Generate, text: "Report what matches, what does not, and what could not be compared."}
---
An email that says documents are attached does not give their content. Quantities quoted in a
letter about the documents (for example a LOI instruction that lists two B/Ls) can be compared with
other records such as the sailing report's cargo quantity, but that is not a check of the documents
themselves: say which it is. Keep the answer to the result and the gaps; the field-by-field table
goes in the details.
