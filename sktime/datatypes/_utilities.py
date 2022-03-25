# -*- coding: utf-8 -*-
# copyright: sktime developers, BSD-3-Clause License (see LICENSE file)
"""Eclectic utilities for the datatypes module."""

import numpy as np
import pandas as pd


def _get_index(x):
    if hasattr(x, "index"):
        return x.index
    else:
        # select last dimension for time index
        return pd.RangeIndex(x.shape[-1])


def get_time_index(X):
    """Get index of time series data, helper function.

    Parameters
    ----------
    X : pd.DataFrame / pd.Series / np.ndarray
    in one of the following sktime mtype specifications for Series, Panel, Hierarchical:
    pd.DataFrame, pd.Series, np.ndarray, pd-multiindex, nested_univ, pd_multiindex_hier
    assumes all time series have equal length and equal index set
    will *not* work for numpy3D, list-of-df, pd-wide, pd-long

    Returns
    -------
    time_index : pandas Index
        Index of time series
    """
    # assumes that all samples share the same the time index, only looks at
    # first row
    if isinstance(X, pd.DataFrame):
        if isinstance(X.index, pd.MultiIndex):
            return X.xs(
                X.index.get_level_values("instances")[0], level="instances"
            ).index
        else:
            return _get_index(X.iloc[0, 0])

    elif isinstance(X, pd.Series):
        if isinstance(X.index, pd.MultiIndex):
            return X.xs(
                X.index.get_level_values("instances")[0], level="instances"
            ).index
        else:
            return _get_index(X.iloc[0])

    elif isinstance(X, np.ndarray):
        return _get_index(X)

    else:
        raise ValueError(
            f"X must be a pandas DataFrame or Series, but found: {type(X)}"
        )


def get_index_for_series(obj, cutoff=0):
    """Get pandas index for a Series object.

    Returns index even for numpy array, in that case a RangeIndex.

    Assumptions on obj are not checked, these should be validated separately.
    Function may return unexpected results without prior validation.

    Parameters
    ----------
    obj : sktime data container
        must be of one of the following mtypes:
            pd.Series, pd.DataFrame, np.ndarray, of Series scitype
    cutoff : int, or pd.datetime, optional, default=0
        current cutoff, used to offset index if obj is np.ndarray

    -------
    index : pandas.Index, index for obj
    """
    if hasattr(obj, "index"):
        return obj.index
    # now we know the object must be an np.ndarray
    return pd.RangeIndex(cutoff, cutoff + obj.shape[0])


def get_cutoff(obj, cutoff=0, return_index=False):
    """Get cutoff = latest time point of time series or time series panel.

    Assumptions on obj are not checked, these should be validated separately.
    Function may return unexpected results without prior validation.

    Parameters
    ----------
    obj : sktime compatible time series data container
        must be of one of the following mtypes:
            pd.Series, pd.DataFrame, np.ndarray, of Series scitype
            pd.multiindex, numpy3D, nested_univ, df-list, of Panel scitype
            pd_multiindex_hier, of Hierarchical scitype
    cutoff : int, optional, default=0
        current cutoff, used to offset index if obj is np.ndarray
    return_index : bool, optional, default=False
        whether a pd.Index object should be returned (True)
            or a pandas compatible index element (False)
        note: return_index=True may set freq attribute of time types to None
            return_index=False will typically preserve freq attribute

    Returns
    -------
    cutoff_index : pandas compatible index element (if return_index=False)
        pd.Index of length 1 (if return_index=True)
    """
    if cutoff is None:
        cutoff = 0

    if len(obj) == 0:
        return cutoff

    # numpy3D (Panel) or np.npdarray (Series)
    if isinstance(obj, np.ndarray):
        if obj.ndim == 3:
            cutoff_ind = obj.shape[-1] + cutoff
        if obj.ndim < 3 and obj.ndim > 0:
            cutoff_ind = obj.shape[0] + cutoff
        if return_index:
            return pd.RangeIndex(cutoff_ind - 1, cutoff_ind)
        else:
            return cutoff_ind

    if isinstance(obj, pd.Series):
        return obj.index[[-1]] if return_index else obj.index[-1]

    # nested_univ (Panel) or pd.DataFrame(Series)
    if isinstance(obj, pd.DataFrame) and not isinstance(obj.index, pd.MultiIndex):
        objcols = [x for x in obj.columns if obj.dtypes[x] == "object"]
        # pd.DataFrame
        if len(objcols) == 0:
            return obj.index[[-1]] if return_index else obj.index[-1]
        # nested_univ
        else:
            if return_index:
                idxx = [x.index[[-1]] for col in objcols for x in obj[col]]
            else:
                idxx = [x.index[-1] for col in objcols for x in obj[col]]
            return max(idxx)

    # pd-multiindex (Panel) and pd_multiindex_hier (Hierarchical)
    if isinstance(obj, pd.DataFrame) and isinstance(obj.index, pd.MultiIndex):
        idx = obj.index
        series_idx = [obj.loc[x].index.get_level_values(-1) for x in idx.droplevel(-1)]
        if return_index:
            cutoffs = [x[[-1]] for x in series_idx]
        else:
            cutoffs = [x[-1] for x in series_idx]
        return max(cutoffs)

    # df-list (Panel)
    if isinstance(obj, list):
        if return_index:
            idxs = [x.index[[-1]] for x in obj]
        else:
            idxs = [x.index[-1] for x in obj]
        return max(idxs)


