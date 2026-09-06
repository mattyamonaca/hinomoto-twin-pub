"""Pure numerical helpers and model axis definitions; no storage access."""
import numpy as np

AGES=[f'{i:02d}' for i in range(1,14)]
STATUS=['regular','nonregular','executive','self','family']

def norm(x):
 x=np.asarray(x,dtype=float);return x/np.maximum(x.sum(axis=-1,keepdims=True),1e-300)
def ipf(seed,rows,cols,tol=1e-10):
 """KL projection with nonnegative, equal-total margins; zeros in margins stay zero."""
 rows=np.asarray(rows,float);cols=np.asarray(cols,float)
 assert np.isclose(rows.sum(),cols.sum(),rtol=1e-8,atol=1e-6)
 if rows.sum()==0:return np.zeros_like(seed,dtype=float),0,0.
 z=np.maximum(np.asarray(seed,float),1e-14)
 z[rows==0,:]=0;z[:,cols==0]=0
 for it in range(2000):
  z*=np.divide(rows,z.sum(1),out=np.zeros_like(rows),where=z.sum(1)>0)[:,None]
  z*=np.divide(cols,z.sum(0),out=np.zeros_like(cols),where=z.sum(0)>0)[None,:]
  err=max(np.max(np.abs(z.sum(1)-rows)/np.maximum(rows,1)),np.max(np.abs(z.sum(0)-cols)/np.maximum(cols,1)))
  if err<tol:return z,it+1,float(err)
 raise RuntimeError(f'IPF did not converge: {err}')
