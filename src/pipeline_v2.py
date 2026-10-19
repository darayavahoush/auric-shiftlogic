"""
One item, one budget. 1x = exactly ONE model request (no retries, no SDK retries: build the client with
max_retries=0). 3x/10x = K independent samples, each solved on its own, then a vote on the FINAL answer
(case + content), so two opposite readings of one line can never be merged into a constraint set.
"""
import json
from collections import Counter
from typing import Any, Dict, List, Optional

from src.prefilter import prefilter_item
from src.solver import solve
from src.repair import repair
import src.decompiler_v2 as D

BUDGET_CALLS = {"1x": 1, "3x": 3, "10x": 10}


def _finalize(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c = r["case"]
    if c == "unique":
        return {"case": "unique", "assignment": r["assignment"]}
    if c == "ambiguous":
        return {"case": "ambiguous", "assignments": r["assignments"]}
    if c == "inconsistent":
        return {"case": "inconsistent", "conflicts": r["conflicts"]}
    return None          # under_constrained: not a legal answer


def _vote_key(a: Dict[str, Any]):
    if a["case"] == "unique":
        return ("unique", json.dumps(a["assignment"], sort_keys=True))
    if a["case"] == "ambiguous":
        return ("ambiguous", tuple(sorted(json.dumps(x, sort_keys=True) for x in a["assignments"])))
    return ("inconsistent", tuple(sorted(a["conflicts"])))


def answer_from_raw(item_id: str, text: str, raw: str, use_repair: bool = True, under_fallback: str = "ambiguous", knn_flagged: Optional[Any] = None):
    pi = prefilter_item(item_id, text)
    cons, verdicts = D.decompile_v2(pi, raw)
    info = {"repair": None}
    if use_repair:
        cons, info["repair"] = repair(pi.header.staff, pi.header.station_holders, cons, flagged_lines=knn_flagged)
    r = solve(pi.header.staff, pi.header.station_holders, cons)
    a = _finalize(r)
    legal = a is not None
    if a is None:                       # still >4 worlds after repair
        a = {"case": "ambiguous", "assignments": [w.format_assignment() for w in r["valid_worlds"][:4]]}
    return a, legal, {"verdicts": verdicts, "worlds": r.get("world_count"), **info}


def run_item(client, model: str, item_id: str, text: str, budget: str = "1x", echo: bool = True,
             use_repair: bool = True, exclude_ids=(), temperature: float = 1.0,
             knn: int = 0, knn_backend: str = "tfidf"):
    n = BUDGET_CALLS[budget]
    pi = prefilter_item(item_id, text)
    msgs = D.messages_for_item(pi, echo=echo, exclude_ids=tuple(exclude_ids), knn=knn, knn_backend=knn_backend)
    answers: List[Dict[str, Any]] = []; legals: List[bool] = []
    calls = 0
    for _ in range(n):
        calls += 1                                     # every attempt counts, success or not; never retried
        try:
            raw = D.call_granite_v2(client, model, item_id, msgs, temperature=temperature)
        except Exception as e:                         # noqa: BLE001
            print(f"[warn] {item_id}: call failed: {e}")
            continue
        flagged = set()
        if use_repair:
            try:
                from src.knn import Retriever
                R = D._RETRIEVER.get(knn_backend) or D._RETRIEVER.setdefault(knn_backend, Retriever(knn_backend))
                lines_all = pi.all_lines
                S_ = R._sims(lines_all)
                for j, p in enumerate(R.pool):
                    if p["item"] == item_id:
                        S_[:, j] = -1
                _, v_dict = D.decompile_v2(pi, raw)
                for idx, l_text in pi.candidate_lines:
                    top = S_[idx - 1].argsort()[::-1][:3]
                    votes_kind = sum(1 for j in top if R.pool[j]["kind"])
                    v_one = v_dict.get(idx)
                    model_says = (v_one is not None and v_one.status == "constraint")
                    knn_says = (votes_kind >= 2)
                    if knn_says != model_says:
                        flagged.add(l_text)
            except Exception:
                flagged = set()
        a, legal, _info = answer_from_raw(item_id, text, raw, use_repair, knn_flagged=flagged)
        answers.append(a); legals.append(legal)
    if not answers:
        return {"case": "inconsistent", "conflicts": []}, calls
    pool = [a for a, l in zip(answers, legals) if l] or answers
    best = Counter(_vote_key(a) for a in pool).most_common(1)[0][0]
    return next(a for a in pool if _vote_key(a) == best), calls
