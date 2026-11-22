# Gold sample

How an evaluation set is recorded, how a sentence sample is drawn, and how that sample is scored. The commands are [`seal.py`](seal.py) and [`gold_sample.py`](gold_sample.py). Neither reads page text. Neither writes into `state_machines/data/`, `local/` or `caselinker_oxigraph/`.

**Contents:**

- [Seal](#seal)
- [What tuning may use](#what-tuning-may-use)
- [Stratified draw](#stratified-draw)
- [Recall](#recall)
- [Precision](#precision)
- [Validation mode](#validation-mode)
- [Blind sheet](#blind-sheet)
- [Agreement](#agreement)
- [Rows for a design-based correction](#rows-for-a-design-based-correction)
- [Levels kept apart](#levels-kept-apart)
- [References](#references)

## Seal

```bash
python -m state_machines.observations.seal --config <config.json> --out <dir>
```

[`seal_config.json`](seal_config.json) is blank: no corpus ids, no excluded ids, no seed, no sizes. The command refuses a blank config. Fill it, then run the command once.

A simple random split is one way to choose the evaluation set. Eligible ids are the corpus with the exclusion list removed. Held-out cases are a simple random sample of that list. The gold frame is a simple random sample of what remains, so the two sets do not overlap. An excluded id is not eligible. If the two sizes ask for more cases than remain, the command stops and writes nothing.

An evaluation set may also be fixed by a pre-declared label rule, for example every case in a folder. The corpus list and the exclusion list record that set: the ids the rule keeps go in the corpus, and the rest go on the exclusion list. The draw then runs inside the recorded set.

The manifest records the seed, both sizes, the population counts (corpus, excluded, eligible, held out, gold frame, and the remainder), the code version, and a SHA-256 of that body. The same inputs produce the same file. The digest is checked before any later command uses the ids. A file whose stored digest is not the hash of its body is rejected.

## What tuning may use

Development loading, extraction debug, and `python -m state_machines.benchmark.score --sealed-manifest` refuse a sealed case id. The way through is `--final-evaluation` together with the manifest hash. Without the manifest flag, benchmark scoring is unchanged.

What may be inspected on the development cases is whether the coding recovered the act, the actor, and the means the sentence states. The sealed cases are not an input to a rule change. A rule changed because of a count on the sealed cases is no longer measured by that sample.

## Stratified draw

```bash
python -m state_machines.observations.gold_sample draw --population <units.json> --config <strata.json> --sealed <sealed_manifest.json> --out <dir>
```

Inside the gold frame, the human sample is a stratified simple random sample of sentences. Stratum names, sizes and the seed come from the config. A unit whose case is outside the frame is refused. A unit whose case is on the exclusion list is refused. A field such as model uncertainty is not read.

`population_from_case` labels a sentence `machine_positive` when it names a listed platform or a level-C feature, and `other` otherwise. The stamp `published_acts` is not a stratum and not a filter. A config `{"take_all": "machine_positive", "fill": "other", "total": N, "seed": ...}` draws every machine-positive sentence and fills the rest of `N` from `other`, so a small machine-positive stratum does not stop the draw. Machine labels are not on the grading sheet.

For a unit in stratum h the inclusion probability is `n_h / N_h`. `N_h` is the number of units of that stratum in the frame. `n_h` is the number drawn. Every drawn row stores `N_h`, `n_h` and the probability. The sampling weight is `N_h / n_h`.

Before the grading sheet is written, the drawn list is hashed. The hash covers the unit id, the stratum and the inclusion probability.

## Recall

Recall is a property of the gold-positive units in the frame. A stratum that was drawn more heavily would otherwise pull an unweighted ratio toward itself. The estimator weights each sampled unit by `N_h / n_h`:

```
sum (weight * hit) / sum (weight * gold)
```

`hit` is 1 when the machine and the gold agree that the unit is positive. `gold` is 1 when the gold says it is positive. For an act, positive means a stated action code. For a means tie and for level C, positive means the boolean on the sheet. The same weights, averaged over every sample the design can draw, recover the population totals. That check is a synthetic test. The interval is a case bootstrap. The unit of resampling is the case: cases are drawn with replacement from all cases in the frame, and every sentence of a drawn case comes along in every stratum it has rows in. Rows that share a court and a case number are one case before the draw, and a later document with the same sha256 is dropped whole. Each row keeps its weight `N_h / n_h`. Sentences are not drawn on their own. The default number of replicates is 2,000.

The score reports the number of gold positives in each stratum next to the recall and its interval. A stratum with fewer than 5 gold positives carries a warning that its bootstrap interval is unreliable.

This is the Horvitz–Thompson estimator of a total: each sampled unit is weighted by the inverse of its inclusion probability (Horvitz and Thompson 1952).

## Precision

Precision uses the same weights. A stratum drawn more heavily would otherwise pull an unweighted ratio toward itself. For each stated unit (an act, a means tie, level C):

```
sum_h (weight_h * TP_h) / sum_h (weight_h * (TP_h + FP_h))
```

`weight_h` is `N_h / n_h`. A unit enters when the machine stated it. `TP` is a statement the gold confirms. The interval is the same case bootstrap as recall: cases are drawn with replacement from the whole frame, and a drawn case brings every one of its rows. Each stratum also has its own Wilson interval (Wilson 1927) on its count of statements.

## Validation mode

The acts a validation sample treats as published are those `intersection-1.0` publishes: both coders cited the same sentence, the same action code and the same actor, and neither saw the other's answer. A mode in which the second coder accepts or corrects the first coder's frames is a separate procedure. It is selected with `CASELINKER_ACT_POLICY=propose-verify-1.0`, which defaults off. It is not the mode of this sample.

## Blind sheet

The sheet contains the sentence and at most two sentences of context on either side. It does not contain a whole filing. It does not contain the machine's act, means, level or stratum. Those fields are in a separate key. Scoring joins the sheet to the key by unit id.

## Agreement

The agreement step is optional. By default one grader marks the sheet, and no agreement figure is reported. Krippendorff's nominal alpha (Hayes and Krippendorff 2007) and Cohen's kappa are computed and reported only when a second grader's marks are supplied. They are computed on the rows both graders marked.

Alpha uses the coincidence matrix. Pairs of values on a unit contribute to the observed coincidence. A missing value is left out. A unit with fewer than two values does not enter. Observed disagreement is the off-diagonal mass. Expected disagreement is the disagreement implied by the category totals. Alpha is 1 minus the ratio. Perfect agreement, observed disagreement 0, is alpha 1. Alpha takes any number of coders and missing cells.

Kappa is the two-coder coefficient: observed agreement corrected by the agreement expected from each coder's own marginals. It is undefined when both coders use only one category, because the chance term is then 1. When a second grader's marks are supplied, both coefficients are reported.

The interval on each is the same case bootstrap. Cases are drawn with replacement from all cases in the frame, and a drawn case brings every sentence it has. The bootstrap seed and the number of replicates are stored with the score.

## Rows for a design-based correction

The machine labels are a surrogate. The human grades are the gold on a sample whose inclusion probabilities are known. This module writes the rows for a design-based correction and does not run that correction.

Design-based supervised learning (Egami, Hinck, Stewart and Wei 2023) combines surrogate labels with gold labels on a sample whose inclusion probabilities are known and bounded away from zero. Here `n_h / N_h` is computed from the stratum sizes. The score file has one row per labeled unit with the gold label, the machine label, the sampling probability, and the weight `N_h / n_h`.

## Levels kept apart

Four claims stay in separate fields.

A mention is the record naming a platform or stating a feature phrase. It does not say that anyone used it.

An act says that someone did something. In the validation mode it is published only when the two coders agree on the sentence, the action and the actor.

A same-sentence means says that the act's own sentence states the platform or the feature as the means. The means slot is the instrument of the act. Level C is a feature the sentence states as that instrument. A platform name is not a level-C affordance (codebook rule B0).

An adjacent-sentence link says that a later sentence has an explicit anaphor ("that account", "he") whose antecedent is in the sentence before it. It is labelled `adjacent-sentence` and stored in its own list. It is not copied into the level-C list. `CASELINKER_ADJACENT_LEVEL` defaults off. With it off, the list is empty.

## References

Egami, Naoki, Musashi Hinck, Brandon M. Stewart, and Hanying Wei (2023). Using Imperfect Surrogates for Downstream Inference: Design-based Supervised Learning for Social Science Applications of Large Language Models. In *Advances in Neural Information Processing Systems* 36. NeurIPS 2023. Also arXiv:2306.04746. https://proceedings.neurips.cc/paper_files/paper/2023/hash/d862f7f5445255090de13b825b880d59-Abstract-Conference.html

Hayes, Andrew F. and Klaus Krippendorff (2007). Answering the Call for a Standard Reliability Measure for Coding Data. *Communication Methods and Measures* 1(1), 77–89. https://doi.org/10.1080/19312450709336664

Horvitz, D. G. and D. J. Thompson (1952). A Generalization of Sampling Without Replacement from a Finite Universe. *Journal of the American Statistical Association* 47(260), 663–685. https://doi.org/10.1080/01621459.1952.10483446

Wilson, Edwin B. (1927). Probable Inference, the Law of Succession, and Statistical Inference. *Journal of the American Statistical Association* 22(158), 209–212. https://doi.org/10.1080/01621459.1927.10502953
