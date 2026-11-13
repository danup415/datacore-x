"""Repository-relative paths for the real-data scripts.

DATA : raw datasets and MATLAB-extracted IMS features (not in the repository).
       Default <repo>/data; override with the DCX_DATA environment variable.
         <DATA>/raw/cwru     CWRU .mat files      (12k drive-end + normal baseline)
         <DATA>/raw/femto    FEMTO/PRONOSTIA      (Learning_set/, Full_Test_Set/ ...)
         <DATA>/ims_features_t*.csv   from matlab/vibration/ims_extract.m
RES  : pdm_realdata/results    FIG : pdm_realdata/figures
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
REPO = os.path.dirname(PKG)
DATA = os.environ.get("DCX_DATA", os.path.join(REPO, "data"))
RES = os.path.join(PKG, "results")
FIG = os.path.join(PKG, "figures")
os.makedirs(RES, exist_ok=True); os.makedirs(FIG, exist_ok=True)
