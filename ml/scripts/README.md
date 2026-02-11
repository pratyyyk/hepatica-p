# ml/scripts

Training/evaluation entry points.

Stage 1:
- `train_stage1.py`
- `evaluate_stage1.py`
- `register_stage1_model.py`

Stage 2:
- `train.py`
- `evaluate.py`

Stage 3:
- `generate_stage3_synthetic.py`
- `train_stage3.py`
- `register_stage3_model.py`

Reason: CLI scripts are the primary "operator interface" for producing artifacts consumed by the backend.
