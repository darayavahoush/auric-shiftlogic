# Blind (zero-leakage) evaluation

    python3 dev/audit_leakage.py --items paraphrase_blind/items.json     # must print PASS
    ./run paraphrase_blind/items.json --budget 1x --out /tmp/blind_1x.json
    python3 score.py paraphrase_blind/key.json /tmp/blind_1x.json

Rules that keep it blind: run it ONCE per prompt version and do not edit the prompt, glossary, shots or kNN pool using
what you see in it. If you do, the pool is burned; write a new pool (dev/pool_blind.py) and re-run the audit.
paraphrase_blind2 (same pool, different seed) is only for a second reading to shrink the standard error.
The audit also re-checks every rendered line of the set against the prompt, shots, kNN pool, visible items and the
earlier test sets, so editing the prompt later can make it FAIL: re-run it after any prompt change.
