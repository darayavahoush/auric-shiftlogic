# Pool D: second blind pool (different construction style)

Pool C (`paraphrase_blind*`) is burned for prompt tuning once you read its per-line taxonomy. Pool D is the clean replacement.

    python3 dev/audit_leakage.py --pool d --items paraphrase_d/items.json    # must print PASS
    python3 dev/audit_leakage.py --pool d --negative-control                 # must print FLAGGED for all 3 planted leaks
    ./run_v2 paraphrase_d/items.json --budget 1x --out /tmp/d_1x.json && python3 score.py paraphrase_d/key.json /tmp/d_1x.json

- Style: nominal / passive / fronted constructions ("{A} has been earmarked for {T}.", "{S} duty falls to {A}.",
  "Of {A} and {B}, the first to work is {A}.", "Right on {B}'s heels comes {A}."). Pool C was short active declaratives.
- 42 binding templates (all 11 kinds), 20 decoy templates (CHAT/PAST/WISH/OPEN/UNMET), 12 new names, 6 new hedges, 3 new wrappers.
- Audit corpus for pool D = everything pool C's corpus had PLUS pool C's templates, names and its two generated sets.
  Pool C's own audit still passes unchanged (`--pool blind`).
- Gold: the generator's typed constraints. Solver + score.py on gold labels = 100% on both sets (60 items each).
- paraphrase_d (seed 41) is the reading; paraphrase_d2 (seed 42) is a second reading to shrink the standard error.

Rules that keep it blind: run it once per prompt version. If you edit the prompt, glossary, shots or kNN pool using what you see in pool D,
it is burned and needs a pool E. Re-run the audit after any prompt change.

Scorer quirk found while building it: `score.py` treats any `"<up to 60 chars>: "` prefix of a line as a restatement prefix and strips it
(`squash_stmt`). A genuine constraint line with a colon in it ("Assigned to 11:00: Anika.") gets mangled in the key match, which broke one
inconsistent item. Pool D therefore avoids colons in constraint templates. If the organisers' held-out lines contain such colons the scorer
will behave oddly on them whatever your model does.
