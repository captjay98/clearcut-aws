# ClearCut Deadline-Driven Delivery Plan

**Planning date:** 2026-08-30  
**Submission deadline:** 2026-09-09 14:00 Pacific

This is an aggressive contest schedule, not an estimate that guarantees completion. It assumes several implementation agents can work on contract-frozen, non-overlapping packets with human checkpoint review. Evidence integrity, tenant isolation, governance, and submission compliance are never waived to recover schedule.

## Critical path

```text
01a-c -> 02a-b -> 03a-b -> 04a -> 05a-c
-> 07a-b -> 08a-b -> 11a-b -> 12b
```

UI foundation, infrastructure, and later trust/monitoring work may prepare in parallel only at the seams declared in the packet index.

## Target calendar

| Pacific date | Required checkpoint | Parallel-safe work |
|---|---|---|
| Aug 30 | plans/contracts accepted; no implementation | organizer clarification request; cloud account/budget readiness |
| Aug 31 | R1: 01a–01c | 06a proof; 12a Terraform skeleton after contract paths freeze |
| Sep 1 | R2 identity/storage foundation: 02a–02c, 03a | 06b shell; CI/infrastructure |
| Sep 2 | R2 intake: 03b; R3 detection: 04a–04b | 02d/03c UI |
| Sep 3 | R3 evidence vertical slice: 05a–05c with mandatory live Search and bounded Extract trace | 06c; 07a contract preparation |
| Sep 4 | R5 review workflow: 07a–07d | hosted integration environment |
| Sep 5 | R6 revision loop: 08a–08c | 09a/10a contract preparation |
| Sep 6 | R7 monitoring/notifications/Records: 09a–09d, 10a; Monitor API only after recorded GO | 10b–10c where seams are frozen |
| Sep 7 | R8 report: 11a–11c; hosted golden path | recovery/security/accessibility passes |
| Sep 8 | release-candidate freeze; 12b demo recording and submission draft | fixes only against frozen evidence |
| Sep 9 | final exact-SHA verification and submit before 10:00 Pacific target | four-hour contingency buffer |

## Daily decision gates

At the end of each day record:

- completed packets and exact SHA;
- failing hard gates;
- provider/deployment evidence obtained;
- critical-path slip in hours;
- scope that is implemented, hidden as incomplete, or explicitly not claimed;
- next day's contract seams and assigned owner.

## Contingency rules

1. Never seed or invent provider evidence to make the demo pass.
2. Never enable an unfinished governed action or insecure cross-tenant route.
3. Prefer one complete live golden path over route shells that imply unavailable behavior.
4. Incomplete non-critical surfaces must be absent or explicitly labeled unavailable, not simulated as production.
5. Freeze provider/model/prompt/policy versions before the final demo rehearsal.
6. Record the demo once the deployed SHA passes; do not continue feature work on that candidate.
7. A missing Gemini/ADK call, mandatory Parallel Search call, public repository/license, hosted URL, or compliant video is a submission blocker. Extract and Monitor are claimed only when their exact deployed evidence exists.

## Human ownership

Each packet and checkpoint needs one named accountable owner in its evidence file. Multiple agents may contribute, but ownership cannot be “the team.” Governed workflow acceptance must include a second human actor for maker/checker proof.
