from pathlib import Path
import sys,os
BASE=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(BASE/'.mplconfig'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
R=BASE
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--font',type=Path,help='Path to a Japanese-capable TTF/OTF/TTC font')
args=parser.parse_args()
font_path=args.font or Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
if not font_path.is_file():parser.error('Specify a Japanese-capable font with --font /path/to/font.ttf')
font=FontProperties(fname=str(font_path))
plt.rcParams.update({'font.family':font.get_name(),'font.size':10,'axes.unicode_minus':False})
from matplotlib import font_manager
font_manager.fontManager.addfont(font.get_file())
x=np.load(R/'data/municipality_model.npz');codes=x['municipality_codes'].tolist()
regions=[('13103','東京都 港区'),('13121','東京都 足立区'),('47201','沖縄県 那覇市')]
ranges=[(0,2),(2,6),(6,8),(8,10),(10,13),(13,16)]
ylabels=[f'{a}–{a+4}' for a in range(15,75,5)]+['75歳以上']
xs=['100未満','100–300','300–500','500–700','700–1,000','1,000以上']
matrices=[np.stack([x['p_age_income_given_municipality'][codes.index(c),:,l:r].sum(-1)*100 for l,r in ranges],-1) for c,n in regions]
fig,axs=plt.subplots(1,3,figsize=(15,7.7),sharey=True)
fig.subplots_adjust(left=.075,right=.90,top=.82,bottom=.26,wspace=.22)
vmax=max(a.max() for a in matrices)
for ax,(c,n),z in zip(axs,regions,matrices):
 im=ax.imshow(z,aspect='auto',vmin=0,vmax=vmax,cmap='Blues')
 ax.set_title(n,fontsize=17,pad=15,fontweight='bold')
 ax.set_xticks(range(6),xs,rotation=45,ha='right');ax.set_yticks(range(13),ylabels)
 ax.set_xlabel('個人の主な仕事の年収（万円）',labelpad=10)
 for j in range(13):
  for k in range(6):ax.text(k,j,f'{z[j,k]:.1f}',ha='center',va='center',fontsize=9,color='white' if z[j,k]>vmax*.55 else '#17344f')
 for sp in ax.spines.values():sp.set_visible(False)
axs[0].set_ylabel('年齢階級',labelpad=12)
cax=fig.add_axes([.925,.26,.014,.56]);cb=fig.colorbar(im,cax=cax);cb.set_label('その地域の15歳以上人口に占める割合（%）',labelpad=12)
fig.text(.075,.945,'市区町村別の「年齢 × 年収」推定分布',fontsize=22,weight='bold')
fig.text(.075,.89,'各パネルの全セル合計 = 100%  ／  同じ色は同じ確率  ／  表示用に年収を6区分へ集約（数値は四捨五入）',fontsize=12,color='#385168')
fig.text(.075,.065,'人口・就業構成・地域境界：2020年  ｜  所得分布：2022年  ｜  税務補助：2022年度（2021年所得）',fontsize=11)
fig.text(.075,.028,'公表統計を組み合わせたモデル推定。100万円未満には非就業等のモデル上0円を含む。実測の市区町村別所得表ではありません。',fontsize=10,color='#4c6072')
fig.savefig(R/'municipal_comparison.png',dpi=160,facecolor='white')
print('Saved plot',vmax)
