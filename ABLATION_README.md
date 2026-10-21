# Ablation harness

    python3 scripts/run_ablation.py selftest     # offline path == pipeline_v2.run_item (fake endpoint, no key)
    python3 scripts/run_ablation.py plan --items items.json --samples 10 --configs full,base_prompt
    python3 scripts/run_ablation.py collect --items items.json --key visible_key.json --tag visible --samples 10 --workers 2 --configs full,base_prompt
    python3 scripts/run_ablation.py collect --items items.json --key visible_key.json --tag visible --samples 5  --workers 2 --configs fixed10,no_shots,no_glossary,no_echo,direct
    python3 scripts/run_ablation.py report  --items items.json --key visible_key.json --tag visible --samples 10 --out results/ablation_visible.md

Banks are appended to results/ablation/bank_<tag>_<variant>.jsonl and are resumable. Re-run the same set with
--items paraphrase_d/items.json --key paraphrase_d/key.json --tag poolD for a non-visible set.
Post-processing ablations (no_repair, no_fuzzy, no_vote) come free from the `full` bank.
