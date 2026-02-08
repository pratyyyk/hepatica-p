from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.inspection import permutation_importance

from .stage1_data import CLASS_ORDER
from .stage1_modeling import Stage1EvalBundle, Stage1Models


@dataclass
class LocalContribution:
    feature: str
    mean_abs_delta: float


def _sorted_importances(importances_mean: np.ndarray, feature_names: list[str]) -> list[dict[str, float]]:
    order = np.argsort(-np.abs(importances_mean))
    out: list[dict[str, float]] = []
    for idx in order:
        out.append(
            {
                "feature": feature_names[idx],
                "importance_mean": float(importances_mean[idx]),
                "importance_abs": float(abs(importances_mean[idx])),
            }
        )
    return out


def compute_global_importance(
    models: Stage1Models,
    eval_bundle: Stage1EvalBundle,
    random_state: int,
    n_repeats: int = 3,
    max_samples: int = 15000,
) -> dict[str, Any]:
    X = eval_bundle.X_transformed
    y_cls = eval_bundle.y_cls
    y_prob = eval_bundle.y_prob
    y_latent = eval_bundle.y_latent

    if max_samples > 0 and X.shape[0] > max_samples:
        rng = np.random.default_rng(random_state)
        idx = np.sort(rng.choice(np.arange(X.shape[0]), size=max_samples, replace=False))
        X = X[idx]
        y_cls = y_cls[idx]
        y_prob = y_prob[idx]
        y_latent = y_latent[idx]

    cls_imp = permutation_importance(
        models.classifier,
        X,
        y_cls,
        n_repeats=n_repeats,
        random_state=random_state,
        scoring="f1_macro",
        n_jobs=1,
    )

    prob_imp = permutation_importance(
        models.reg_probability,
        X,
        y_prob,
        n_repeats=n_repeats,
        random_state=random_state,
        scoring="neg_mean_absolute_error",
        n_jobs=1,
    )

    latent_imp = permutation_importance(
        models.reg_latent,
        X,
        y_latent,
        n_repeats=n_repeats,
        random_state=random_state,
        scoring="neg_mean_absolute_error",
        n_jobs=1,
    )

    return {
        "classifier_macro_f1": _sorted_importances(cls_imp.importances_mean, models.feature_names),
        "reg_probability_mae": _sorted_importances(prob_imp.importances_mean, models.feature_names),
        "reg_latent_mae": _sorted_importances(latent_imp.importances_mean, models.feature_names),
    }


def _leave_one_feature_out_delta(
    *,
    model,
    X_subset: np.ndarray,
    baseline: np.ndarray,
    predict_fn,
) -> np.ndarray:
    feature_count = X_subset.shape[1]
    base_pred = predict_fn(model, X_subset)
    out = np.zeros(feature_count, dtype=np.float64)
    for j in range(feature_count):
        modified = X_subset.copy()
        modified[:, j] = baseline[j]
        mod_pred = predict_fn(model, modified)
        out[j] = float(np.mean(np.abs(base_pred - mod_pred)))
    return out


def compute_local_class_summary(
    models: Stage1Models,
    eval_bundle: Stage1EvalBundle,
    top_n: int = 100,
) -> dict[str, Any]:
    probs = eval_bundle.pred_probs
    classes = models.classifier.classes_.tolist()
    pred_cls = eval_bundle.pred_cls

    summaries: dict[str, Any] = {}

    for cls in CLASS_ORDER:
        if cls not in classes:
            summaries[cls] = {"selected_count": 0, "top_features": []}
            continue

        class_idx = classes.index(cls)
        candidate_idx = np.where(pred_cls == cls)[0]
        if candidate_idx.size == 0:
            summaries[cls] = {"selected_count": 0, "top_features": []}
            continue

        confidence = probs[candidate_idx, class_idx]
        order = candidate_idx[np.argsort(-confidence)]
        selected = order[: min(top_n, order.size)]
        X_subset = eval_bundle.X_transformed[selected]

        deltas = _leave_one_feature_out_delta(
            model=models.classifier,
            X_subset=X_subset,
            baseline=models.feature_baseline,
            predict_fn=lambda m, x: m.predict_proba(x)[:, class_idx],
        )

        idx_sorted = np.argsort(-deltas)
        top_features = [
            {
                "feature": models.feature_names[idx],
                "mean_abs_delta": float(deltas[idx]),
            }
            for idx in idx_sorted[:20]
        ]

        summaries[cls] = {
            "selected_count": int(selected.size),
            "top_features": top_features,
        }

    return summaries


def compute_local_regression_summary(
    models: Stage1Models,
    eval_bundle: Stage1EvalBundle,
    top_n: int = 100,
) -> dict[str, Any]:
    out: dict[str, Any] = {}

    regression_views = {
        "probability_rule": (eval_bundle.y_prob, eval_bundle.pred_prob, models.reg_probability),
        "latent_fibrosis_score": (eval_bundle.y_latent, eval_bundle.pred_latent, models.reg_latent),
    }

    for target_name, (y_true, y_pred, model) in regression_views.items():
        residual = np.abs(y_true - y_pred)
        idx_sorted = np.argsort(-residual)
        high_idx = idx_sorted[: min(top_n, idx_sorted.size)]

        median_value = np.median(residual)
        median_idx = np.argsort(np.abs(residual - median_value))[: min(top_n, residual.size)]

        groups = {
            "high_residual": high_idx,
            "median_residual": median_idx,
        }

        group_payload: dict[str, Any] = {}
        for group_name, group_idx in groups.items():
            X_subset = eval_bundle.X_transformed[group_idx]
            deltas = _leave_one_feature_out_delta(
                model=model,
                X_subset=X_subset,
                baseline=models.feature_baseline,
                predict_fn=lambda m, x: m.predict(x),
            )

            idx_top = np.argsort(-deltas)
            top_features = [
                {
                    "feature": models.feature_names[idx],
                    "mean_abs_delta": float(deltas[idx]),
                }
                for idx in idx_top[:20]
            ]

            group_payload[group_name] = {
                "selected_count": int(group_idx.size),
                "top_features": top_features,
            }

        out[target_name] = group_payload

    return out
