"""Codebook cue words per action code: a deterministic third reading of an act's sentence.

A rule that was evaluated and not adopted; off by default (``resolve(..., settle_codes=True)``, ``pipeline --settle-codes``).
Where both model coders cite the same sentence as an act and name the same actor but give it
different action codes, the sentence is read against this table. If it carries a cue for exactly
one of the two codes, that code is taken; in every other case (no cue, cues for both, a code with
no entry) the act stays unpublished. The table never adds an act, never changes an actor and never
proposes a third code.

Why it is not part of a machine release: a machine release states that two independent coders
agreed on everything published, and a settled code is one coder's code confirmed by a word rule.
On the synthetic benchmark the rule recovers acts at no cost in precision; on five real cases
coded earlier by hand-checked pilot coders, settled codes matched the pilot's code for the same
sentence less often than codes both models gave (numbers in the release REPORT). Real sentences
are long and often state several acts, so each coder may have coded a different one. The rule is
kept so the measurement can be repeated.

The cues restate the codebook's definitions (``coder._DEF``) as the words filings use for them.
Residual codes (``RESIDUAL``) are defined by the codebook as "not coded more specifically", so
they hold no cues and yield to a specific code the sentence cues.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Set

CUE_VERSION = "cues-1.0.0"
RESIDUAL = {"COMMUNICATE", "OTHER_OFFENDER_ACTION", "PROC_OTHER"}

_IMG = r"(?:images?|photos?|photographs?|pictures?|videos?|depictions?|nudes?|files?|recordings?)"
_ASK = r"(?:ask|request|told|tell|instruct|direct|demand|persuad|induc|entic|coerc|urg|solicit|order|command|pressur)\w*"

_CUES: Dict[str, str] = {
    "SEEK_TARGETS": r"\b(?:search(?:ed|ing)? for|look(?:ed|ing) for|brows(?:ed|ing))\b|\bpost\w*\b[^.]*\b(?:seeking|looking for|asking|wanted)\b|\bpublic post\b",
    "INITIATE_CONTACT": r"\bfirst (?:contact\w*|messag\w*|communicat\w*|met|conversation|wrote)\b|\binitiat\w+ (?:contact|a conversation|communications?)\b"
                        r"|\bbegan (?:communicating|chatting|messaging|talking|corresponding)\b|\bintroduced himself\b|\bstruck up\b",
    "ACQUIRE_REPRESENTATION": r"\b(?:obtain|collect|gather|learn|sav|screenshot|cop)\w*\b[^.]*\b(?:profile (?:photo|picture)s?|photos? of|pictures? of|home address|school|full name|personal information|identifying information)\b",
    "ACQUIRE_MATERIAL": r"\bdownload\w*\b|\b(?:receiv|obtain|purchas|bought|acquir)\w*\b[^.]*\b(?:child pornography|child sexual abuse material|CSAM)\b",
    "MISREPRESENT_IDENTITY": r"\bfalsely\b|\bpretend\w*\b|\bpos(?:ed|ing) as\b|\bpurport\w* to be\b|\bclaim\w* to be\b|\bnot true\b|\blied about\b"
                             r"|\bfake (?:name|age|identity|profile|persona)\b|\bfalse (?:name|age|identity)\b|\bmisrepresent\w*\b",
    "BUILD_RAPPORT": r"\bcompliment\w*|\bflatter\w*|\bgifts?\b|\bbefriend\w*|\b(?:gain|earn|won)\w* (?:her|his|their|\S+ \S+ \d+'s) trust\b|\bboyfriend\b|\bgirlfriend\b",
    "OFFER_INDUCEMENT": r"\boffer\w*\b[^.]*\b(?:money|pay|cash|gift cards?|drugs|alcohol|\$\d)|\bin exchange for\b|\bpromis\w+ to (?:pay|buy|give)\b",
    "SEXUALIZE_COMMUNICATION": r"\bsexual(?:ly explicit)? (?:conversations?|messages?|chats?|comments?|topics?|questions?)\b|\b(?:image|photo|picture|video)s? of his (?:penis|genitals)\b|\babout sex\b",
    "SOLICIT_IMAGERY": rf"\b{_ASK}\b[^.]*\bto (?:send|take|produce|create|make|record|transmit|provide)\b[^.]*\b{_IMG}\b"
                       rf"|\b(?:ask|request|demand|solicit)\w*\b[^.]*\b(?:for|that)\b[^.]*\b{_IMG}\b",
    "DIRECT_CONDUCT": rf"\b{_ASK}\b[^.]*\bto (?:engage in|perform|touch|masturbate|pose|undress|insert|remove (?:her|his))\b",
    "THREATEN_EXPOSURE": r"\bthreat\w*\b[^.]*\b(?:send|share|post|publish|release|distribute|expose|show|forward|leak)\w*\b|\bsextort\w*",
    "THREATEN_HARM": r"\bthreat\w*\b[^.]*\b(?:kill|hurt|harm|rape|beat|shoot|injur\w*|violence)\b",
    "DIRECT_VICTIM_TO_RECRUIT": r"\brecruit\w*\b|\b(?:bring|involve|introduce|include)\b[^.]*\b(?:friends?|sister|brother|sibling|other (?:girls|boys|minors|children))\b",
    "MOVE_CHANNEL": r"\b(?:mov|switch|migrat|transition|shift)\w*\b[^.]*\b(?:conversations?|chats?|communications?|discussions?)\b[^.]*\b(?:to|onto)\b"
                    r"|\bcontinu\w*\b[^.]*\b(?:conversations?|chats?|communications?|talking|communicating|discussions?)\b[^.]*\b(?:on|over|through|via)\b",
    "RECREATE_ACCOUNT": r"\b(?:creat|made|make|open|set up|register|establish)\w*\b[^.]*\b(?:new|another|second|different|additional) (?:\w+ )?(?:account|profile)\b",
    "RECONTACT": r"\bre-?contact\w*\b|\bresum\w+ (?:contact|communicat\w+|messaging)\b|\b(?:contacted|messaged|wrote to)\b[^.]*\bagain\b",
    "RECEIVE_SELF_GENERATED": rf"\b(?:sent|send|transmitted|provided|forwarded)\b[^.]*\b(?:the defendant|defendant|him)\b[^.]*\b{_IMG}\b"
                              rf"|\breceiv\w*\b[^.]*\b{_IMG}\b[^.]*\bfrom\b|\b(?:of herself|of himself|self-produced|self-generated)\b|\bas (?:he|defendant|the defendant) (?:had )?(?:asked|requested|directed|instructed)\b",
    "RECORD_LIVE_SESSION": r"\b(?:record|screen-?record|captur|screenshot)\w*\b[^.]*\b(?:live|video (?:calls?|chats?)|livestream\w*|stream\w*|webcam|session)\b",
    "PRODUCE_IN_PERSON": r"\b(?:filmed|photographed|videotaped|video-?recorded|took (?:photos|photographs|pictures|videos?) of)\b",
    "SYNTHESIZE_OR_ALTER_IMAGERY": r"\bartificial intelligence\b|\bAI[- ]generated\b|\bmorph\w*|\bdeepfake\w*|\bdigitally (?:alter|creat|manipulat)\w*|\bface-?swap\w*",
    "STORE_MATERIAL": r"\b(?:stored|saved|kept|retained|maintained|possessed)\b",
    "ORGANIZE_MATERIAL": r"\b(?:organiz|catalogu|categoriz)\w*|\bsorted\b|\bfolders?\b",
    "DISTRIBUTE_MATERIAL": r"\b(?:distribut\w*|shared|sent|posted|uploaded|traded|forwarded|transmitted)\b[^.]*\b(?:to|with|in|among)\b[^.]*\b(?:others?|users|members|groups?|individuals?|persons?|people|another)\b",
    "ADVERTISE_MATERIAL_OR_ACCESS": r"\badvertis\w*|\boffer\w* to (?:sell|trade)\b|\bfor sale\b",
    "EXPOSE_TO_VICTIM_NETWORK": r"\b(?:sent|shared|posted|forwarded|distributed)\b[^.]*\b(?:friends|family|followers|classmates|parents|mother|father|relatives|contacts)\b",
    "ADMINISTER_SPACE": r"\b(?:administ\w*|moderat\w*|created|ran|operated|managed|founded)\b[^.]*\b(?:groups?|servers?|sites?|websites?|channels?|forums?|chat ?rooms?|boards?)\b",
    "GATEKEEP_MEMBERSHIP": r"\b(?:vet\w*|admit\w*|approv\w*|verif\w*)\b[^.]*\bmembers?\b|\bmembership\b",
    "SET_RULES": r"\brules?\b|\bquotas?\b",
    "ASSIGN_ROLE": r"\b(?:promot\w*|rank\w*|appointed|assigned)\b",
    "COORDINATE_CO_OFFENDERS": r"\b(?:conspir\w*|coordinat\w*|planned with|agreed with|together with)\b",
    "SHARE_TRADECRAFT": r"\b(?:advis\w*|instruct\w*|taught|explain\w*|tips?)\b[^.]*\b(?:avoid|evad|hid|conceal|detect|encrypt)\w*",
    "PAY_THIRD_PARTY": r"\b(?:paid|payments?|sent money|wired|transferred)\b",
    "ARRANGE_MEETING": r"\b(?:arrang\w*|plann\w*|agreed|set up|schedul\w*|made plans|propos\w*)\b[^.]*\b(?:meet|meeting|in person|pick (?:her|him) up)\b",
    "TRAVEL_TO_MEET": r"\b(?:travel\w*|drove|driving|flew|arrived|took a (?:bus|train|flight))\b",
    "IN_PERSON_SEXUAL_ABUSE": r"\bsexual(?:ly)? (?:abus|assault|intercourse|contact|act)\w*|\bengaged in (?:sexual|sex)\b|\bhad sex\b|\brap(?:ed|ing)\b|\bmolest\w*",
    "ADVERTISE_COMMERCIAL_SEX": r"\b(?:advertis\w*|posted (?:an )?ads?)\b[^.]*\b(?:commercial sex|escort\w*|prostitut\w*)\b",
    "ARRANGE_COMMERCIAL_SEX": r"\b(?:book\w*|transport\w*|drove|arranged)\b[^.]*\b(?:commercial sex|customers?|clients?|buyers?|prostitut\w*)\b",
    "COLLECT_PROCEEDS": r"\b(?:collect\w*|kept|took)\b[^.]*\b(?:proceeds|money|earnings|payments?)\b",
    "CONTROL_VICTIM": r"\b(?:confiscat\w*|harbor\w*|withheld|locked)\b|\btook (?:her|his) (?:phone|identification)\b",
    "CONCEAL_OR_DESTROY_EVIDENCE": r"\b(?:delet\w*|destroy\w*|wip(?:ed|ing)|discard\w*|eras\w*)\b|\bfactory reset\b|\bthrew away\b",
    "EVADE_DETECTION": r"\b(?:avoid|evad)\w*\b[^.]*\b(?:detect\w*|law enforcement|police|caught)\b",
    "OBSTRUCT_OR_TAMPER": r"\b(?:tamper\w*|obstruct\w*)\b|\bnot to (?:tell|talk to|cooperate)\b|\bto lie\b",
    "FLEE": r"\b(?:fled|flee\w*|absconded)\b",
    "RESP_REFUSE": r"\b(?:refus\w*|declin\w*|said no|would not|did not (?:send|comply|agree))\b",
    "RESP_BLOCK": r"\bblock\w*|\bstopped responding\b|\bunfriended\b",
    "RESP_REPORT": r"\breport\w*",
    "RESP_DISCLOSE": r"\bdisclos\w*|\b(?:told|informed)\b[^.]*\b(?:mother|father|parents?|teacher|friend|counselor|guardian|sister|brother)\b",
    "RESP_PLATFORM_ENFORCE": r"\b(?:banned|suspended|removed|disabled|terminated|deactivated|shut down)\b",
    "LE_RECEIVE_TIP": r"\bcyber ?tip\w*|\btips?\b|\bNCMEC\b|\breceiv\w+ (?:a |an )?(?:report|complaint|referral)\b",
    "LE_UNDERCOVER_ENGAGE": r"\bundercover\b|\bUC\b|\bcovert\b",
    "LE_SURVEIL": r"\bsurveil\w*|\bmonitor\w*",
    "LE_LEGAL_PROCESS": r"\bsubpoena\w*|\bwarrant\b|\bcourt order\b|\blegal process\b",
    "LE_SEARCH_SEIZE": r"\b(?:search\w*|seiz\w*)\b",
    "LE_FORENSIC_EXAM": r"\bforensic\w*|\bexamin\w*|\bextract\w*",
    "LE_INTERVIEW": r"\binterview\w*|\bMiranda\b|\bconfess\w*",
    "LE_INTERDICT": r"\binterdict\w*|\bintercept\w*",
    "LE_ARREST": r"\barrest\w*|\btaken into custody\b|\bapprehend\w*",
    "PROC_CHARGE": r"\bindict\w*|\bcharged\b|\bcomplaint\b|\binformation\b",
    "PROC_PLEA": r"\bple(?:a|d|aded)\b|\bguilty\b",
    "PROC_VERDICT": r"\bverdict\b|\bconvicted\b|\bfound (?:him|her|the defendant|defendant) guilty\b",
    "PROC_SENTENCE": r"\bsentenc\w*|\bmonths\b|\bimprisonment\b",
}
CUES = {code: re.compile(pattern, re.I) for code, pattern in _CUES.items()}


def cued(sentence: str, codes=None) -> Set[str]:
    """The codes (among ``codes``, default every code with cues) the sentence carries a cue for."""
    return {c for c in (CUES if codes is None else codes) if c in CUES and CUES[c].search(sentence)}


def settle(sentence: str, x: str, y: str) -> Optional[str]:
    """The one of two differing action codes the sentence supports, or None.

    Both codes must be specific codes with cue entries and exactly one must be cued; or one is a
    residual code and the other, specific code is cued (the codebook's "not coded more specifically")."""
    if x == y:
        return x
    specific = [c for c in (x, y) if c not in RESIDUAL]
    if any(c not in CUES for c in specific):
        return None
    hit = cued(sentence, specific)
    return next(iter(hit)) if len(hit) == 1 else None
