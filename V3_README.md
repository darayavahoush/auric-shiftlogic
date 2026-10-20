# decompiler_v3 (slot form) + pool E (third blind pool)

## What v3 is
Same job, same single call per item, different OUTPUT FORM. Instead of positional predicates (`BEFORE(x, y)` with an argument-order
convention) the model fills a named-slot form per line and Python maps it to the repo's constraint kinds:

    ON person=X block=HH:MM neg=no|yes        AT person=X station=S neg=no|yes
    ORDER first=<earlier> second=<later> gap=any|none        BETWEEN middle=M ends=A,B        SKIP:<chat|past|wish|open|unmet>

The decisions v2 got wrong on pool C (who is earlier, who is in the middle, NEXT vs BEFORE) become explicit named slots.
The prompt also walks the model through five questions per line (is it today's roster? what kind? polarity, who is first, who is in the middle)
and contains the patch rules. Shots and kNN lines are the same visible data, re-rendered into slots by `fmt_form` (code, not hand-edited).
**This is a bundle test (format + prompt wording), not an isolated test of the format.** It is a hypothesis, not a result.

## Pool E
Third style: spoken hand-over voice (imperatives, "if you need someone at X it is Y", fragments, "wraps up and ... is up straight away").
42 binding templates (all 11 kinds), 20 decoy templates, 12 new names, 6 hedges, 3 wrappers. Audited against the v3 prompt, the patched v2 prompt,
shots, kNN pool, visible items, pools A/B/C/D and every earlier generated set. `paraphrase_e` (seed 51) + `paraphrase_e2` (seed 52) = 120 items.
Imperative/fragment templates are exempt from hedge prefixes (they would read as broken English); that is declared in `E_NO_HEDGE`.

## Install and offline checks (no API)
    cd ~/Downloads/candidate_package
    unzip -o ~/Downloads/shiftlogic_v3_poolE_kit_v6.zip
    python3 dev/enable_shift_dec.py                      # idempotent: pipeline_v2.py / eval_lines.py read SHIFT_DEC
    python3 dev/test_v3.py paraphrase_e paraphrase_e2    # roundtrip 0 mismatches; gold e2e 1.000; swapped-ORDER e2e ~0.33
    python3 dev/audit_leakage.py --pool e --items paraphrase_e/items.json     # PASS
    python3 dev/audit_leakage.py --pool e --items paraphrase_e2/items.json    # PASS
    python3 dev/audit_leakage.py --pool e --negative-control                  # FLAGGED x4

## The run (three configs, same pipeline defaults, once each)
    for s in e e2; do for cfg in v2_base v2 v3; do
      SHIFT_DEC=$cfg ./run_v2 paraphrase_$s/items.json --budget 1x --out results/${s}_${cfg}.json 2>&1 | tee results/${s}_${cfg}.log | tail -1
    done; done
    grep -c "call failed" results/*_v2_base.log results/*_v2.log results/*_v3.log
    python3 dev/compare_runs.py --labels base,patched,v3 --sets \
      paraphrase_e:paraphrase_e/key.json:paraphrase_e/items.json:results/e_v2_base.json,results/e_v2.json,results/e_v3.json \
      paraphrase_e2:paraphrase_e2/key.json:paraphrase_e2/items.json:results/e2_v2_base.json,results/e2_v2.json,results/e2_v3.json

`v2_base` = the original prompt (src/decompiler_v2_base.py, from commit 4c3ff4a); `v2` = current patched prompt; `v3` = slot form.

## Rules set BEFORE seeing any pool E result
1. One run per config per set. Do not re-run a config to pick the better draw.
2. Failed calls (connection errors) count as failures in the score. Report the failed-call count beside every number; if the counts differ a lot between
   configs, re-run the affected config and keep the first run's count in the notes.
3. Adopt v3 only if it beats patched v2 by at least 5 items net out of 120 AND the paired sign test gives p < 0.10. Otherwise keep patched v2.
   Ties and small gains are not a reason to switch format.
4. Do not open per-line output (eval_lines) for pool E until the decision is made. After that, E is spent for prompt tuning.
5. Pool E is a style I invented. The decision rule is about relative ranking, not a promise about the organisers' set.
