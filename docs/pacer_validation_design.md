# Validation design for the PACER coding study

This note is the methods record for the pre-registered validation of act and means coding. It states each design choice and the reason for it. It does not report measurements from any court corpus. The numbers that belong in the paper are produced later, from the sealed sample, after the manifest hash is fixed.

## Seal the split before tuning

The first command a researcher runs on the real corpus is a seal, not a tuning loop. The seal takes the corpus case ids, an exclusion list, a seed, and two sizes: a held-out case split, and a gold-sample frame. Those values live in a config file. The copy in the repository is blank, so the committed code does not contain a draw.

Eligible cases are the corpus with the exclusion list removed. Held-out cases are a simple random sample of the eligible list. The gold frame is a simple random sample of what remains, so the two sets do not overlap. The manifest stores the seed, both sizes, the population counts (corpus, excluded, eligible, held out, gold frame, and the remainder, which is the development set), the code version, and a SHA-256 of that body. The same inputs produce the same file.

The reason to seal first is that a sample chosen after looking at errors is no longer a probability sample. Any later change to a coder, a lexicon, or a prompt is then a change made in sight of the cases on which it will be scored. The seal makes the held-out cases and the gold frame a fixed list with a hash. Development and tuning entry points, including extraction debug and benchmark scoring, refuse to load a sealed case id. The only way through is an explicit final-evaluation flag together with that hash. A manifest whose stored hash does not match its body is rejected before any id is used.

The exclusion list is where the pilot cases go. Those cases were used to see how the rules behaved. They are not part of the eligible population, and the sampler will not draw them even if a later step asks for more cases than the eligible set contains. The list is filled by the researcher in the config. It is not hardcoded.

## Tune on extraction errors, and not on the hypothesis

What a developer may inspect on the development cases is whether the coding recovered the act, the actor, and the means the sentence states. That is an extraction question: given a sentence, did the pipeline mark what the sentence says.

What a developer may not inspect, on the sealed cases or as a reason to change a rule, is the scientific hypothesis the corpus is meant to answer. A rule changed because it raised or lowered a co-occurrence between a platform feature and a harm has been fit to the outcome. The validation would then measure the fitted rule. Extraction errors are the allowed feedback. Hypothesis outcomes are not.

## Stratified sample with known inclusion probabilities

Inside the sealed gold frame, the human sample is a stratified simple random sample of sentences. The strata, the size of each, and the seed come from a config the researcher fills from the same pre-registration. The strata exist so that rare sentences are not left to a simple random draw that might miss them. Typical hit strata are sentences with a published act and sentences where a means is tied to an act. Typical uncoded strata are sentences where the means rule fires and no act is tied, and the remaining sentences. The sizes are chosen in the config. The code does not choose them, and it does not prefer a sentence because a model was uncertain about it or because it looked interesting. A field of that kind on a row is ignored.

For a unit in stratum h the inclusion probability is pi_h = n_h / N_h, where N_h is the number of units in the stratum inside the frame and n_h is the number drawn. Every drawn row stores N_h, n_h, and pi_h. The sampling weight used below is N_h / n_h, the inverse of the inclusion probability. Before any grading, the drawn list is hashed. The hash covers the unit id, the stratum, and the inclusion probability. It does not cover a human label, because none exists yet.

## Recall is a Horvitz-Thompson ratio

Recall is a property of the population of gold-positive units, not of the sample alone. A sentence the design oversampled would otherwise pull the sample recall toward that stratum. The estimator is the Horvitz-Thompson estimator of the number of true positives, divided by the Horvitz-Thompson estimator of the number of gold-positive units:

```
recall = sum_i (w_i * hit_i) / sum_i (w_i * gold_i)
```

w_i is N_h / n_h for the unit's stratum, hit_i is 1 when the machine and the gold agree that the unit is positive, and gold_i is 1 when the gold says it is positive. For an act, positive means a stated action code. For a means tie and for level C, positive means the boolean the sheet records. The same weights, averaged over every sample the design can draw, recover the population totals, and therefore the population recall. That is the check the tests run on a synthetic population. The interval is a percentile bootstrap that resamples inside each stratum at the stratum's drawn size, so the resample respects the design.

The estimator is the one in Horvitz and Thompson (1952): an unbiased estimator of a population total under a design with known inclusion probabilities, formed by weighting each sampled unit by the inverse of its inclusion probability.

## Precision is per stated unit

Precision is reported separately for each stated unit: an act (the action code the machine emitted), a means tie, and level C. A unit enters the precision denominator when the machine stated it. The numerator is the number of those statements the gold confirms. The ratio is unweighted. The sample of machine statements is what precision describes, and the Wilson interval (Wilson 1927) is the interval on that proportion. Wilson's interval is used because the counts of rare statements are small, and the normal approximation is a poor interval for a proportion near 0 or 1 in a small sample.

## The validation mode stays independent

The published validation acts are those `intersection-1.0` would publish: both coders cited the same sentence, the same action code, and the same actor, and neither coder saw the other coder's answer. Independence is the point of a reliability sample. A production mode in which the second coder accepts or corrects the first coder's frames is a different procedure. It can be used to build a release a researcher has decided to build. It is not the mode of the validation sample, and the manifest of a validation run names `intersection-1.0`.

## The grading sheet is blind

The sheet a human grades contains the sentence and about two sentences of context on either side. It does not contain a whole filing, and it does not contain the machine's act, means, level, or stratum. Those fields are written to a separate key. The grader cannot anchor a judgment to the machine label, because the label is not on the page. Scoring joins the sheet back to the key by unit id after the grades exist.

