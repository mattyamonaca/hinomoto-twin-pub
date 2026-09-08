"""Explicit, limited support rules and expectation-preserving integer role allocation.

These rules do not establish accuracy of unobserved household relationships. In particular,
we do not impose a typical spouse age gap or identify biological/step/adoptive relationships.
"""
import numpy as np

VERSION = 'household-support-1'
RULES = [
    '世帯主は1人、世帯主の配偶者は最大1人です。',
    '「夫婦のみ」は世帯主と配偶者の2人です。「夫婦と子供」は、現行の世帯主・配偶者を夫婦とする作り方に合わせ、残りを「子」に限定します。',
    '「ひとり親と子供」「単独」には世帯主の配偶者を割り当てません。単独世帯は世帯主だけです。',
    '15歳未満を配偶者として生成せず、15歳未満の世帯主にも配偶者を割り当てません。15〜19歳は一つの階級なので、この階級全体は除外しません。',
    '15歳以上の世帯主に、15歳未満の「世帯主の父母」を割り当てません。',
]
LIMITATION = ('これは生成上の限定的な整合ルールです。夫婦と子供の世帯で子が世帯主になる場合は現行モデルの対象外です。'
              '年齢差の大小や所得の高低だけで人物を排除せず、すべての親族関係の妥当性を保証するものではありません。'
              '不詳の補完方法や世帯員同士の所得の関連は、今回の制約では改善していません。')


def support(f, head_age):
    allowed = np.ones((13, 2, 18), dtype=bool)
    allowed[0] = False
    if f == 0:
        allowed[2:] = False
    elif f == 1:
        allowed[3:] = False
    elif f == 2:
        allowed[1] = False
    elif f == 5:
        allowed[:] = False
    allowed[1, :, :3] = False
    if head_age < 3:
        allowed[1] = False
    else:
        allowed[4, :, :3] = False
    return allowed


def constrain(N, T):
    """Condition member shapes on allowed support, keeping each head-cell's member total.

    No new support or fallback uniform distribution is introduced. F1/F2 already assume
    the head and spouse are the couple. Their spouse total stays one per household.
    Changed sex/age/role margins are reported rather than claimed to remain calibrated.
    """
    out = T.copy(); moved = 0.; changed = 0
    for f, s, a, k in np.argwhere(N > 1e-9):
        ix = (f, s, a, k); n = N[ix]; cell = T[ix]
        remaining = cell[1:].sum()
        z = np.where(support(f, a), cell, 0.)
        if f in (0, 1):
            if a < 3 or remaining < n - 1e-7:
                raise ValueError(f'Infeasible couple head/size at {ix}')
            sp = z[1].sum()
            if sp <= 0:
                raise ValueError(f'No admissible spouse support at {ix}')
            z[1] *= n / sp
            rest = max(remaining - n, 0.)
            if f == 0 and rest > 1e-7:
                raise ValueError(f'Couple-only size is not two at {ix}')
            if f == 1 and rest < n - 1e-7:
                raise ValueError(f'Couple-with-children lacks child slots at {ix}')
            mass = z[2:].sum()
            if rest > 1e-7 and mass <= 0:
                raise ValueError(f'No admissible child support at {ix}')
            z[2:] *= rest / mass if mass > 0 else 0.
        else:
            mass = z.sum()
            if remaining > 1e-7 and mass <= 0:
                raise ValueError(f'No admissible member support at {ix}')
            z *= remaining / mass if mass > 0 else 0.
            if z[1].sum() > n:
                z[1] *= n / z[1].sum()
                rest=z[2:].sum()
                if remaining-n>1e-7 and rest<=0:
                    raise ValueError(f'No admissible non-spouse support at {ix}')
                z[2:] *= (remaining-n)/rest if rest>0 else 0.
        z[0] = cell[0]
        delta = float(np.abs(z - cell).sum()) / 2
        moved += delta; changed += int(delta > 1e-8)
        out[ix] = z
    # Ignore only numerical-zero household cells consistently with the sampler.
    tiny = (N <= 1e-9)
    out[tiny] = 0
    validate(N, out)
    return out, {'version': VERSION, 'changed_head_cells': changed,
                 'reallocated_expected_members': moved,
                 'sex_age_margin_l1_change': float(np.abs(out.sum((0,1,2,3,4))-T.sum((0,1,2,3,4))).sum()),
                 'note': 'Head-cell household and member totals are preserved; role and sex/age margins may change.'}


