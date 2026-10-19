# shiftlogic v2 kit

Unzip into the repo root (adds src/decompiler_v2.py, pipeline_v2.py, repair.py, shots.json, run_v2, eval_lines.py,
paraphrase_new/ (50 reworded items), paraphrase_visiblectl/ (30 in-distribution control items), dev/).

    pip install -r requirements.txt openai python-dotenv
    # 1) measure per-line accuracy + 1x macro, 5 samples each (each sample = ONE call)
    python3 eval_lines.py --items paraphrase_new/items.json --gold paraphrase_new/gold_lines.json --key paraphrase_new/key.json --samples 5 --out report_new.json
    python3 eval_lines.py --items paraphrase_visiblectl/items.json --gold paraphrase_visiblectl/gold_lines.json --key paraphrase_visiblectl/key.json --samples 5 --out report_ctl.json
    python3 eval_lines.py --items items.json --gold visible_gold_lines.json --key visible_key.json --samples 5 --out report_vis.json
    # 2) official-style run
    ./run_v2 paraphrase_new/items.json --budget 1x --out /tmp/a.json && python3 score.py paraphrase_new/key.json /tmp/a.json

Checks that pass offline: dev/oracle_check.py (60/60 visible keys incl. all conflict sets), dev/validate_set.py,
dev/test_roundtrip.py, dev/test_pipeline.py (1/3/10 requests per item, failures counted, never retried).
Nothing here has been run against Granite.

## kNN examples (optional, A/B against the fixed shots)
    pip install sentence-transformers scikit-learn
    python3 eval_lines.py ... --knn 3            # sentence embeddings (MiniLM), 3 nearest labelled lines per line
    python3 eval_lines.py ... --knn 3 --knn-backend tfidf   # offline fallback
    ./run_v2 items.json --budget 1x --knn 3 --out a.json
Embeddings only choose which labelled lines Granite sees. Granite still labels every line. Still ONE call per sample.

## Signal logging (step 1 of fusion)
    python3 eval_lines.py --items paraphrase_new/items.json --gold paraphrase_new/gold_lines.json --key paraphrase_new/key.json --samples 5 --logprobs --out report_signals.json
Look at report["signals"]: error rate when kNN disagrees with Granite vs when it agrees, and error rate in the
lowest-confidence 10% of lines (needs the endpoint to return logprobs; if "logprob_conf" is missing, it doesn't).
