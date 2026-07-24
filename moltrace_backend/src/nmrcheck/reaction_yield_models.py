"""Repho R12 — yield/selectivity predictors: sklearn surrogate + optional GNN (math governed).

Two interchangeable backends behind one interface:

* :class:`SklearnSurrogatePredictor` — the **Phase-A fallback**, a GP (Matérn) on a deterministic
  condition featurisation. Core dependencies only (sklearn/numpy); always available; this is what
  runs in CI and on every unflagged deployment.
* :class:`TorchMPNNPredictor` — the **R12 heavy backend**: a compact message-passing network over
  RDKit molecular graphs concatenated with the condition vector, with **MC-Dropout uncertainty**
  (T stochastic passes → mean/std) for acquisition. Torch is a site-installed accelerator probed
  lazily — importing this module never imports torch, and constructing the predictor without
  torch raises :class:`~nmrcheck.reaction_ml.CapabilityUnavailableError` with the enablement hint.

Governance (the Phase-C contract): backend selection goes through
:func:`nmrcheck.reaction_ml.resolve_backend` — the GNN activates only when the flag is on, torch
is present, **and an R11 benchmark gate pass names the exact model version**. A predictor-level
comparison helper is provided (MAE / calibration, metric dominance via the frozen R9 comparator),
but predictor metrics alone are never activation evidence: the R11 evidence must come from the
full-loop benchmark, which includes the blocking safety-recall dimension. Weights live outside
git (``*.pt`` is gitignored); saved checkpoints carry a SHA-256 that load verifies — refuse on
mismatch.

Pure/deterministic: no DB / HTTP / clock; the torch path seeds explicitly.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import reaction_feedback, reaction_ml

ENGINE = "reaction_yield_models.v1"

YIELD_METRIC_DIRECTIONS: dict[str, str] = {
    "mae": "lower",
    "calibration_error": "lower",
}


# --------------------------------------------------------------------------- #
# Deterministic condition featurisation (shared by both backends).
# --------------------------------------------------------------------------- #
class ConditionFeaturizer:
    """Frozen one-hot (categorical) + passthrough (numeric) featurisation of condition dicts.

    The vocabulary is fixed at :meth:`fit` in sorted order, so the same training data produces the
    same feature layout on any machine. Anything the fitted layout cannot represent — an unseen
    categorical value, an absent key, a non-numeric value in a numeric column — encodes to zero
    for that feature and is recorded in :attr:`last_unknowns`: visible, never a crash, and never
    a fabricated condition that reads as a real observation.
    """

    def __init__(self) -> None:
        self.numeric_keys: list[str] = []
        self.categorical_vocab: dict[str, list[str]] = {}
        self.fitted = False
        self.last_unknowns: list[str] = []

    def fit(self, conditions: Sequence[Mapping[str, Any]]) -> ConditionFeaturizer:
        numeric: set[str] = set()
        categories: dict[str, set[str]] = {}
        for row in conditions:
            for key, value in row.items():
                name = str(key)
                if isinstance(value, bool):
                    categories.setdefault(name, set()).add(str(value))
                elif isinstance(value, (int, float)):
                    if not math.isfinite(float(value)):
                        raise ValueError(f"Non-finite numeric condition {name}={value!r}")
                    numeric.add(name)
                else:
                    categories.setdefault(name, set()).add(str(value))
        self.numeric_keys = sorted(numeric)
        self.categorical_vocab = {k: sorted(v) for k, v in sorted(categories.items())}
        self.fitted = True
        return self

    @property
    def width(self) -> int:
        return len(self.numeric_keys) + sum(len(v) for v in self.categorical_vocab.values())

    def transform(self, conditions: Mapping[str, Any]) -> list[float]:
        if not self.fitted:
            raise ValueError("ConditionFeaturizer is not fitted.")
        self.last_unknowns = []
        vector: list[float] = []
        for key in self.numeric_keys:
            value = conditions.get(key)
            if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                # Imputing 0.0 is strictly more dangerous here than in the categorical block:
                # 0.0 is a legitimate in-range value (0 degC), so a fabricated feature is
                # indistinguishable from a real observation and can collide with genuine training
                # rows — earning a near-perfect MAE for a run whose condition was never recorded.
                # It must be reported for exactly the reason the categorical branch below is.
                self.last_unknowns.append(
                    f"{key}=<missing>"
                    if key not in conditions
                    else f"{key}=<non-numeric:{value!r}>"
                )
                vector.append(0.0)
            else:
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError(f"Non-finite numeric condition {key}={value!r}")
                vector.append(number)
        for key, vocab in self.categorical_vocab.items():
            raw = conditions.get(key)
            label = str(raw) if raw is not None else None
            if label is None:
                # Absent encodes to the same all-zero block as an unseen value, so it must be
                # reported too — otherwise a silently-dropped condition looks like a clean one.
                self.last_unknowns.append(f"{key}=<missing>")
            elif label not in vocab:
                self.last_unknowns.append(f"{key}={label}")
            for candidate in vocab:
                vector.append(1.0 if label == candidate else 0.0)
        return vector

    def as_dict(self) -> dict[str, Any]:
        return {
            "numeric_keys": list(self.numeric_keys),
            "categorical_vocab": {k: list(v) for k, v in self.categorical_vocab.items()},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ConditionFeaturizer:
        featurizer = cls()
        featurizer.numeric_keys = [str(k) for k in payload.get("numeric_keys") or []]
        featurizer.categorical_vocab = {
            str(k): [str(x) for x in v]
            for k, v in dict(payload.get("categorical_vocab") or {}).items()
        }
        featurizer.fitted = True
        return featurizer


@dataclass
class YieldPrediction:
    mean: float
    std: float
    backend: str
    n_samples: int = 1
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mean": self.mean,
            "std": self.std,
            "backend": self.backend,
            "n_samples": self.n_samples,
            "warnings": list(self.warnings),
            "engine": ENGINE,
        }


def _validated_examples(examples: Sequence[YieldExample]) -> list[YieldExample]:
    """Reject non-finite targets before fitting.

    A NaN target propagates silently through every backend (kNN weighted mean, GP fit, torch
    loss) and emerges as a NaN prediction that compares False against every threshold — an
    unusable model that looks like a working one.
    """

    if not examples:
        raise ValueError("Cannot fit on zero examples.")
    for index, example in enumerate(examples):
        target = float(example.yield_percent)
        if not math.isfinite(target):
            raise ValueError(
                f"Example {index} has a non-finite yield_percent ({example.yield_percent!r})."
            )
    return list(examples)


@dataclass(frozen=True)
class YieldExample:
    """One training/eval example: conditions (+ optional structures) → observed yield %."""

    conditions: Mapping[str, Any]
    yield_percent: float
    reactants_smiles: tuple[str, ...] = ()
    products_smiles: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Phase-A fallbacks. The terminal fallback is ZERO-dependency (sklearn is itself optional in
# this codebase — reaction_bo degrades to a rule-based path the same way).
# --------------------------------------------------------------------------- #
class KNNSurrogatePredictor:
    """Deterministic distance-weighted k-NN over the condition featurisation.

    Pure stdlib — the terminal fallback that is *always* available, mirroring
    ``reaction_bo``'s ``rule_based_fallback`` when sklearn is not installed. Uncertainty is the
    weighted standard deviation of the neighbours' yields (with a small floor so a single-point
    neighbourhood never claims certainty).
    """

    backend_name = "knn_surrogate"

    def __init__(self, *, k: int = 5, std_floor: float = 2.0) -> None:
        self.k = k
        self.std_floor = std_floor
        self.featurizer = ConditionFeaturizer()
        self._points: list[tuple[list[float], float]] = []

    def fit(self, examples: Sequence[YieldExample]) -> KNNSurrogatePredictor:
        examples = _validated_examples(examples)
        self.featurizer.fit([example.conditions for example in examples])
        self._points = [
            (self.featurizer.transform(example.conditions), float(example.yield_percent))
            for example in examples
        ]
        return self

    def predict(self, conditions: Mapping[str, Any]) -> YieldPrediction:
        if not self._points:
            raise ValueError("Predictor is not fitted.")
        vector = self.featurizer.transform(conditions)
        warnings = (
            [f"unrepresented condition(s) encoded as zero: {self.featurizer.last_unknowns}"]
            if self.featurizer.last_unknowns
            else []
        )
        # Sort on (distance, target, index): distance ties would otherwise resolve by fit
        # order, making the k-boundary neighbours — and the prediction — order-dependent.
        scored = sorted(
            (
                (
                    math.sqrt(sum((a - b) ** 2 for a, b in zip(vector, point, strict=True))),
                    target,
                    index,
                )
                for index, (point, target) in enumerate(self._points)
            )
        )[: max(1, self.k)]
        scored = [(distance, target) for distance, target, _ in scored]
        weights = [1.0 / (distance + 1e-9) for distance, _ in scored]
        total = sum(weights)
        mean = sum(w * target for w, (_, target) in zip(weights, scored, strict=True)) / total
        variance = (
            sum(w * (target - mean) ** 2 for w, (_, target) in zip(weights, scored, strict=True))
            / total
        )
        return YieldPrediction(
            mean=mean,
            std=max(self.std_floor, math.sqrt(max(0.0, variance))),
            backend=self.backend_name,
            n_samples=len(scored),
            warnings=warnings,
        )


class SklearnSurrogatePredictor:
    """GP (Matérn 2.5) over the condition featurisation — used when sklearn is installed."""

    backend_name = "sklearn_gp_surrogate"

    def __init__(self, *, random_state: int = 20260615, std_floor: float = 1e-3) -> None:
        self.random_state = random_state
        self.std_floor = std_floor
        self.featurizer = ConditionFeaturizer()
        self._model: Any = None

    def fit(self, examples: Sequence[YieldExample]) -> SklearnSurrogatePredictor:
        examples = _validated_examples(examples)
        import numpy as np  # noqa: PLC0415  (core dep; local import keeps module import light)
        from sklearn.gaussian_process import GaussianProcessRegressor  # noqa: PLC0415
        from sklearn.gaussian_process.kernels import (  # noqa: PLC0415
            ConstantKernel,
            Matern,
            WhiteKernel,
        )

        self.featurizer.fit([example.conditions for example in examples])
        features = np.asarray(
            [self.featurizer.transform(example.conditions) for example in examples], dtype=float
        )
        targets = np.asarray([float(example.yield_percent) for example in examples], dtype=float)
        # WhiteKernel models observation noise: without it the GP interpolates replicated
        # conditions exactly and reports ~zero uncertainty on inherently noisy assay data.
        kernel = ConstantKernel(1.0) * Matern(nu=2.5) + WhiteKernel(noise_level=1.0)
        self._model = GaussianProcessRegressor(
            kernel=kernel,
            normalize_y=True,
            alpha=1e-6,
            random_state=self.random_state,
        ).fit(features, targets)
        return self

    def predict(self, conditions: Mapping[str, Any]) -> YieldPrediction:
        if self._model is None:
            raise ValueError("Predictor is not fitted.")
        import numpy as np  # noqa: PLC0415

        vector = np.asarray([self.featurizer.transform(conditions)], dtype=float)
        mean, std = self._model.predict(vector, return_std=True)
        warnings = (
            [f"unrepresented condition(s) encoded as zero: {self.featurizer.last_unknowns}"]
            if self.featurizer.last_unknowns
            else []
        )
        return YieldPrediction(
            mean=float(mean[0]),
            std=max(self.std_floor, float(std[0])),
            backend=self.backend_name,
            warnings=warnings,
        )


# --------------------------------------------------------------------------- #
# R12 heavy backend: compact MPNN + MC-Dropout (torch is a probed, lazy guest).
# --------------------------------------------------------------------------- #
_ATOM_FEATURES = 6  # Z, degree, formal charge, aromatic, in-ring, total Hs


def _meta_digest(meta: Mapping[str, Any]) -> str:
    """SHA-256 over the checkpoint metadata, excluding the digest field itself."""

    body = {k: meta[k] for k in sorted(meta) if k != "meta_sha256"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_torch():
    try:
        import torch  # noqa: PLC0415  (site-installed accelerator; never a core dependency)

        return torch
    except ImportError:
        return None


def _load_rdkit():
    try:
        from rdkit import Chem  # noqa: PLC0415

        return Chem
    except ImportError:
        return None


def _molecule_graph(
    chem: Any, smiles_list: Sequence[str]
) -> tuple[list[list[float]], list[tuple[int, int]]]:
    """Atom-feature rows + undirected edge list for the union of the given molecules."""

    atoms: list[list[float]] = []
    edges: list[tuple[int, int]] = []
    offset = 0
    for smiles in smiles_list:
        mol = chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Unparseable SMILES for graph featurisation: {smiles!r}")
        for atom in mol.GetAtoms():
            atoms.append(
                [
                    float(atom.GetAtomicNum()),
                    float(atom.GetDegree()),
                    float(atom.GetFormalCharge()),
                    1.0 if atom.GetIsAromatic() else 0.0,
                    1.0 if atom.IsInRing() else 0.0,
                    float(atom.GetTotalNumHs()),
                ]
            )
        for bond in mol.GetBonds():
            a = bond.GetBeginAtomIdx() + offset
            b = bond.GetEndAtomIdx() + offset
            edges.append((a, b))
            edges.append((b, a))
        offset = len(atoms)
    if not atoms:
        raise ValueError("No atoms to featurise.")
    return atoms, edges


def _build_mpnn(torch: Any, *, cond_dim: int, hidden: int, rounds: int, dropout: float):
    nn = torch.nn

    class _MPNN(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.embed = nn.Linear(_ATOM_FEATURES, hidden)
            self.message = nn.Linear(hidden, hidden)
            self.update = nn.GRUCell(hidden, hidden)
            self.rounds = rounds
            self.dropout = nn.Dropout(dropout)
            self.head = nn.Sequential(
                nn.Linear(hidden + cond_dim, hidden),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden, 1),
            )

        def forward(self, atom_features, edge_index, condition_vector):
            h = torch.relu(self.embed(atom_features))
            for _ in range(self.rounds):
                messages = torch.zeros_like(h)
                if edge_index.numel():
                    src, dst = edge_index[0], edge_index[1]
                    messages = messages.index_add(0, dst, self.message(h)[src])
                h = self.update(messages, h)
            pooled = self.dropout(h.mean(dim=0, keepdim=True))
            joined = torch.cat([pooled, condition_vector.unsqueeze(0)], dim=1)
            return self.head(joined).squeeze()

    return _MPNN()


class TorchMPNNPredictor:
    """Compact MPNN over molecular graphs + conditions, with MC-Dropout uncertainty.

    ``model.train()`` is kept on during prediction **deliberately** — that is what makes dropout
    stochastic for MC sampling (the architecture avoids BatchNorm for exactly this reason). The
    mean/std over ``mc_samples`` passes is the acquisition-facing uncertainty.
    """

    backend_name = "torch_mpnn_mc_dropout"

    def __init__(
        self,
        *,
        hidden: int = 64,
        rounds: int = 3,
        dropout: float = 0.2,
        epochs: int = 200,
        learning_rate: float = 1e-3,
        mc_samples: int = 20,
        seed: int = 20260615,
        model_version: str = "",
    ) -> None:
        torch = _load_torch()
        if torch is None:
            raise reaction_ml.CapabilityUnavailableError(
                "yield_gnn: torch is not installed. "
                + reaction_ml.CAPABILITIES["yield_gnn"].install_hint
            )
        chem = _load_rdkit()
        if chem is None:
            raise reaction_ml.CapabilityUnavailableError(
                "yield_gnn: rdkit is required for molecular-graph featurisation."
            )
        self._torch = torch
        self._chem = chem
        self.hidden = hidden
        self.rounds = rounds
        self.dropout = dropout
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.mc_samples = mc_samples
        self.seed = seed
        self.model_version = model_version
        self.featurizer = ConditionFeaturizer()
        self._model: Any = None

    # -- training ---------------------------------------------------------- #
    def fit(self, examples: Sequence[YieldExample]) -> TorchMPNNPredictor:
        examples = _validated_examples(examples)
        torch = self._torch
        torch.manual_seed(self.seed)
        self.featurizer.fit([example.conditions for example in examples])
        self._model = _build_mpnn(
            torch,
            cond_dim=self.featurizer.width,
            hidden=self.hidden,
            rounds=self.rounds,
            dropout=self.dropout,
        )
        optimizer = torch.optim.Adam(self._model.parameters(), lr=self.learning_rate)
        loss_fn = torch.nn.MSELoss()
        prepared = [self._prepare(example) for example in examples]
        targets = [
            torch.tensor(float(example.yield_percent) / 100.0) for example in examples
        ]
        self._model.train()
        for _ in range(self.epochs):
            for (atoms, edges, cond), target in zip(prepared, targets, strict=True):
                optimizer.zero_grad()
                prediction = self._model(atoms, edges, cond)
                loss = loss_fn(prediction, target)
                loss.backward()
                optimizer.step()
        return self

    def _prepare(self, example: YieldExample):
        torch = self._torch
        smiles = list(example.reactants_smiles) + list(example.products_smiles)
        if not smiles:
            # Condition-only rows still work: a single virtual atom carries no chemistry.
            atoms, edges = [[0.0] * _ATOM_FEATURES], []
        else:
            atoms, edges = _molecule_graph(self._chem, smiles)
        atom_tensor = torch.tensor(atoms, dtype=torch.float32)
        edge_tensor = (
            torch.tensor(list(zip(*edges, strict=True)), dtype=torch.long)
            if edges
            else torch.zeros((2, 0), dtype=torch.long)
        )
        cond_tensor = torch.tensor(
            self.featurizer.transform(example.conditions), dtype=torch.float32
        )
        return atom_tensor, edge_tensor, cond_tensor

    # -- prediction (MC-Dropout) ------------------------------------------- #
    def predict(self, example: YieldExample) -> YieldPrediction:
        if self._model is None:
            raise ValueError("Predictor is not fitted.")
        torch = self._torch
        atoms, edges, cond = self._prepare(example)
        self._model.train()  # deliberate: keeps dropout stochastic for MC sampling
        samples: list[float] = []
        with torch.no_grad():
            for index in range(self.mc_samples):
                torch.manual_seed(self.seed + index)  # reproducible MC draws
                samples.append(float(self._model(atoms, edges, cond)) * 100.0)
        mean = sum(samples) / len(samples)
        variance = sum((s - mean) ** 2 for s in samples) / max(1, len(samples) - 1)
        return YieldPrediction(
            mean=mean,
            std=math.sqrt(max(0.0, variance)),
            backend=self.backend_name,
            n_samples=len(samples),
        )

    # -- checkpointing (weights out of git; sha-verified) -------------------- #
    def save(self, directory: str | Path) -> dict[str, Any]:
        if self._model is None:
            raise ValueError("Nothing to save: predictor is not fitted.")
        torch = self._torch
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        weights_path = path / "mpnn.pt"
        torch.save(self._model.state_dict(), weights_path)
        weight_sha = hashlib.sha256(weights_path.read_bytes()).hexdigest()
        meta = {
            "engine": ENGINE,
            "backend": self.backend_name,
            "model_version": self.model_version,
            "hidden": self.hidden,
            "rounds": self.rounds,
            "dropout": self.dropout,
            "mc_samples": self.mc_samples,
            "seed": self.seed,
            "featurizer": self.featurizer.as_dict(),
            "weight_sha256": weight_sha,
        }
        # Seal the metadata too: the featurizer vocabulary and the weight digest itself live
        # here, so an unsealed meta.json lets an edited vocabulary (or a swapped digest) pass
        # a weights-only integrity check.
        meta["meta_sha256"] = _meta_digest(meta)
        (path / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
        # The checkpoint directory is caller-chosen, so a repo-root pattern cannot reliably
        # cover it. Drop a self-ignoring .gitignore beside the artifacts (the pip/poetry
        # convention): trained weights and their sealed metadata never enter git, wherever the
        # caller decided to write them.
        (path / ".gitignore").write_text("# Repho R12 checkpoint — never commit.\n*\n")
        return meta

    @classmethod
    def load(cls, directory: str | Path, *, expected_model_version: str | None = None):
        path = Path(directory)
        meta = json.loads((path / "meta.json").read_text())
        recorded_meta_sha = meta.get("meta_sha256")
        if recorded_meta_sha != _meta_digest(meta):
            raise reaction_ml.CapabilityUnavailableError(
                "yield_gnn: checkpoint integrity failure — meta.json digest mismatch; "
                "refusing to load."
            )
        weights_path = path / "mpnn.pt"
        actual_sha = hashlib.sha256(weights_path.read_bytes()).hexdigest()
        if actual_sha != meta.get("weight_sha256"):
            raise reaction_ml.CapabilityUnavailableError(
                "yield_gnn: checkpoint integrity failure — weight SHA-256 mismatch "
                f"({actual_sha} != {meta.get('weight_sha256')}); refusing to load."
            )
        # Governance binding: the promoted version must be the version being loaded.
        if expected_model_version is not None and (
                str(meta.get("model_version") or "") != expected_model_version
        ):
            raise reaction_ml.CapabilityUnavailableError(
                "yield_gnn: checkpoint model_version "
                f"{meta.get('model_version')!r} is not the promoted version "
                f"{expected_model_version!r}; refusing to load."
            )
        predictor = cls(
            hidden=int(meta["hidden"]),
            rounds=int(meta["rounds"]),
            dropout=float(meta["dropout"]),
            mc_samples=int(meta["mc_samples"]),
            seed=int(meta["seed"]),
        )
        predictor.model_version = str(meta.get("model_version") or "")
        predictor.featurizer = ConditionFeaturizer.from_dict(meta["featurizer"])
        predictor._model = _build_mpnn(
            predictor._torch,
            cond_dim=predictor.featurizer.width,
            hidden=predictor.hidden,
            rounds=predictor.rounds,
            dropout=predictor.dropout,
        )
        predictor._model.load_state_dict(
            predictor._torch.load(weights_path, weights_only=True)
        )
        return predictor


# --------------------------------------------------------------------------- #
# Governed backend selection + honest evaluation.
# --------------------------------------------------------------------------- #
def select_yield_predictor(
    *,
    promotion_evidence: Mapping[str, Any] | None = None,
    expected_gold_checksum: str | None = None,
    expected_model_version: str | None = None,
    probe: Any = None,
    env: Mapping[str, str] | None = None,
) -> tuple[Any, reaction_ml.BackendDecision]:
    """Instantiate the governed backend for yield prediction.

    Heavy (:class:`TorchMPNNPredictor`) only when flag + torch + R11 promotion evidence all hold;
    otherwise the fallback chain mirrors ``reaction_bo``: sklearn GP when sklearn is installed,
    else the zero-dependency :class:`KNNSurrogatePredictor`. The decision (with provenance,
    including which fallback was instantiated) is returned for the caller to persist.

    Pass ``expected_gold_checksum`` / ``expected_model_version`` to bind the evidence to the
    benchmark and the checkpoint actually being activated — without them a genuine gate pass
    earned by *some other* model on *some other* gold set would still unlock the heavy path.
    """

    decision = reaction_ml.resolve_backend(
        "yield_gnn",
        promotion_evidence=promotion_evidence,
        expected_gold_checksum=expected_gold_checksum,
        expected_model_version=expected_model_version,
        probe=probe,
        env=env,
    )
    if decision.backend == "heavy":
        return TorchMPNNPredictor(), decision
    import importlib.util  # noqa: PLC0415

    if importlib.util.find_spec("sklearn") is not None:
        predictor: Any = SklearnSurrogatePredictor()
    else:
        predictor = KNNSurrogatePredictor()
    decision.provenance["fallback_backend"] = predictor.backend_name
    return predictor, decision


def benchmark_yield_predictor(
    predictor: Any,
    examples: Sequence[YieldExample],
    *,
    tolerance: float = 5.0,
    bins: int = 5,
) -> dict[str, float]:
    """MAE + calibration error on held-out examples (predictor-level metrics only).

    Calibration compares the model's own claimed probability that its error is within
    ``tolerance`` (from the Gaussian predictive std: ``erf(tol / (std * sqrt(2)))``) against the
    empirical rate, binned — the standard ECE construction. These metrics feed the model card and
    the predictor-level comparison; **they are not activation evidence** (that requires the
    full-loop R11 gate, which includes the blocking safety-recall dimension).
    """

    if not examples:
        raise ValueError("Cannot benchmark on zero examples.")
    errors: list[float] = []
    pairs: list[tuple[float, bool]] = []
    for example in examples:
        prediction = (
            predictor.predict(example)
            if isinstance(predictor, TorchMPNNPredictor)
            else predictor.predict(example.conditions)
        )
        if not math.isfinite(prediction.mean) or not math.isfinite(prediction.std):
            raise ValueError(f"Non-finite prediction from {prediction.backend}: {prediction!r}")
        error = abs(prediction.mean - float(example.yield_percent))
        errors.append(error)
        if prediction.std <= 0:
            claimed = 1.0
        else:
            claimed = math.erf(tolerance / (prediction.std * math.sqrt(2.0)))
        pairs.append((max(0.0, min(1.0, claimed)), error <= tolerance))
    mae = sum(errors) / len(errors)

    grouped: dict[int, list[tuple[float, bool]]] = {}
    for confidence, accurate in pairs:
        index = min(bins - 1, int(confidence * bins))
        grouped.setdefault(index, []).append((confidence, accurate))
    ece = 0.0
    for bucket in grouped.values():
        mean_conf = sum(c for c, _ in bucket) / len(bucket)
        accuracy = sum(1 for _, a in bucket if a) / len(bucket)
        ece += (len(bucket) / len(pairs)) * abs(mean_conf - accuracy)
    return {"mae": mae, "calibration_error": ece}


def compare_yield_models(
    candidate_metrics: Mapping[str, float],
    incumbent_metrics: Mapping[str, float],
    *,
    tolerance: float = 0.0,
) -> tuple[bool, list[str]]:
    """Predictor-level metric dominance (MAE/ECE) via the frozen R9 comparator.

    Deliberately **not** a promotion verdict: it carries no safety dimension. Promotion evidence
    for registry activation must come from the full-loop R11 benchmark gate.
    """

    return reaction_feedback.dominates(
        dict(candidate_metrics),
        dict(incumbent_metrics),
        directions=YIELD_METRIC_DIRECTIONS,
        tolerance=tolerance,
    )
