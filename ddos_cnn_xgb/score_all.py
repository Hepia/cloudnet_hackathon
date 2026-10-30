#!/usr/bin/env python3
# Score ALL windows of a windowed HDF5 with a trained CNN run. Pure h5py+tf+sklearn.
# Optional --ablate zeroes given byte positions (test-time field removal probe).
import argparse, json, time
import numpy as np, h5py, tensorflow as tf
from sklearn.metrics import precision_recall_fscore_support, confusion_matrix

ap=argparse.ArgumentParser()
ap.add_argument("-i","--input",required=True)
ap.add_argument("-m","--model",required=True)
ap.add_argument("-t","--threshold",type=float,default=0.5)
ap.add_argument("-b","--batch",type=int,default=256)
ap.add_argument("--ablate",default="",help="comma byte positions to zero before scoring")
ap.add_argument("--timeit",action="store_true")
a=ap.parse_args()

with open(f"{a.model}/model.json") as f: model=tf.keras.models.model_from_json(f.read())
model.load_weights(f"{a.model}/run.weights.h5")
with h5py.File(a.input,"r") as f:
    X=f["X"][:]; y=f["y"][:]
abl=[int(x) for x in a.ablate.split(",") if x!=""]
if abl:
    X=X.copy(); X[:,:,abl]=0
Xf=X[...,np.newaxis].astype(np.float32)
t0=time.perf_counter()
probs=model.predict(Xf,batch_size=a.batch,verbose=0)
dt=time.perf_counter()-t0
preds=(probs>a.threshold).astype(np.int32)
yt=y.ravel(); yp=preds.ravel()
acc=float((yt==yp).mean())
(p0,p1),(r0,r1),(f0,f1),_=precision_recall_fscore_support(yt,yp,labels=[0,1],zero_division=0)
tn,fp,fn,tp=confusion_matrix(yt,yp,labels=[0,1]).ravel()
yw=(y.mean(1)>0.5).astype(int); pw=(preds.mean(1)>0.5).astype(int)
wacc=float((yw==pw).mean())
npk=yt.size
out=dict(model=a.model.split("/")[-1],windows=int(y.shape[0]),packets=int(npk),
    accuracy=round(acc,6),benign_prec=round(float(p0),5),benign_rec=round(float(r0),5),
    ddos_prec=round(float(p1),5),ddos_rec=round(float(r1),5),ddos_f1=round(float(f1),5),
    fp_rate=float(fp/(fp+tn)) if fp+tn else 0.0, fn_rate=float(fn/(fn+tp)) if fn+tp else 0.0,
    window_acc=round(wacc,5), cm=[int(tn),int(fp),int(fn),int(tp)],
    fp_per_million_benign=round(1e6*fp/(fp+tn),2) if fp+tn else 0.0,
    ablate=a.ablate)
if a.timeit:
    out["pkts_per_sec"]=round(npk/dt,1); out["us_per_pkt"]=round(1e6*dt/npk,3); out["predict_s"]=round(dt,2)
print(json.dumps(out))
