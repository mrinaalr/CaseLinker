# Contributing to CaseLinker

Thanks for being here. CaseLinker turns public and collected data into structured, linkable knowledge for ICAC research, and it gets better when more people work on it. From typo fixes, to new tests, to proposals for whole new phases, every contribution makes CaseLinker better!

This file is everything you need to get started. For the day-to-day working process (conventions, tooling, agent workflows), see [AGENTS.md](AGENTS.md).

## Where to start

1. **Read the [README](README.md)** for what CaseLinker does and how to run it.
2. **Pick something** from the roadmap below, or open an issue describing what you want to work on.
3. **Consider saying hello in the issue** before starting anything large, so nobody duplicates effort.

> [!TIP]
> First contribution? Small is great. Documentation fixes, test coverage, and clearer error messages are all real contributions!

## Roadmap: where help is wanted

Phase 5 measures how faithfully CaseLinker's extracted fields and graphs represent their source records.

- **Data fidelity**: defining what a faithful extraction is, and detecting where output drifts from source
- **Extraction benchmarking**: building reproducible benchmarks so changes to extraction can be compared on evidence
- **Reporting**: making fidelity results easy to read and track over time
- **Graph validation loop**: checking generated graphs against source material, surfacing disagreements, and feeding the results back into processing
- **Stable case ids**: freezing the case-id map so ids no longer move when cases are re-ingested

**Further out:** treating the corpus as a temporal, heterogeneous network of cases, platforms, agencies, and locations to study how documented ICAC offending and enforcement evolve, including how platforms spread across cases and regions, which platforms and offenses form communities, and how network structure might inform intervention.

Not sure whether a task fits a phase? Open an issue and we will sort it out together.

## Other directions we are open to exploring

The roadmap is a compass, and a rough one at that. Ideas within CaseLinker are welcome, such as new collectors, better entity resolution, performance work, new views over the graph, or improvements to the developer / analyst experience. Ideas outside the roadmap are welcome too. If you have a direction that is interesting, rigorous, and useful to the field, open an issue and pitch it!

**Data beyond case reports?** Yes. CaseLinker starts from public case reports because anyone can access and verify them, and they record enough about each case (platforms, offenses, investigation and prosecution) to support cross-case analysis at scale. The same collect, extract and model pipeline could be applied to other ICAC data, such as forensic extractions from seized devices, peer-to-peer file-sharing measurements, cryptocurrency payment graphs or Tor onion-service crawls, but each new kind of data needs its own collection, extraction, and modeling in UCO, CASE and CAC, and their publication may carry adversarial risk (see [*Scaling*](https://mrinaalr.github.io/website/Scaling.pdf)). This repository and its human-subjects determination (UMass Amherst HRPO #7668) cover public case reports only, so work on other data would need its own ethics review and may not be publishable here. Open an issue to talk it through.

## How to contribute

- **Open an issue** for anything beyond a small fix, so the approach can be talked through first.
- **Fork the repo and branch from `main`**, and keep each pull request to one small, reviewable change.
- **Write commit messages that say what shipped**, with the PR reference, for example `Add fidelity check for entity links (#123)`.
- **Document testing in the PR**: what you ran and what you saw. The PR is the record other people click through to.
- **Match the existing style** of the code and docs around your change.
- **Or just wow us with a big PR**: If you have a new idea and would like us to take a look without the paperwork, feel free to open a PR directly. The review may take longer, but we are open to it.

## Forking and extending CaseLinker

CaseLinker is built for one challenge: collecting and analyzing public and collected data for ICAC research. The same architecture should be able to adapt well beyond it. The processing layer is where domain knowledge lives, so a fork can retune it for other fields, such as financial investigation, or be used to turn PDFs relating to business operations into interoperable knowledge graphs.

CaseNoesis is where we are exploring this more general direction: a broader extraction layer on the same ingestion, storage, analysis, and agent pipeline. If you want to turn your own data into graphs, the CASE-UCO SDK is a good place to start.

Forks are welcome and encouraged. Keep domain-specific work in your fork, and send improvements that help CaseLinker's ICAC research upstream. If you build something interesting, tell us about it!
