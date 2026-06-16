# Data

## Introduction

Sourcing the right data is an important part of technoeconomic analysis. `technoeconomics-app` provides access to many useful datasets behind a common interface. That interface is simple - a `Dataset` is something that takes in arbitrary arguments, and returns either a single value, or a timeseries.

## Available datasets

We provide the following datasets out of the box:

<!-- TODO: make a nice table with name | inputs | outputs -->

- `Constant` - returns a timeseries with a constant value, useful for testing
- `Sinusoidal` - sinusoidal timeseries, useful for testing

## Adding a dataset

Creating a new `Dataset` is very simple. It's simply a Python [dataclass](https://docs.python.org/3/library/dataclasses.html) with a `compute()` method that returns either a `float` or a Pandas [`Series`](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.html). As a reference, look at the implementation of the `Sinusoidal` dataset:

```python
@dataclass(frozen=True)
class Sinusoidal(SeriesDataset):
    """A sine wave over the snapshots -- a stand-in for daily/seasonal shapes.

    The value at time ``t`` is ``mean + amplitude * sin(2*pi * (h - phase) /
    period)``, where ``h`` is the number of hours since the first snapshot.

    Attributes:
        mean: Baseline the wave oscillates around.
        amplitude: Peak deviation from ``mean``.
        period: Oscillation period in hours (e.g. ``24`` daily, ``8760`` yearly).
        phase: Horizontal shift in hours.
    """

    mean: float
    amplitude: float
    period: float = 24.0
    phase: float = 0.0

    def compute(self, snapshots: pd.DatetimeIndex) -> pd.Series:
        """Return the sine wave sampled at ``snapshots``."""
        hours = np.asarray(
            (snapshots - snapshots[0]) / pd.Timedelta(hours=1), dtype=float
        )
        values = self.mean + self.amplitude * np.sin(
            2 * np.pi * (hours - self.phase) / self.period
        )
        return pd.Series(values, index=snapshots)
```

Four important points to note here:

1. `@dataclass` decorator above the dataset class (`frozen=True` to make it immutable)
2. A class which inherits from `SeriesDataset` if it returns a timeseries (`pd.Series`) or from `ScalarDataset` if it returns a `float`
3. Arguments passed with `arg: TYPE` on top of the class declaration, as one does for a `dataclass`
4. The `compute(self, snapshots: pd.DatetimeIndex)` function. This is where the heavy lifting happens

`compute()` can do anything - download data from the Internet, read from disk, calculate things from an equation, run a complex simulation. It accepts a `pd.DatetimeIndex`, because the final goal is to pass the output of our dataset into a time-varying simulation. This simulation may be hourly over a year, or daily over a week. If you return a timeseries, obviously it has to have as many timesteps as the rest of the model. We enforce this by giving you an index. If you return a timeseries, it should use this index. If you return a single value, you can use the index to e.g. aggregate the data appropriately, but feel free to ignore it if you don't need it.

Some recommendations for writing your own `compute()`:

- **make it fast** if you want to play around with your optimisation by changing values and rerunning the model, this function may get called a lot. If you're downloading data from the Internet, or doing slow computations - implement some sort of cache. If you're calculating things, try to [vectorise](https://www.geeksforgeeks.org/numpy/vectorized-operations-in-numpy/) your operations, or use [Numba](https://numba.pydata.org/)

## Full dataset API

::: technoeconomics.data.base
