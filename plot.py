"""Factual counts rendered from the independent audit; no generated data."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
audit=json.loads((ROOT/'results/audit.json').read_text())
assert audit['passed'] and audit['trials']==144
modes=['query','tenant','context']
labels=['Query only','Tenant + query','Fresh authorized context']
metrics=[('unauthorized','Unauthorized answers',24),('stale','Stale answers',8),
         ('repeat_hit','Repeat cache hits',8),('cold_denied','Correct cold denials',8)]
with plt.rc_context({'font.family':'DejaVu Sans','font.size':14,'svg.fonttype':'none'}):
    fig,axes=plt.subplots(2,2,figsize=(12,9),layout='constrained')
    for i,(ax,(metric,title,n)) in enumerate(zip(axes.flat,metrics)):
        values=[audit['summary'][mode][metric] for mode in modes]
        bars=ax.barh(range(3),values,color=['#44546A','#006A9C','#8B4513'],height=.56)
        bars[1].set_hatch('//')
        ax.set_yticks(range(3),labels if i%2==0 else ['','',''])
        ax.invert_yaxis();ax.set_xlim(0,n*1.33)
        ax.set_xticks([0,n/2,n],[str(0),str(n//2),str(n)])
        ax.set_title(title,fontweight='bold',fontsize=16,pad=14)
        ax.set_xlabel('Trials')
        for y,v in enumerate(values):
            ax.text(v+n*.04,y,f'{v}/{n}',va='center',fontsize=16)
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
    for suffix in ['png','svg']:
        fig.savefig(ROOT/f'results/cache-scope.{suffix}',dpi=170,facecolor='white')
    plt.close(fig)
(ROOT/'evidence/chart-environment.json').write_text(json.dumps(dict(matplotlib=matplotlib.__version__,source='results/audit.json',script='plot.py',transform='Raw audited numerators and predeclared denominators; no intervals, normalization, smoothing or missing-cell exclusion.',destination='LinkedIn factual metrics image'),indent=2)+'\n')
