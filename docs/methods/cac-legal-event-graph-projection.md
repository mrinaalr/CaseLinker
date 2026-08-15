# CAC legal-event graph projection method

## Inputs

One immutable legal-event resolution bundle:

- one `caselinker:subjectOfLegalEvent` assertion;
- one `caselinker:legalEventType` assertion;
- zero or one `caselinker:eventDate` assertion;
- a reader for the current review decision governing every extraction input.

## Preconditions

Every member must be affirmed, resolved, live-eligible for research publication, and
identical in input lineage, review lineage, resolution method, run, and code revision.
The subject relation identifies the event entity; type and date describe that entity.

## Mapping profile

| Procedural value | Conservative CAC class |
|---|---|
| `legal_event_arrest` | `cac:LegalProcessPhase` |
| `legal_event_charge` | `cac-legal:CriminalCharge` |
| `legal_event_indictment` | `cac:LegalProcessPhase` |
| `legal_event_guilty_plea` | `cac-legal:PleaBargaining` |
| `legal_event_conviction` | `cac-legal:LegalProceeding` |
| `legal_event_sentencing` | `cac-legal:SentencingHearing` |

The broader class never replaces the exact procedural value. Both are emitted.

## Determinism

The graph contains no blank nodes, ambient timestamps, display labels, or filesystem
paths. Triples are rendered in lexical N-Triples order with exactly one terminal line
feed. SHA-256 identifies those bytes. Equivalent input ordering therefore produces the
same artifact identity.

## Validation

`schemas/rdf/cac-legal-event-projection-v1.shacl.ttl` requires one attributed subject,
one named projection profile, one event type, no more than one typed date, two or three
resolved provenance nodes, and resolution-run metadata. The validator receives the
shapes graph explicitly, uses no inference or network access, and returns the exact
projection and canonical-shapes digests alongside its report digest.

SHACL conformance is necessary but insufficient for research publication. Callers must
retain the policy result and still apply disclosure, privacy, authorization, cohort,
and claim-governance controls appropriate to the output.

## Reproduction

Re-run the projector against the same assertion ledger and current review state. Match
the canonical byte digest, then run the pinned SHACL profile. If review state changed,
the historical resolution correctly becomes ineligible rather than being regenerated
as though nothing changed.
