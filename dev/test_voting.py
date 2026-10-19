"""
Voting Ablation: Compares Final-Answer Modal Voting vs Per-Line Constraint Voting
across multi-sample outputs saved in results/report_signals_v4.json.
"""
import json
from collections import defaultdict, Counter
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.prefilter import prefilter_item
import src.decompiler_v2 as D
from src.solver import solve, Constraint
from src.pipeline_v2 import answer_from_raw, _finalize, _vote_key
import score as S

def main():
    report_path = os.path.join(os.path.dirname(__file__), "../results/report_signals_v4.json")
    if not os.path.exists(report_path):
        print("Report not found:", report_path)
        return
    data = json.load(open(report_path))
    raws = data["raw_outputs"]
    items = {it["id"]: it for it in json.load(open(os.path.join(os.path.dirname(__file__), "../paraphrase_new/items.json")))}
    key = json.load(open(os.path.join(os.path.dirname(__file__), "../paraphrase_new/key.json")))

    item_samples = defaultdict(list)
    for k, raw in raws.items():
        if not raw or not raw.strip():
            continue
        iid, s = k.split("#")
        item_samples[iid].append(raw)

    valid_iids = [iid for iid, sl in item_samples.items() if len(sl) >= 3]
    print(f"Items with >= 3 valid samples: {len(valid_iids)} out of 50")

    # 1. Final answer modal voting (K=3)
    final_answers = {}
    for iid in valid_iids:
        it = items[iid]
        sample_answers = []
        for raw in item_samples[iid][:3]:
            ans, legal, _ = answer_from_raw(iid, it["text"], raw)
            sample_answers.append(ans)
        best_key = Counter(_vote_key(a) for a in sample_answers).most_common(1)[0][0]
        final_answers[iid] = next(a for a in sample_answers if _vote_key(a) == best_key)

    sc_final = S.score({i: key[i] for i in valid_iids}, final_answers, [items[i] for i in valid_iids])
    print(f"Final-Answer Modal Voting (K=3) Macro: {sc_final['macro_exact_match']:.4f}")
    print("Per case:", sc_final["per_case_rate"])

    # 2. Per-line constraint voting (K=3)
    per_line_answers = {}
    for iid in valid_iids:
        it = items[iid]
        pi = prefilter_item(iid, it["text"])
        lines_dict = dict(pi.candidate_lines)
        line_verdicts = defaultdict(list)
        for raw in item_samples[iid][:3]:
            v_dict = D.parse_verdicts(raw, pi.header.staff, pi.candidate_lines)
            for idx in lines_dict:
                v = v_dict.get(idx)
                if v and v.status == "constraint":
                    line_verdicts[idx].append((v.kind, v.args))
                else:
                    line_verdicts[idx].append(None)
                    
        voted_constraints = []
        for idx, calls in line_verdicts.items():
            counts = Counter(calls)
            best_v, cnt = counts.most_common(1)[0]
            if best_v is not None and cnt >= 2:
                kind, args = best_v
                voted_constraints.append(Constraint(kind=kind, args=args, source_line=lines_dict[idx]))
                
        r = solve(pi.header.staff, pi.header.station_holders, voted_constraints)
        ans = _finalize(r)
        if ans is None:
            ans = {"case": "ambiguous", "assignments": [w.format_assignment() for w in r["valid_worlds"][:4]]}
        per_line_answers[iid] = ans

    sc_line = S.score({i: key[i] for i in valid_iids}, per_line_answers, [items[i] for i in valid_iids])
    print(f"Per-Line Voting (K=3) Macro: {sc_line['macro_exact_match']:.4f}")
    print("Per case:", sc_line["per_case_rate"])

if __name__ == "__main__":
    main()
