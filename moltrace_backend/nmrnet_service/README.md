# NMRNet GPU inference microservice

The optional NMRNet backend for MolTrace's `predict_shifts(...)`, run as a
separate GPU service so the main backend stays torch-free. MolTrace talks to it
through `moltrace.spectroscopy.predict.nmrnet_client`.

> **Runtime:** Python 3.8 + CUDA 11.6 + torch 1.13.1 (Linux x86_64). This does
> **not** run in the main MolTrace venv (Python 3.14, macOS arm64) — it lives in
> its own box/container. That separation is the whole point.

## Deploy

1. **Provision a GPU box** (T4/L4/A10 is ample for inference), Ubuntu + CUDA 11.6,
   conda env at Python 3.8.

2. **Get NMRNet + weights**
   ```bash
   git clone https://github.com/Colin-Jay/NMRNet
   # download the checkpoint from Zenodo record 19142375 into NMRNet/weight/
   pip install torch==1.13.1+cu116 torchvision==0.14.1+cu116 \
     --extra-index-url https://download.pytorch.org/whl/cu116
   pip install ./unicore-0.0.1+cu116torch1.12.0-cp38-cp38-linux_x86_64.whl
   pip install -r requirements.txt
   ```

3. **Fill the two integration points in `app.py`** — `_load_model()` and
   `_run_inference()` — by transcribing the model build, dataset/collator, and
   forward pass from `NMRNet/demo/notebook/NMRNet.ipynb`. The recipe (verbatim
   cells) is documented at the top of `app.py`. Until they're filled the service
   raises `NotImplementedError` — it never returns fabricated shifts.

4. **Run**
   ```bash
   export MOLTRACE_NMRNET_WEIGHTS=/path/to/NMRNet/weight/checkpoint.pt
   uvicorn app:app --host 0.0.0.0 --port 8000
   curl localhost:8000/health    # {"ok": true}
   ```

## Point MolTrace at it

In the **main backend** environment:
```bash
export MOLTRACE_NMRNET_MODULE=moltrace.spectroscopy.predict.nmrnet_client
export MOLTRACE_NMRNET_SERVICE_URL=http://<gpu-host>:8000
```
`predict_shifts(...)` now routes to NMRNet; if the service is unset or
unreachable it transparently falls back to the HOSE predictor.

## Contract

```
POST /predict
request : {"symbols": ["C","C","H",...],
           "coordinates": [[x,y,z], ...],   # Å, one per atom, same order
           "nuclei": ["1H","13C"]}
response: {"shifts": {"<atom_index>": [predicted_ppm, uncertainty_ppm], ...}}
```

## Validating against the paper

Once live, set `MOLTRACE_NMRNET_WEIGHTS` (service side) and
`MOLTRACE_QM9NMR_PATH` (test side) and run
`tests/test_nmrnet_wrapper.py::test_nmrnet_qm9_mae_within_30pct_of_paper`. Use
`moltrace.spectroscopy.predict.qm9nmr` to convert QM9-NMR shielding σ → shift δ
(supply the per-nucleus linear reference your benchmark calibrates). **Confirm
which benchmark the paper's 0.181/1.098 ppm MAE refers to** (likely the
experimental nmrshiftdb2-2024 set, not QM9-NMR) and compare like-for-like.
