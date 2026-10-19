import json, sys, os, random, itertools, re, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from score import squash_stmt
import gold_annotate as ga

ITEMS=json.load(open(os.path.join(ROOT, 'items.json')))
KEY=json.load(open(os.path.join(ROOT, 'visible_key.json')))
ST=["intake","calibration","packing"]
UNMET=('wanted','lobbied','put in for','asked to move')
def build_item(it):
    staff,holders,lines,gold=ga.gold_for_item(it)
    gold=[g for g in gold if not any(u in g['line'].lower() for u in UNMET)]
    perms=list(itertools.permutations(range(5))); sperm=list(itertools.permutations(range(3)))
    B=np.array([p for p in perms for _ in sperm])                     # 720x5 block idx per staff
    S=np.array([s for _ in perms for s in sperm])                     # 720x3: station idx per holder
    # SB[w,s] = block of holder having station s
    hidx=[staff.index(h) for h in holders]
    SB=np.zeros((720,3),int)
    for hi,h in enumerate(hidx):
        for w in range(720): pass
    # vectorised
    for hi,h in enumerate(hidx):
        for s in range(3):
            m=S[:,hi]==s
            SB[m,s]=B[m,h]
    return dict(id=it['id'],staff=staff,holders=holders,hidx=hidx,B=B,S=S,SB=SB,lines=lines,gold=gold)
def mask(item,kind,args):
    B,S,SB,staff,holders=item['B'],item['S'],item['SB'],item['staff'],item['holders']
    pi=lambda n: staff.index(n)
    if kind=="BLOCK_EQ": return B[:,pi(args[0])]==args[1]
    if kind=="BLOCK_NEQ": return B[:,pi(args[0])]!=args[1]
    if kind in("STATION_EQ","STATION_NEQ"):
        if args[0] not in holders: return np.zeros(720,bool) if kind=="STATION_EQ" else np.ones(720,bool)
        m=S[:,holders.index(args[0])]==ST.index(args[1]); return m if kind=="STATION_EQ" else ~m
    if kind=="ORDER_LT": return B[:,pi(args[0])]<B[:,pi(args[1])]
    if kind=="IMMEDIATE_AFTER": return B[:,pi(args[0])]==B[:,pi(args[1])]+1
    if kind=="IMMEDIATE_BEFORE": return B[:,pi(args[1])]==B[:,pi(args[0])]+1
    if kind=="BETWEEN":
        m,x,y=[B[:,pi(a)] for a in args]; return ((x<m)&(m<y))|((y<m)&(m<x))
    if kind=="ORDER_STATION_PERSON": return SB[:,ST.index(args[0])]<B[:,pi(args[1])]
    raise ValueError(kind)
def core_search(masks,minsize=3,maxsize=6):
    n=len(masks)
    for r in range(minsize,min(maxsize,n)+1):
        for comb in itertools.combinations(range(n),r):
            m=masks[comb[0]].copy()
            for c in comb[1:]: m&=masks[c]
            if not m.any():
                # minimal? every (r-1)-subset must be sat (guaranteed since smaller sizes searched first, but sizes<minsize skipped)
                return comb
    return None
# truth
def truth(item):
    ms=[mask(item,g['kind'],g['args']) for g in item['gold']]
    m=np.ones(720,bool)
    for x in ms: m&=x
    return set(np.nonzero(m)[0].tolist())
def key_cores_norm(item):
    return [frozenset(squash_stmt(s) for s in c) for c in KEY[item['id']].get('conflict_line_sets',[])]
ITEMS_B=[build_item(it) for it in ITEMS]
for it in ITEMS_B:
    it['truth']=truth(it); it['kcores']=key_cores_norm(it); it['case']=KEY[it['id']]['case']

# ---- decoy readings (what a model could wrongly extract from non-binding lines)
DEC=[(r"(\w+) wanted (\d\d:00) and did not get it","BLOCK_NEQ"),(r"(\w+) lobbied for (\d\d:00) without success","BLOCK_NEQ"),
     (r"(\w+) put in for the (\d\d:00) block and was turned down","BLOCK_NEQ"),(r"(\w+) asked to move to the (\d\d:00) block","BLOCK_NEQ"),
     (r"(\w+) would have been a better fit for the (\d\d:00) block","BLOCK_EQ"),(r"if (\w+) had taken the (\d\d:00) block","BLOCK_EQ"),
     (r"had the rota gone the other way, (\w+) would be on (\d\d:00)","BLOCK_EQ"),(r"putting (\w+) on the (\d\d:00) block","BLOCK_EQ"),
     (r"(\w+) and the (\d\d:00) block came up","BLOCK_EQ"),(r"whether (\w+) (?:was down for the|had) (\d\d:00)","BLOCK_EQ"),
     (r"question of (\w+) on (\d\d:00)","BLOCK_EQ")]
