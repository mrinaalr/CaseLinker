# Security Policy

CaseLinker processes public records concerning crimes against children. Even
when source records are public, misuse, aggregation, or careless disclosure can
create serious safety and privacy harm. Security reports must minimize the
reproduction and redistribution of case content.

## Supported work

This proposal branch is pre-release research software. It does not currently
represent an official supported CaseLinker release. Security fixes target the
latest commit on the active proposal branch and should be coordinated with the
upstream maintainer when upstream code or deployments are affected.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting or Security Advisory workflow for
the affected repository. If private reporting is unavailable, contact the
repository owner without opening a public issue containing exploit details.

Include:

- the affected commit and component;
- a minimal reproduction using synthetic data;
- impact and likely abuse path;
- suggested mitigation, if known;
- whether the issue affects the upstream deployment.

Do **not** include source PDFs, illegal material, victim-identifying details,
credentials, production tokens, or unnecessary excerpts from case records.
Synthetic fixtures are required whenever they can demonstrate the issue.

## High-priority classes

- unauthorized access to source text, notes, exports, or administrative routes;
- bypass of cohort, field-level, or bulk-export policy controls;
- prompt injection or model egress that exposes restricted content;
- cache-key, tenant, or snapshot confusion that returns another policy context;
- provenance tampering or a claim linked to the wrong evidence;
- stored or reflected injection through case records or community-authored text;
- secret exposure, unsafe deserialization, path traversal, and dependency
  compromise;
- denial-of-service paths affecting ingestion, graph generation, cohort queries,
  or model endpoints.

## Disclosure expectations

Please allow maintainers time to reproduce, contain, fix, and coordinate before
public disclosure. This policy does not authorize access to systems or data
beyond what the reporter already has permission to use.
