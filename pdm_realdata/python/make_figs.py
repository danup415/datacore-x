import json, sys, numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import dcx_vib as V
from dcx_paths import DATA, RES, FIG; os.chdir(RES)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
BLUE,ORANGE,RED,GREY,GREEN='#2F5A86','#B7791F','#B42318','#8A9099','#2E7D4F'
# 1 CWRU splits
R=json.load(open('cwru_results.json')); ks=['random','load','size']; lab=['Random windows\n(common, leaky)','Unseen motor load','Unseen fault size']
fig,ax=plt.subplots(figsize=(7.2,3.6)); x=np.arange(3); w=0.36
for j,(m,c,n) in enumerate([('rf',BLUE,'Random forest on physics features'),('rule',ORANGE,'Training-free envelope rule')]):
    v=[R[k][f'{m}_macro_f1'] for k in ks]; lo=[R[k][f'{m}_macro_f1']-R[k][f'{m}_ci'][0] for k in ks]; hi=[R[k][f'{m}_ci'][1]-R[k][f'{m}_macro_f1'] for k in ks]
    ax.bar(x+(j-.5)*w,v,w,color=c,label=n,yerr=[lo,hi],capsize=3); [ax.text(x[i]+(j-.5)*w,v[i]+0.03,f'{v[i]:.2f}',ha='center',fontsize=9) for i in range(3)]
ax.set_xticks(x); ax.set_xticklabels(lab); ax.set_ylim(0,1.12); ax.set_ylabel('Macro-F1 (95 % CI)'); ax.legend(frameon=False,fontsize=8,loc='upper right')
ax.set_title('CWRU bearing faults (Normal / inner race / ball / outer race)',fontsize=10)
plt.tight_layout(); plt.savefig(os.path.join(FIG,'fig_cwru_splits.png'),dpi=150); plt.close()
# 2 FEMTO health index + alarm, 6 bearings
d=pd.read_csv('femto_features.csv.gz'); EW=pd.read_csv('femto_early_warning.csv').set_index('bearing'); P=json.load(open('femto_summary.json'))['prior']
import femto_rul as FR
bs=['Bearing1_1','Bearing1_3','Bearing2_2','Bearing2_3','Bearing1_4','Bearing3_3']
fig,axs=plt.subplots(2,3,figsize=(10,5.2),sharey=True)
for a,b in zip(axs.flat,bs):
    g=d[d.bearing==b].sort_values('idx'); sm,thr,al=FR.indicator(g); t=g['t_s'].values/3600
    hi=100*(1-np.clip((sm-1)/(P['R_fail']-1),0,1)); a.plot(t,hi,color=BLUE,lw=1.2)
    if al is not None: a.axvline(t[al],color=ORANGE,ls='--',lw=1); a.text(t[al],8,' alarm',color=ORANGE,fontsize=8)
    if b in FR.TRUNC: a.axvline(t[FR.TRUNC[b]-1],color=GREY,ls=':',lw=1); a.text(t[FR.TRUNC[b]-1],92,' cut',color=GREY,fontsize=8)
    a.set_title(f'{b}  (life {t[-1]:.1f} h)',fontsize=9); a.set_xlabel('Time (h)')
for a in axs[:,0]: a.set_ylabel('Health Index')
fig.suptitle('FEMTO / PRONOSTIA: Health Index from RMS vibration (alarm = sustained rise above healthy baseline)',fontsize=10)
plt.tight_layout(); plt.savefig(os.path.join(FIG,'fig_femto_hi.png'),dpi=150); plt.close()
# 3 FEMTO score per bearing
Rr=pd.read_csv('femto_rul_results.csv'); S=json.load(open('femto_summary.json'))['summary']
fig,ax=plt.subplots(figsize=(8.5,3.4)); x=np.arange(len(Rr))
ax.bar(x-0.2,Rr['naive_A'],0.4,color=GREY,label=f"Naive mean life (score {S['naive']['score']:.3f})")
ax.bar(x+0.2,Rr['hybrid_A'],0.4,color=BLUE,label=f"HI + exponential, bounded (score {S['hybrid']['score']:.3f})")
ax.set_xticks(x); ax.set_xticklabels([b.replace('Bearing','B') for b in Rr.bearing],fontsize=8); ax.set_ylabel('Official accuracy score A'); ax.set_ylim(0,1.05)
ax.legend(frameon=False,fontsize=8); ax.set_title('IEEE PHM 2012 test bearings: RUL at the official cut-off (1 = exact; late predictions penalised more)',fontsize=9)
plt.tight_layout(); plt.savefig(os.path.join(FIG,'fig_femto_scores.png'),dpi=150); plt.close()
# 4 waterfall Bearing1_1 velocity spectrum over life
import os
root=os.path.join(DATA,'raw','femto','Learning_set','Bearing1_1'); files=sorted(f for f in os.listdir(root) if f.startswith('acc_'))
sel=np.linspace(0,len(files)-1,14).astype(int); fig,ax=plt.subplots(figsize=(8,4.6)); cm=plt.get_cmap('viridis')
for j,i in enumerate(sel):
    a=pd.read_csv(os.path.join(root,files[i]),header=None).values[:,4]; a=a-a.mean(); N=len(a)
    A=np.abs(np.fft.rfft(a*np.hanning(N)))/N*2*9.80665; f=np.fft.rfftfreq(N,1/25600); m=(f>=10)&(f<=3000)
    vel=1000*A[m]/(2*np.pi*f[m]); ax.plot(f[m],vel+j*0.6,color=cm(j/len(sel)),lw=0.9)
    ax.text(3020,j*0.6,f'{i*10/3600:.1f} h',fontsize=7,va='bottom')
ax.set_xlabel('Frequency (Hz)'); ax.set_ylabel('Velocity amplitude (mm/s), offset by time'); ax.set_yticks([])
ax.set_title('FEMTO Bearing1_1: velocity spectrum from new to failure (7.8 h)',fontsize=10)
plt.tight_layout(); plt.savefig(os.path.join(FIG,'fig_femto_waterfall.png'),dpi=150); plt.close()
print('figs ok')