STD=[(r"back in the old arrangement, (\w+) took (\w+)","STATION_EQ"),(r"last month (\w+) was on (\w+)","STATION_EQ"),
     (r"in the spring (\w+) held (\w+)","STATION_EQ"),(r"on the previous cycle (\w+) was (\w+)'s","STATION_EQ_R")]
def decoys(item):
    gl={g['line'] for g in item['gold']}; out=[]
    names=set(item['staff'])
    for i,l in enumerate(item['lines']):
        if l in gl: continue
        low=l.lower()
        for rx,k in DEC:
            m=re.search(rx,low)
            if m:
                nm=m.group(1).capitalize()
                if nm in names: out.append((l,k,(nm,ga.BLOCK_TO_IDX[m.group(2)]))); break
        else:
            for rx,k in STD:
                m=re.search(rx,low)
                if m:
                    a,b=m.group(1),m.group(2)
                    if k=="STATION_EQ_R": a,b=b,a
                    nm=a.capitalize() if a.capitalize() in names else b.capitalize()
                    st=[s for s in ST if s in (a,b)]
                    if nm in names and st: out.append((l,"STATION_EQ",(nm,st[0]))); break
    return out
for it in ITEMS_B: it['decoys']=decoys(it)

FLIP={"BLOCK_EQ":"BLOCK_NEQ","BLOCK_NEQ":"BLOCK_EQ","STATION_EQ":"STATION_NEQ","STATION_NEQ":"STATION_EQ"}
def corrupt(g,rng):
    k,a=g['kind'],list(g['args'])
    if k in FLIP and rng.random()<0.6: return FLIP[k],tuple(a)
    if k in("ORDER_LT","IMMEDIATE_AFTER","IMMEDIATE_BEFORE"): return k,(a[1],a[0])
    if k=="ORDER_STATION_PERSON": return k,(a[0],rng.choice([x for x in noisy_names if x!=a[1]]))
    if k=="BETWEEN": return k,(a[1],a[0],a[2])
    if k in("BLOCK_EQ","BLOCK_NEQ"):
        if rng.random()<.5: return k,(rng.choice([x for x in noisy_names if x!=a[0]]),a[1])
        return k,(a[0],(a[1]+rng.randint(1,4))%5)
    if k in("STATION_EQ","STATION_NEQ"): return k,(a[0],rng.choice([x for x in ST if x!=a[1]]))
    return k,tuple(a)
noisy_names=[]
def extract(item,e,d,rng):
    """model reading: per binding line -> {drop, corrupt} w.p. e ; per decoy line -> emitted as binding w.p. d."""
    global noisy_names; noisy_names=item['staff']
    rd=[]
    for g in item['gold']:
        r=rng.random()
        if r<e/2: continue                              # omission
        if r<e: k,a=corrupt(g,rng); rd.append((g['line'],k,tuple(a)))
        else: rd.append((g['line'],g['kind'],tuple(g['args'])))
    for (l,k,a) in item['decoys']:
        if rng.random()<d: rd.append((l,k,a))
    return rd
def decide(item,rd):
    ms=[mask(item,k,a) for _,k,a in rd]
    m=np.ones(720,bool)
    for x in ms: m&=x
    idx=np.nonzero(m)[0]; n=len(idx)
    if n==0:
        core=core_search(ms)
        return ("inconsistent",frozenset(squash_stmt(rd[c][0]) for c in core) if core else None)
    if n==1: return ("unique",set(idx.tolist()))
    if n<=4: return ("ambiguous",set(idx.tolist()))
    return ("under",None)
def correct(item,dec):
    case,val=dec
    if case!=item['case']: return False
    if case=="inconsistent": return val is not None and val in item['kcores']
    return val==item['truth']
def run(e,d,trials,seed=0,decoder=decide):
    rng=random.Random(seed); res={k:[0,0] for k in("unique","ambiguous","inconsistent")}
    for it in ITEMS_B:
        for _ in range(trials):
            rd=extract(it,e,d,rng); res[it['case']][0]+=correct(it,decoder(it,rd)); res[it['case']][1]+=1
    per={k:v[0]/v[1] for k,v in res.items()}; return sum(per.values())/3,per
if __name__=="__main__":
    print("decoy lines per item (avg):",sum(len(i['decoys']) for i in ITEMS_B)/60)
    print("binding lines per item:",sum(len(i['gold']) for i in ITEMS_B)/60)
    print(f"{'per-line err e':>14} {'decoy-as-binding d':>19} {'macro':>7}  unique/ambig/incons")
    for e,d in [(0,0),(0,0.3),(0.02,0),(0.05,0),(0.10,0),(0.02,0.05),(0.05,0.15),(0.08,0.3)]:
        m,p=run(e,d,15); print(f"{e:14.2f} {d:19.2f} {m:7.1%}  {p['unique']:.0%}/{p['ambiguous']:.0%}/{p['inconsistent']:.0%}")