def validate(N, T):
    for f, s, a, k in np.argwhere(N > 1e-9):
        ix = (f,s,a,k); n=N[ix]; cell=T[ix]; tol=max(1e-8,n*1e-10)
        if not np.isfinite(cell).all() or (cell < 0).any():
            raise ValueError(f'Invalid household member weights at {ix}')
        head=cell[0].copy();head[s,a]-=n
        if np.abs(head).sum()>tol:
            raise ValueError(f'Household must have exactly one matching head at {ix}')
        if (cell[1:][~support(f,a)[1:]]>0).any():
            raise ValueError(f'Forbidden household member support at {ix}; rebuild household data')
        spouse=cell[1].sum()/n;size=cell.sum()/n
        if spouse>1+1e-9 or (f in (0,1) and abs(spouse-1)>1e-9):
            raise ValueError(f'Invalid spouse count at {ix}')
        if (k<9 and abs(size-(k+1))>1e-7) or (k==9 and size<10-1e-7):
            raise ValueError(f'Invalid household size at {ix}')
        if f==0 and abs(size-2)>1e-7 or f==1 and size<3-1e-7 or f==5 and abs(size-1)>1e-7:
            raise ValueError(f'Family/size contradiction at {ix}')


def _ends(counts):
    c=np.asarray(counts,dtype=float)
    c=np.where(np.abs(c-np.rint(c))<1e-9,np.rint(c),c)
    ends=np.cumsum(c)
    return np.where(np.abs(ends-np.rint(ends))<1e-7,np.rint(ends),ends)


def role_counts(counts, offset):
    """Systematic rounding: each role gets floor/ceil(c), E[count]=c, total floor/ceil(sum c)."""
    ends=_ends(counts)
    return np.diff(np.r_[0,np.floor(ends+offset)]).astype(int)


def count_patterns(counts):
    """Exact integral over the one uniform offset, used by analytic presence probabilities."""
    ends=_ends(counts)
    cuts=np.unique(np.r_[0.,1.,np.mod(-ends,1.)])
    return [(float(hi-lo),role_counts(counts,(lo+hi)/2))
            for lo,hi in zip(cuts[:-1],cuts[1:]) if hi-lo>1e-12]


def validate_population(df):
    """Check actual generated records, not just expectations; reject before publication."""
    if df.empty:
        return {'version': VERSION, 'checked_households': 0, 'violations': 0}
    g=df.groupby('household_id');heads=df[df.role==0].set_index('household_id')
    if len(heads)!=g.ngroups or heads.index.has_duplicates:
        raise ValueError('Population must have one head per household')
    size=g.size();sp=df[df.role==1].groupby('household_id').size().reindex(size.index,fill_value=0)
    bad=(sp>1)|(size!=g['size'].first())|(g['family'].nunique()!=1)|(g['size_bin'].nunique()!=1)
    f=g['family'].first();k=g['size_bin'].first()
    bad|=((k<9)&(size!=k+1))|((k==9)&(size<10))
    bad|=((f==0)&((size!=2)|(sp!=1)))|((f==1)&((size<3)|(sp!=1)))|((f==5)&(size!=1))
    if bad.any():raise ValueError('Population violates head/spouse/family/size constraints')
    nonhead=df[df.role!=0]
    masks=np.array([[support(f,a) for a in range(18)] for f in range(7)])
    head_age=nonhead.household_id.map(heads.age18).to_numpy(int)
    allowed=masks[nonhead.family.to_numpy(int),head_age,nonhead.role.to_numpy(int),
                  nonhead.sex.to_numpy(int),nonhead.age18.to_numpy(int)]
    if not allowed.all():raise ValueError('Population contains forbidden relationship/age support')
    return {'version': VERSION, 'checked_households': int(g.ngroups), 'violations': 0}