GET_LATEST_WINDOW_SUPPORTED_MTYPES = [
    "pd.DataFrame",
    "pd-multiindex",
    "pd_multiindex_hier",
    "np.ndarray",
    "numpy3D",
]


def get_window(obj, window_length=None, lag=0):
    """Slice obj to the time index window with given length and lag.

    Returns time series or time series panel with time indices
        strictly greater than cutoff - lag - window_length, and
        equal or less than cutoff - lag.
    Cutoff if of obj, as determined by get_cutoff.

    Parameters
    ----------
    obj : sktime compatible time series data container
        must be of one of the following mtypes:
            pd.Series, pd.DataFrame, np.ndarray, of Series scitype
            pd.multiindex, numpy3D, nested_univ, df-list, of Panel scitype
            pd_multiindex_hier, of Hierarchical scitype
    window_length : int or timedelta, optional, default=-inf
        must be int if obj is int indexed, timedelta if datetime indexed
        length of the window to slice to. Default = window of infinite size
    lag : int or timedelta, optional, default = 0
        must be int if obj is int indexed, timedelta if datetime indexed
        lag of the latest time in the window, with respect to cutoff of obj

    Returns
    -------
    obj sub-set to time indices in the semi-open interval
        (cutoff - window_length - lag, cutoff - lag)
    """
    from sktime.datatypes import check_is_scitype, convert_to

    if window_length is None:
        return obj

    valid, _, metadata = check_is_scitype(
        obj, scitype=["Series", "Panel", "Hierarchical"], return_metadata=True
    )
    if not valid:
        raise ValueError("obj must be of Series, Panel, or Hierarchical scitype")
    obj_in_mtype = metadata["mtype"]

    obj = convert_to(obj, GET_LATEST_WINDOW_SUPPORTED_MTYPES)

    # numpy3D (Panel) or np.npdarray (Series)
    if isinstance(obj, np.ndarray):
        obj_len = len(obj)
        window_start = max(-window_length - lag, -obj_len)
        window_end = max(-lag, 
        if window_end == 0:
            return obj[window_start:]
        else:
            return obj[window_start:window_end]

    # pd.DataFrame(Series), pd-multiindex (Panel) and pd_multiindex_hier (Hierarchical)
    if isinstance(obj, pd.DataFrame):
        cutoff = get_cutoff(obj)
        win_start_excl = cutoff - window_length - lag
        win_end_incl = cutoff - lag

        if not isinstance(obj.index, pd.MultiIndex):
            time_indices = obj.index
        else:
            time_indices = obj.index.get_level_values(-1)

        win_select = (time_indices > win_start_excl) & (time_indices <= win_end_incl)
        obj_subset = obj.iloc[win_select]

        return convert_to(obj_subset, obj_in_mtype)

    raise ValueError(
        "bug in get_latest_window, unreachable condition, ifs should be exhaustive"
    )