## A second coder, alpha, and a bootstrap interval

At least two people grade the sheet, independently, under the same instructions. Agreement across those coders is reported as Krippendorff's nominal alpha and, for a pair of coders, Cohen's kappa.

Alpha is computed from the coincidence matrix. For each unit, pairs of the values the coders assigned contribute to the observed coincidence; a missing value on a unit is left out, and a unit with fewer than two values does not enter. Observed disagreement is the off-diagonal mass of that matrix. Expected disagreement is the disagreement implied by the category totals. Alpha is 1 minus the ratio of the two. When the coders agree perfectly, observed disagreement is 0 and alpha is 1. The definition follows Krippendorff's computing note (Krippendorff 2011). Alpha is the coefficient that accepts any number of coders and missing cells. Kappa is the two-coder coefficient: observed agreement corrected by the agreement expected from each coder's own marginals (Cohen 1960). The two answer different questions. Both are reported. Kappa is undefined when the coders use only one category, because the chance term is then 1.

The interval on alpha, and the interval on kappa, is a percentile bootstrap over units. Artstein and Poesio (2008), reporting Krippendorff's recommendation, note that the sampling distribution of alpha is not treated as a simple closed form, and that the interval is obtained by bootstrapping. Rare categories are exactly where a normal interval would be least trustworthy, so the bootstrap is the interval this design uses. The bootstrap seed is fixed and the number of replicates is recorded with the score.

## Rows ready for DSL or prediction-powered inference

The machine labels are a surrogate. The human grades are the gold on a probability sample. Two published procedures turn that pair into a corrected estimate, and this design stops at handing them the inputs they require.

Design-based supervised learning (Egami, Hinck, Stewart, and Wei, NeurIPS 2023) combines surrogate labels with gold labels on a sample whose inclusion probabilities are known. The paper's sampling assumption is that those probabilities are known and bounded away from zero, which is the stratified design above: pi_h = n_h / N_h is computed from the stratum sizes, not estimated. Prediction-powered inference (Angelopoulos, Bates, Fannjiang, Jordan, and Zrnic, Science 2023) uses a small gold set to correct a quantity estimated from abundant machine predictions, without an assumption about how the predictions were made. Both need the gold label, the machine label, and the sampling probability of each labeled unit. The scorer writes one row per labeled unit with those fields and the weight N_h / n_h. It does not itself compute a DSL or prediction-powered estimate. That computation is a later, separate step, on the sealed hash.

## Evidence levels stay separate

Four claims are easy to collapse and are kept apart.

A mention is the record naming a platform or stating a feature phrase. It is not a claim that anyone used it.

An act is the claim that someone did something. Under the validation mode, it is in the published set only when the two independent coders agree on the sentence, the action, and the actor.

A same-sentence means is the claim that the act's own sentence states the platform or the feature as the means. Level C, in the codebook's sense, is narrower still: a platform name is never a level-C affordance. Level C is a feature the sentence states as the means of the act.

An adjacent-sentence link is a different claim. It says that a later sentence uses an explicit anaphor ("that account", "he") whose antecedent is in the sentence before it. It carries its own label, `adjacent-sentence`, and it is stored in its own list. It is not written into the level-C list. A means the act's own sentence did not state is not level C, and merging the two would make the level-C count include ties the sentence did not make. The flag that produces adjacent links defaults off. With it off, the list is empty.

## References

Angelopoulos, Anastasios N., Stephen Bates, Clara Fannjiang, Michael I. Jordan, and Tijana Zrnic. 2023. "Prediction-Powered Inference." *Science* 382 (6671): 669–674. Published 10 November 2023. https://doi.org/10.1126/science.adi6000

Artstein, Ron, and Massimo Poesio. 2008. "Inter-Coder Agreement for Computational Linguistics." *Computational Linguistics* 34 (4). https://aclanthology.org/J08-4004/

Cohen, Jacob. 1960. "A Coefficient of Agreement for Nominal Scales." *Educational and Psychological Measurement*. First published April 1960. https://doi.org/10.1177/001316446002000104

Egami, Naoki, Musashi Hinck, Brandon M. Stewart, and Hanying Wei. 2023. "Using Imperfect Surrogates for Downstream Inference: Design-based Supervised Learning for Social Science Applications of Large Language Models." 37th Conference on Neural Information Processing Systems (NeurIPS 2023). https://proceedings.neurips.cc/paper_files/paper/2023/hash/d862f7f5445255090de13b825b880d59-Abstract-Conference.html

Horvitz, D. G., and D. J. Thompson. 1952. "A Generalization of Sampling Without Replacement from a Finite Universe." *Journal of the American Statistical Association* 47 (260): 663–685. https://doi.org/10.1080/01621459.1952.10483446

Krippendorff, Klaus. 2011. "Computing Krippendorff's Alpha-Reliability." University of Pennsylvania, Annenberg School for Communication. Dated 2011.1.25; literature note updated 2013.9.13. https://www.asc.upenn.edu/sites/default/files/2021-03/Computing%20Krippendorff%27s%20Alpha-Reliability.pdf

Wilson, Edwin B. 1927. "Probable Inference, the Law of Succession, and Statistical Inference." *Journal of the American Statistical Association* 22 (158): 209–212. https://doi.org/10.1080/01621459.1927.10502953
