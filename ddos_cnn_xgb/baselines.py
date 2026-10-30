import sys, json, time
import numpy as np, h5py
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import confusion_matrix

TRAIN=sys.argv[1]; DSFILES=sys.argv[2:]
rng=np.random.default_rng(42)

def load_flat(path, cap=None):
    with h5py.File(path,"r") as f:
        X=f["X"][:]; y=f["y"][:]
    X=X.reshape(-1,X.shape[-1]).astype(np.float32); y=y.ravel().astype(np.int32)
    if cap and len(y)>cap:
        idx=np.sort(rng.choice(len(y),cap,replace=False)); X=X[idx]; y=y[idx]
    return X,y

Xtr,ytr=load_flat(TRAIN,cap=1_500_000)
print(f"train packets={len(ytr)} attack_frac={ytr.mean():.3f}",flush=True)
Xtr_s=Xtr/255.0

def rule_pred(X):
    # X: [n,64] float 0..255. Ethernet II / IPv4 / TCP layout: ethertype @12-13=0x0800,
    # IP protocol @23=6, TCP flags @47 (SYN=0x02, RST=0x04).
    # Transparent rule: a packet is attack iff it is a TCP SYN or TCP RST.
    et=(X[:,12].astype(int)<<8)|X[:,13].astype(int)
    proto=X[:,23].astype(int); flags=X[:,47].astype(int)
    is_tcp=(et==0x0800)&(proto==6)
    syn_or_rst=((flags & 0x02)>0)|((flags & 0x04)>0)
    return (is_tcp & syn_or_rst).astype(int)

def metrics(y,yp):
    tn,fp,fn,tp=confusion_matrix(y,yp,labels=[0,1]).ravel()
    return dict(acc=round((tn+tp)/len(y),5),
        benign_rec=round(tn/(tn+fp),4) if tn+fp else 0,
        ddos_rec=round(tp/(tp+fn),4) if tp+fn else 0,
        fp_rate=round(fp/(fp+tn),5) if fp+tn else 0,
        fp_per_M=round(1e6*fp/(fp+tn),1) if fp+tn else 0, cm=[int(tn),int(fp),int(fn),int(tp)])

models={}
t=time.perf_counter(); models["logreg"]=LogisticRegression(max_iter=200,n_jobs=-1).fit(Xtr_s,ytr); print("logreg fit",round(time.perf_counter()-t,1),"s",flush=True)
t=time.perf_counter(); models["tree_d12"]=DecisionTreeClassifier(max_depth=12,random_state=42).fit(Xtr,ytr); print("tree fit",round(time.perf_counter()-t,1),"s",flush=True)
t=time.perf_counter(); models["mlp_64_32"]=MLPClassifier(hidden_layer_sizes=(64,32),max_iter=40,random_state=42).fit(Xtr_s,ytr); print("mlp fit",round(time.perf_counter()-t,1),"s",flush=True)

results={}
for ds in DSFILES:
    name=ds.split("/")[-1].replace("_win.h5","")
    Xd,yd=load_flat(ds); Xd_s=Xd/255.0
    results[name]={}
    results[name]["rule_SYN_RST"]=metrics(yd,rule_pred(Xd))
    results[name]["logreg"]=metrics(yd,models["logreg"].predict(Xd_s))
    results[name]["tree_d12"]=metrics(yd,models["tree_d12"].predict(Xd))
    results[name]["mlp_64_32"]=metrics(yd,models["mlp_64_32"].predict(Xd_s))
print(json.dumps(results,indent=1))
