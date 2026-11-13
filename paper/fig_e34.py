import sys, pandas as pd, numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from statsmodels.stats.proportion import proportion_confint as pc
from scipy import stats
csv, out = sys.argv[1], sys.argv[2]
d=pd.read_csv(csv)
f=d[(d.workload=='diurnal')&(d.scenario!='normal')&(d.rul_scale==1)]
fig,ax=plt.subplots(1,2,figsize=(7.2,2.8))
modes=[('haempc','Full'),('ha_noHI','no HI'),('ha_noRUL','no RUL'),('ha_noPrecool','no pre-cool'),('empc','EMPC')]
for i,(m,l) in enumerate(modes):
    x=f[f['mode']==m]; k=int(x.unplanned_trips.sum()); n=len(x); lo,hi=pc(k,n,method='wilson')
    ax[0].bar(i,k/n,color='0.6' if m=='empc' else '#3b6ea5'); ax[0].errorbar(i,k/n,yerr=[[k/n-lo],[hi-k/n]],color='k',capsize=3)
    ax[0].text(i,hi+0.03,f'{k}/{n}',ha='center',fontsize=7)
ax[0].set_xticks(range(5)); ax[0].set_xticklabels([l for _,l in modes],fontsize=8); ax[0].set_ylabel('Unplanned-trip rate'); ax[0].set_ylim(0,1.12); ax[0].set_title('E3: ablations (both faults, both climates)',fontsize=9)
p=d[(d.climate=='pune')&(d.workload=='diurnal')&(d.scenario=='pump')&(d['mode']=='haempc')]
g=p.groupby('rul_scale').risk_zoneCD_s.agg(['mean','std','count'])
ci=stats.t.ppf(.975,g['count']-1)*g['std'].fillna(0)/np.sqrt(g['count'])
ax[1].errorbar(g.index,g['mean']/60,yerr=ci/60,marker='o',capsize=3,color='#3b6ea5',label='PI-HA-EMPC')
e=d[(d.climate=='pune')&(d.workload=='diurnal')&(d.scenario=='pump')&(d['mode']=='empc')].risk_zoneCD_s.mean()/60
ax[1].axhline(e,color='0.5',ls='--',label='EMPC (no health)')
ax[1].set_xlabel('RUL scale factor (1 = nominal; >1 optimistic)',fontsize=8); ax[1].set_ylabel('Zone C/D exposure (min)'); ax[1].set_ylim(0,55)
ax[1].set_title('E4: pump fault, Pune (0 trips at every scale)',fontsize=9); ax[1].legend(fontsize=7,loc='lower right')
for a in ax: a.grid(alpha=.3); a.tick_params(labelsize=8)
plt.tight_layout(); plt.savefig(out)
