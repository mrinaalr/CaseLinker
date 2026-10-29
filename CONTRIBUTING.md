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

### Phase 4: Ontology expansion, grounding, and the graph validation loop

Phase 4 widens what CaseLinker can represent and tightens how the graph is checked against its sources.

- **Ontology expansion**: extending coverage of entities, relationships, and case structures with CASE/UCO-aligned classes
- **Grounding**: tying every node and edge back to the evidence it came from
- **Graph validation loop**: checking generated graphs against source material, surfacing disagreements, and feeding the results back into processing

### Phase 5: Data fidelity and extraction benchmarking

Phase 5 measures how faithfully CaseLinker turns raw material into structure.

- **Data fidelity**: defining what a faithful extraction is, and detecting where output drifts from source
- **Extraction benchmarking**: building reproducible benchmarks so changes to extraction can be compared on evidence
- **Reporting**: making fidelity results easy to read and track over time

Not sure whether a task fits a phase? Open an issue and we will sort it out together.

## Other directions we are open to exploring

The roadmap is a compass, and a rough one at that. Ideas within CaseLinker are welcome, such as new collectors, better entity resolution, performance work, new views over the graph, or improvements to the developer / analyst experience. Ideas outside the roadmap are welcome too. If you have a direction that is interesting, rigorous, and useful to the field, open an issue and pitch it!

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
