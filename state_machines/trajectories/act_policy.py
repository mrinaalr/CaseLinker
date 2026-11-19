"""The act-selection policy a machine release publishes.

``intersection-1.0`` publishes an act only when both pinned coders cite the
same sentence, the same action code, and the same actor. An act only one coder
proposed, and a sentence the two coded differently, stays out of the published
bundle. Those disagreements are counted. They are not turned into agreement.

This is the policy of ``pacer-v1``. Agreement is not treated as truth, and the
policy is not a recall measurement. Coder A alone, the union of the two coders,
and cue-settled action codes (resolve rule 2b) are not this policy. A different
policy is a different release.
"""

POLICY_ID = "intersection-1.0"
