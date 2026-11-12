#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
import mdtest
from mdtest.presentation import export_guided_report

def main():
    f=ROOT/'examples/data/synthetic_variance_relaxation_independent.csv'
    r=mdtest.auto_compare(f,col=1,m_trend_grid=[2,5,10,20,40],m_corr_grid=[10,20,40,80,160,320],stride_points=None,ess_stride_points=None,ess_min_lag=3,ess_max_lag=None,write_outputs=False,make_plots=False)
    export_guided_report(r,ROOT/'examples/workbench_demo',prefix='variance_relaxation',level='guided',include_figures=True)
    print('start_SW',r.auto_safe.selected_start_index_sw)
    print('start_ESS',r.ess.selected_start_index_ess)
    print('combined',r.selected_start_index_star)
    print('g',r.ess.selected_g)
    print('version',mdtest.__version__)
if __name__=='__main__': main()
