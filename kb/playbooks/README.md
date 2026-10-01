# Playbooks

One file per operator procedure (docs/design_agent_e16_v7.md, section 7). The file name is the id.
Header (YAML): `id`, `title`, `when` (one line the router reads), `mode` (the execution mode the system applies when it is chosen: evidence_reasoning, proposal_reasoning, domain_knowledge or hybrid), `status` (`draft` until the owner has
reviewed the file, then `approved`), `source` (who wrote it and when), `requires` (evidence needed),
`steps` (`id`, `primitive`, `text`). Primitives: Select, Extract, Detect, Compare, Transform,
Generate (E nodes), Allocation, Ranking (D nodes). The body is guidance and an email template.

Only `approved` playbooks reach the assistant. For a review run set `E16_INCLUDE_DRAFT_PLAYBOOKS=1`;
answers then show "(draft)". The service refuses to start if a file is invalid.
