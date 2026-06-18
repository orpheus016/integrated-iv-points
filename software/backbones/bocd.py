"""Bayesian Online Changepoint Detection (BOCD) snapshot backbone.

Adapts the Adams & MacKay 2007 algorithm to the streaming BaseBackbone interface.
This implementation adds **best-plateau selection**: all stable plateaus detected
during a recording session are ranked by run-length, and the longest one is
exposed via the ``best_snapshot`` property.

Signal polarity is handled automatically: the Gaussian model operates on
``abs(voltage)`` so that an instrumentation-amplifier polarity flip
(e.g. -0.95 V instead of +0.95 V) is treated as equally valid.  The original
signed voltage is always stored in the emitted ``Snapshot``.

References
----------
- Adams & MacKay 2007, "Bayesian Online Changepoint Detection"
  https://arxiv.org/abs/0710.3742
- Murphy 2007, "Conjugate Bayesian analysis of the Gaussian distribution"
  https://www.cs.ubc.ca/~murphyk/Papers/bayesGauss.pdf
- Original Python reference by Gregory Gundersen
  http://gregorygundersen.com/blog/2019/08/13/bocd/
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np
from scipy.special import logsumexp  # type: ignore[import]

from .base import BaseBackbone
from ..utils.math import compute_resistance_ohm
from ..utils.types import Sample, Snapshot


# ---------------------------------------------------------------------------
# Internal conjugate model: Gaussian with unknown mean, known variance
# ---------------------------------------------------------------------------

class _GaussianUnknownMean:
    """Online sufficient-statistic accumulator for a Normal-Normal conjugate model.

    Operates on ``abs(voltage)`` so polarity flips are transparent to the
    changepoint detector.

    The internal param arrays grow by one entry per time step (one per active
    run-length hypothesis).  When the caller prunes low-probability hypotheses it
    must call ``prune(mask)`` so the param arrays stay aligned with
    ``log_message``.

    Args:
        mean0: Prior mean on the signal magnitude.
        var0:  Prior variance on the signal mean.
        varx:  Known observation noise variance.
    """

    def __init__(self, mean0: float, var0: float, varx: float) -> None:
        self._mean0 = mean0
        self._var0 = var0
        self._varx = varx
        # Index 0 = run-length 0 (the reset / changepoint hypothesis).
        self._mean_params: np.ndarray = np.array([mean0])
        self._prec_params: np.ndarray = np.array([1.0 / var0])

    def log_pred_prob(self, abs_v: float) -> np.ndarray:
        """Predictive log-probability for each active run-length hypothesis.

        The size of the returned array matches the current ``_mean_params``
        length and therefore the current ``log_message`` length.

        Args:
            abs_v: Absolute value of the new scalar observation.

        Returns:
            1-D array of log-probabilities, one per active hypothesis.
        """
        post_stds = np.sqrt(1.0 / self._prec_params + self._varx)
        return (
            -0.5 * np.log(2.0 * math.pi * post_stds ** 2)
            - 0.5 * ((abs_v - self._mean_params) ** 2) / (post_stds ** 2)
        )

    def update_params(self, abs_v: float) -> None:
        """Absorb a new observation and prepend the run-length-0 prior.

        After this call the arrays are one element longer than before: index 0
        is the fresh-start prior and indices 1..n are the updated run-length
        hypotheses.

        Args:
            abs_v: Absolute value of the new scalar observation.
        """
        new_prec = self._prec_params + (1.0 / self._varx)
        new_mean = (self._mean_params * self._prec_params + abs_v / self._varx) / new_prec

        # Prepend the run-length-0 (reset) prior.
        self._prec_params = np.concatenate([[1.0 / self._var0], new_prec])
        self._mean_params = np.concatenate([[self._mean0], new_mean])

    def prune(self, mask: np.ndarray) -> None:
        """Discard param rows corresponding to pruned hypotheses.

        Args:
            mask: Boolean array aligned with the current ``_mean_params``.
                  ``True`` = keep, ``False`` = drop.
        """
        self._mean_params = self._mean_params[mask]
        self._prec_params = self._prec_params[mask]

    @property
    def current_mean(self) -> float:
        """MAP posterior mean (last element = longest active run)."""
        return float(self._mean_params[-1])

    @property
    def current_var(self) -> float:
        """MAP posterior variance of the longest active run."""
        return float(1.0 / self._prec_params[-1] + self._varx)


# ---------------------------------------------------------------------------
# Streaming BOCD backbone
# ---------------------------------------------------------------------------

class BochdBackbone(BaseBackbone):
    """Streaming BOCD snapshot backbone with best-plateau selection.

    Applies Bayesian Online Changepoint Detection (Adams & MacKay 2007) to the
    incoming voltage stream using ``abs(voltage)`` so instrumentation-amplifier
    polarity flips are transparent.

    Plateau tracking
    ~~~~~~~~~~~~~~~~
    Each time the MAP run-length drops from >= ``min_stable_samples`` to below
    ``cp_reset_threshold`` a plateau is *sealed*: a Snapshot is emitted from
    ``update()`` and the ``(run_length, snapshot)`` pair is stored internally.
    After the stream ends, ``best_snapshot`` returns the sealed candidate with
    the longest run-length.  If the stream ends while a plateau is still active
    (no changepoint ever fires), the active run is sealed on the first access to
    ``best_snapshot``.

    Args:
        min_stable_samples:    Run-length that must be reached before a plateau
                               is considered valid for snapshotting.
        min_recording_samples: Minimum total samples ingested before any plateau
                               can be sealed.
        hazard_rate:           Constant prior on changepoint probability per step.
                               Default 1/200 → expect a changepoint every 200 samples.
        mean0:                 Prior mean on the signal magnitude.
        var0:                  Prior variance on the signal mean.
        varx:                  Assumed observation noise variance.
        prune_threshold:       Log-probability below which run-length hypotheses
                               are dropped to bound memory.
        cp_reset_threshold:    MAP run-length must fall below this value to confirm
                               a changepoint and seal the current plateau.  Default 5.
        gain:                  Gain correction for resistance calculation.
    """

    def __init__(
        self,
        min_stable_samples: int = 10,
        min_recording_samples: int = 1,
        hazard_rate: float = 1.0 / 200.0,
        mean0: float = 0.0,
        var0: float = 1.0,
        varx: float = 1e-6,
        prune_threshold: float = -50.0,
        cp_reset_threshold: int = 5,
        gain: float = 1.0,
    ) -> None:
        super().__init__(min_recording_samples=min_recording_samples)
        if min_stable_samples < 1:
            raise ValueError("min_stable_samples must be >= 1")
        if not (0.0 < hazard_rate < 1.0):
            raise ValueError("hazard_rate must be in (0, 1)")
        if var0 <= 0.0:
            raise ValueError("var0 must be > 0")
        if varx <= 0.0:
            raise ValueError("varx must be > 0")
        if cp_reset_threshold < 1:
            raise ValueError("cp_reset_threshold must be >= 1")

        self._min_stable_samples = min_stable_samples
        self._hazard_rate = hazard_rate
        self._log_H = math.log(hazard_rate)
        self._log_1mH = math.log(1.0 - hazard_rate)
        self._mean0 = mean0
        self._var0 = var0
        self._varx = varx
        self._prune_threshold = prune_threshold
        self._cp_reset_threshold = cp_reset_threshold
        self._gain = gain

        # BOCD state
        self._model = _GaussianUnknownMean(mean0, var0, varx)
        self._log_message: np.ndarray = np.array([0.0])

        # Plateau tracking
        self._prev_run_length: int = 0
        # Snapshot + raw voltage accumulated during the current active plateau
        self._plateau_snapshot: Optional[Snapshot] = None
        self._plateau_raw_voltage: float = 0.0
        self._plateau_run_length: int = 0
        # Sealed candidates: (run_length, snapshot)
        self._candidates: List[Tuple[int, Snapshot]] = []
        # Whether best_snapshot has already sealed the active run
        self._stream_sealed: bool = False

    # ------------------------------------------------------------------
    # BaseBackbone interface
    # ------------------------------------------------------------------

    def update(self, sample: Sample) -> Optional[Snapshot]:
        """Process one streaming sample and seal a plateau on changepoint.

        The method applies one step of the BOCD forward algorithm. It continuously
        returns a ``Snapshot`` while the MAP run-length remains >= ``min_stable_samples``.
        When a changepoint is confirmed (run-length falls below ``cp_reset_threshold``),
        the active plateau is sealed for offline comparison, and the method returns ``None``.

        Args:
            sample: ``(timestamp, voltage, current_mA)`` triple.

        Returns:
            A frozen :class:`~software.utils.types.Snapshot` when the signal is
            stable, or ``None`` if it is unstable.
        """
        timestamp, voltage, current_mA = sample
        self._mark_sample()
        abs_v = abs(voltage)

        # 1. Evaluate predictive log-probabilities using CURRENT params
        #    (one entry per active hypothesis, matching _log_message length).
        log_pis = self._model.log_pred_prob(abs_v)

        # 2. Growth probabilities (no changepoint, run grows by 1).
        log_growth_probs = log_pis + self._log_message + self._log_1mH

        # 3. Changepoint probability (run resets to 0).
        log_cp_prob = float(logsumexp(log_pis + self._log_message + self._log_H))

        # 4. New joint: element 0 = changepoint, elements 1..n = growth.
        new_log_joint = np.concatenate([[log_cp_prob], log_growth_probs])

        # 5. Normalise.
        log_sum = float(logsumexp(new_log_joint))
        new_log_joint -= log_sum

        # 6. Update conjugate model (grows params by 1, matching new_log_joint).
        self._model.update_params(abs_v)

        # 7. Prune low-probability hypotheses from BOTH the joint and the model.
        mask = new_log_joint > self._prune_threshold
        new_log_joint = new_log_joint[mask]
        self._model.prune(mask)

        # 8. Store message for next step.
        self._log_message = new_log_joint

        # 9. Current MAP run-length (argmax of the pruned posterior).
        current_run_length = int(np.argmax(new_log_joint))

        # 10. Update the active plateau candidate if stable enough.
        if current_run_length >= self._min_stable_samples and self._has_min_recording():
            # Keep track of the most-representative sample for this plateau
            # (the one at peak run-length — most confident estimate).
            if current_run_length > self._plateau_run_length:
                self._plateau_run_length = current_run_length
                self._plateau_raw_voltage = voltage
                mean_v = self._model.current_mean
                std_v = math.sqrt(max(0.0, self._model.current_var))
                resistance = compute_resistance_ohm(abs_v, current_mA, self._gain)
                self._plateau_snapshot = Snapshot(
                    timestamp=timestamp,
                    voltage=voltage,          # original sign preserved
                    current_mA=current_mA,
                    resistance=resistance,
                    std_dev=std_v,
                    best_run_length=current_run_length,
                )

        # 11. Detect changepoint: run-length was high, now collapsed.
        if (
            self._prev_run_length >= self._min_stable_samples
            and current_run_length < self._cp_reset_threshold
            and self._plateau_snapshot is not None
        ):
            sealed_snapshot = self._plateau_snapshot
            self._candidates.append((self._plateau_run_length, sealed_snapshot))
            self._plateau_snapshot = None
            self._plateau_run_length = 0

        self._prev_run_length = current_run_length

        # 12. Return live snapshot if currently stable
        if current_run_length >= self._min_stable_samples and self._plateau_snapshot is not None:
            return self._plateau_snapshot
        return None

    def reset(self) -> None:
        """Reset internal BOCD state for a new measurement stage.

        Any active plateau that was >= ``min_stable_samples`` is sealed into
        the candidates list before state is cleared, so ``best_snapshot`` is
        not lost across a stage transition.
        """
        self._seal_active_run()
        self._model = _GaussianUnknownMean(self._mean0, self._var0, self._varx)
        self._log_message = np.array([0.0])
        self._prev_run_length = 0
        self._plateau_snapshot = None
        self._plateau_raw_voltage = 0.0
        self._plateau_run_length = 0
        self._stream_sealed = False
        self._samples_seen = 0

    # ------------------------------------------------------------------
    # Diagnostic / result properties
    # ------------------------------------------------------------------

    @property
    def best_snapshot(self) -> Optional[Snapshot]:
        """The Snapshot from the longest stable plateau seen so far.

        On first access after the stream has ended (or if called before a
        final changepoint fires), any active run >= ``min_stable_samples`` is
        sealed into the candidates list before selecting the winner.

        Returns:
            The highest-run-length ``Snapshot``, or ``None`` if no stable
            plateau was ever reached.
        """
        if not self._stream_sealed:
            self._seal_active_run()
            self._stream_sealed = True

        if not self._candidates:
            return None
        # Return the snapshot whose run_length is the maximum.
        return max(self._candidates, key=lambda pair: pair[0])[1]

    @property
    def most_probable_run_length(self) -> int:
        """Current MAP estimate of the run length."""
        return int(np.argmax(self._log_message))

    @property
    def candidate_count(self) -> int:
        """Number of sealed plateau candidates accumulated so far."""
        return len(self._candidates)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _seal_active_run(self) -> None:
        """Seal the current active plateau into candidates if stable enough."""
        if (
            self._plateau_snapshot is not None
            and self._plateau_run_length >= self._min_stable_samples
        ):
            self._candidates.append((self._plateau_run_length, self._plateau_snapshot))
            self._plateau_snapshot = None
            self._plateau_run_length = 0