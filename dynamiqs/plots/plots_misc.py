from __future__ import annotations

from matplotlib.axes import Axes

from ..utils.tensor_types import ArrayLike, to_numpy
from .utils import colors, optax

__all__ = ['plot_pwc_pulse']


@optax
def plot_pwc_pulse(
    times: ArrayLike,
    values: ArrayLike,
    *,
    ax: Axes = None,
    ycenter: bool = True,
    real_color: str = colors['blue'],
    imag_color: str = colors['purple'],
):
    """Plot a piecewise-constant pulse.

    Warning:
        Documentation redaction in progress.

    Examples:
        >>> n = 20
        >>> times = np.linspace(0, 1.0, n+1)
        >>> values = dq.rand_complex(n, seed=42)
        >>> dq.plot_pwc_pulse(times, values)
        >>> renderfig('plot_pwc_pulse')

        ![plot_pwc_pulse](/figs-code/plot_pwc_pulse.png){.fig}
    """
    times = to_numpy(times)  # (n + 1)
    values = to_numpy(values)  # (n)

    # format times and values, for example:
    # times  = [0, 1, 2, 3] -> [0, 1, 1, 2, 2, 3]
    # values = [4, 5, 6]    -> [4, 4, 5, 5, 6, 6]
    times = times.repeat(2)[1:-1]  # (2n)
    values = values.repeat(2)  # (2n)

    # real part
    ax.plot(times, values.real, label='real', color=real_color, alpha=0.7)
    ax.fill_between(times, 0, values.real, color=real_color, alpha=0.2)

    # imaginary part
    ax.plot(times, values.imag, label='imag', color=imag_color, alpha=0.7)
    ax.fill_between(times, 0, values.imag, color=imag_color, alpha=0.2)

    ax.legend(loc='lower right')

    if ycenter:
        ymin, ymax = ax.get_ylim()
        ymax_abs = max(abs(ymin), abs(ymax))
        ax.set_ylim(ymin=-ymax_abs, ymax=ymax_abs)

    ax.set(xlim=(0, times[-1]))
