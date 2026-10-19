import random, itertools, numpy as np
import sim
from sim import *
def readings_to_mask(item,rd):
    m=np.ones(720,bool)
    for _,k,a in rd: m&=mask(item,k,a)
    return m
def pair_unsat(item,rd):
    ms=[mask(item,k,a) for _,k,a in rd]
    for i in range(len(ms)):
        for j in range(i+1,len(ms)):
            if not (ms[i]&ms[j]).any(): return True
    return False
def neighbors(item,l,k,a):
    out=[]
    if k in FLIP: out.append((FLIP[k],a))
    if k in("ORDER_LT","IMMEDIATE_AFTER","IMMEDIATE_BEFORE"): out.append((k,(a[1],a[0])))
    if k=="BETWEEN":
        for i in (1,2): out.append((k,(a[i],a[1 if i==2 else 2],a[0])))
    return out
def plausible_count(n): return 1<=n<=4
def repair_decoder(item,rd,cands):
    """rd: extracted readings; cands: readings for lines the model did NOT extract (activation candidates)"""
    base=decide(item,rd)
    m=readings_to_mask(item,rd); n=int(m.sum())
    implausible = n>4 or (n==0 and pair_unsat(item,rd))
    if not implausible: return base
    best=None
    def consider(new_rd):
        nonlocal best
        mm=readings_to_mask(item,new_rd); c=int(mm.sum())
        if plausible_count(c) and (best is None or c<best[0]): best=(c,new_rd)
    for i,(l,k,a) in enumerate(rd):
        consider(rd[:i]+rd[i+1:])                                   # drop
        for nk,na in neighbors(item,l,k,a): consider(rd[:i]+[(l,nk,na)]+rd[i+1:])   # typed flip
    for c in cands: consider(rd+[c])                                # activate a skipped line
    if best is None: return base
    return decide(item,best[1])
def run2(e,d,trials,seed=1,use_cands=True):
    rng=random.Random(seed); res={}
    for name in("plain","repair"): res[name]={k:[0,0] for k in("unique","ambiguous","inconsistent")}
    for it in ITEMS_B:
        for _ in range(trials):
            rd=extract(it,e,d,rng)
            got={l for l,_,_ in rd}
            cands=[(g['line'],g['kind'],tuple(g['args'])) for g in it['gold'] if g['line'] not in got]+[(l,k,a) for l,k,a in it['decoys'] if l not in got]
            if not use_cands: cands=[]
            for name,dec in (("plain",decide(it,rd)),("repair",repair_decoder(it,rd,cands))):
                r=res[name][it['case']]; r[0]+=correct(it,dec); r[1]+=1
    return {n:(sum(v[0]/v[1] for v in r.values())/3,{k:v[0]/v[1] for k,v in r.items()}) for n,r in res.items()}
if __name__=="__main__":
    for e,d in [(0.05,0.0),(0.05,0.10),(0.07,0.15),(0.10,0.10)]:
        for uc in (False,True):
            r=run2(e,d,12,use_cands=uc)
            print(f"e={e:.2f} d={d:.2f} cands={'yes' if uc else 'no '}: plain {r['plain'][0]:.1%}  repair {r['repair'][0]:.1%}   ({' / '.join(f'{v:.0%}' for v in r['repair'][1].values())})")
