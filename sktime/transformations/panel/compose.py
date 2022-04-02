# -*- coding: utf-8 -*-
"""Meta Transformers module.

This module has meta-transformations that is build using the pre-existing
transformations as building blocks.
"""
from warnings import warn

import numpy as np
import pandas as pd

from deprecated.sphinx import deprecated
from scipy import sparse
from sklearn.base import clone
from sklearn.compose import ColumnTransformer as _ColumnTransformer

from sktime.datatypes._panel._convert import (
    from_2d_array_to_nested,
    from_3d_numpy_to_2d_array,
    from_nested_to_2d_array,
)
from sktime.transformations.base import (
    BaseTransformer,
    _PanelToPanelTransformer,
    _PanelToTabularTransformer,
)
from sktime.utils.validation.panel import check_X

__author__ = ["Markus Löning", "Sajay Ganesh"]
__all__ = [
    "ColumnTransformer",
    "SeriesToPrimitivesRowTransformer",
    "SeriesToSeriesRowTransformer",
    "ColumnConcatenator",
]


class ColumnTransformer(_ColumnTransformer, _PanelToPanelTransformer):
    """Column-wise application of transformers.

    Applies transformations to columns of an array or pandas DataFrame. Simply
    takes the column transformer from sklearn
    and adds capability to handle pandas dataframe.

    This estimator allows different columns or column subsets of the input
    to be transformed separately and the features generated by each transformer
    will be concatenated to form a single feature space.
    This is useful for heterogeneous or columnar data, to combine several
    feature extraction mechanisms or transformations into a single transformer.

    Parameters
    ----------
    transformers : list of tuples
        List of (name, transformer, column(s)) tuples specifying the
        transformer objects to be applied to subsets of the data.
        name : string
            Like in Pipeline and FeatureUnion, this allows the transformer and
            its parameters to be set using ``set_params`` and searched in grid
            search.
        transformer : estimator or {"passthrough", "drop"}
            Estimator must support `fit` and `transform`. Special-cased
            strings "drop" and "passthrough" are accepted as well, to
            indicate to drop the columns or to pass them through untransformed,
            respectively.
        column(s) : str or int, array-like of string or int, slice, boolean
        mask array or callable
            Indexes the data on its second axis. Integers are interpreted as
            positional columns, while strings can reference DataFrame columns
            by name.  A scalar string or int should be used where
            ``transformer`` expects X to be a 1d array-like (vector),
            otherwise a 2d array will be passed to the transformer.
            A callable is passed the input data `X` and can return any of the
            above.
    remainder : {"drop", "passthrough"} or estimator, default "drop"
        By default, only the specified columns in `transformations` are
        transformed and combined in the output, and the non-specified
        columns are dropped. (default of ``"drop"``).
        By specifying ``remainder="passthrough"``, all remaining columns that
        were not specified in `transformations` will be automatically passed
        through. This subset of columns is concatenated with the output of
        the transformations.
        By setting ``remainder`` to be an estimator, the remaining
        non-specified columns will use the ``remainder`` estimator. The
        estimator must support `fit` and `transform`.
    sparse_threshold : float, default = 0.3
        If the output of the different transformations contains sparse matrices,
        these will be stacked as a sparse matrix if the overall density is
        lower than this value. Use ``sparse_threshold=0`` to always return
        dense.  When the transformed output consists of all dense data, the
        stacked result will be dense, and this keyword will be ignored.
    n_jobs : int or None, optional (default=None)
        Number of jobs to run in parallel.
        ``None`` means 1 unless in a :obj:`joblib.parallel_backend` context.
        ``-1`` means using all processors.
    transformer_weights : dict, optional
        Multiplicative weights for features per transformer. The output of the
        transformer is multiplied by these weights. Keys are transformer names,
        values the weights.
    preserve_dataframe : boolean
        If True, pandas dataframe is returned.
        If False, numpy array is returned.


    Attributes
    ----------
    transformers_ : list
        The collection of fitted transformations as tuples of
        (name, fitted_transformer, column). `fitted_transformer` can be an
        estimator, "drop", or "passthrough". In case there were no columns
        selected, this will be the unfitted transformer.
        If there are remaining columns, the final element is a tuple of the
        form:
        ("remainder", transformer, remaining_columns) corresponding to the
        ``remainder`` parameter. If there are remaining columns, then
        ``len(transformers_)==len(transformations)+1``, otherwise
        ``len(transformers_)==len(transformations)``.
    named_transformers_ : Bunch object, a dictionary with attribute access
        Read-only attribute to access any transformer by given name.
        Keys are transformer names and values are the fitted transformer
        objects.
    sparse_output_ : bool
        Boolean flag indicating wether the output of ``transform`` is a
        sparse matrix or a dense numpy array, which depends on the output
        of the individual transformations and the `sparse_threshold` keyword.
    """

    _required_parameters = ["transformers"]

    def __init__(
        self,
        transformers,
        remainder="drop",
        sparse_threshold=0.3,
        n_jobs=1,
        transformer_weights=None,
        preserve_dataframe=True,
    ):
        super(ColumnTransformer, self).__init__(
            transformers=transformers,
            remainder=remainder,
            sparse_threshold=sparse_threshold,
            n_jobs=n_jobs,
            transformer_weights=transformer_weights,
        )
        self.preserve_dataframe = preserve_dataframe
        self._is_fitted = False

    def _hstack(self, Xs):
        """
        Stacks X horizontally.

        Supports input types (X): list of numpy arrays, sparse arrays and
        DataFrames
        """
        types = set(type(X) for X in Xs)

        if self.sparse_output_:
            return sparse.hstack(Xs).tocsr()
        if self.preserve_dataframe and (pd.Series in types or pd.DataFrame in types):
            return pd.concat(Xs, axis="columns")
        return np.hstack(Xs)

    def _validate_output(self, result):
        """Validate output of every transformer.

        Ensure that the output of each transformer is 2D. Otherwise
        hstack can raise an error or produce incorrect results.

        Output can also be a pd.Series which is actually a 1D
        """
        names = [
            name for name, _, _, _ in self._iter(fitted=True, replace_strings=True)
        ]
        for Xs, name in zip(result, names):
            if not (getattr(Xs, "ndim", 0) == 2 or isinstance(Xs, pd.Series)):
                raise ValueError(
                    "The output of the '{0}' transformer should be 2D (scipy "
                    "matrix, array, or pandas DataFrame).".format(name)
                )

    def fit(self, X, y=None):
        """Fit the transformer."""
        X = check_X(X, coerce_to_pandas=True)
        super(ColumnTransformer, self).fit(X, y)
        self._is_fitted = True
        return self

    def transform(self, X, y=None):
        """Transform the data."""
        self.check_is_fitted()
        X = check_X(X, coerce_to_pandas=True)
        return super(ColumnTransformer, self).transform(X)

    def fit_transform(self, X, y=None):
        """Fit and transform, shorthand."""
        # Wrap fit_transform to set _is_fitted attribute
        Xt = super(ColumnTransformer, self).fit_transform(X, y)
        self._is_fitted = True
        return Xt


class ColumnConcatenator(_PanelToPanelTransformer):
    """Concatenate multivariate series to a long univariate series.

    Transformer that concatenates multivariate time series/panel data
    into long univariate time series/panel
        data by simply concatenating times series in time.
    """

    def transform(self, X, y=None):
        """Transform the data.

        Concatenate multivariate time series/panel data into long
        univariate time series/panel
        data by simply concatenating times series in time.

        Parameters
        ----------
        X : nested pandas DataFrame of shape [n_samples, n_features]
            Nested dataframe with time-series in cells.

        Returns
        -------
        Xt : pandas DataFrame
          Transformed pandas DataFrame with same number of rows and single
          column
        """
        self.check_is_fitted()
        X = check_X(X)

        # We concatenate by tabularizing all columns and then detabularizing
        # them into a single column
        if isinstance(X, pd.DataFrame):
            Xt = from_nested_to_2d_array(X)
        else:
            Xt = from_3d_numpy_to_2d_array(X)
        return from_2d_array_to_nested(Xt)


row_trafo_deprec_msg = (
    "All row transformers are deprecated since 0.12.0 and will be removed "
    "in 0.13.0. Vectorization functionality from Series to Panel is natively "
    "integrated to all transformers via the base class. Simply use fit "
    "or transform on Panel data, no row transformer is necessary anymore."
)


class _RowTransformer(BaseTransformer):
    """Base class for RowTransformer."""

    _required_parameters = ["transformer"]

    def __init__(self, transformer):

        warn(row_trafo_deprec_msg)

        self.transformer = transformer
        self.transformer_ = clone(transformer)
        super(_RowTransformer, self).__init__()
        self.clone_tags(transformer)

    def _fit(self, *args, **kwargs):
        """Transform the data."""
        return self.transformer_._fit(*args, **kwargs)

    def _transform(self, *args, **kwargs):
        """Transform the data."""
        return self.transformer_._transform(*args, **kwargs)

    def _inverse_transform(self, *args, **kwargs):
        """Transform the data."""
        return self.transformer_._inverse_transform(*args, **kwargs)

    def _update(self, *args, **kwargs):
        """Transform the data."""
        return self.transformer_._update(*args, **kwargs)

    def get_test_params(cls):
        """Return testing parameter settings for the estimator."""
        from sktime.transformations.series.exponent import ExponentTransformer

        params = {"transformer": ExponentTransformer()}
        return params


class SeriesToPrimitivesRowTransformer(_RowTransformer, _PanelToTabularTransformer):
    """Series-to-primitives row transformer."""


class SeriesToSeriesRowTransformer(_RowTransformer, _PanelToPanelTransformer):
    """Series-to-series row transformer."""


msg = "Vectorization is now natively integrated in BaseTransform, simply "


@deprecated(version="0.13.0", reason=row_trafo_deprec_msg, category=FutureWarning)
def make_row_transformer(transformer, transformer_type=None, **kwargs):
    """Old vectorization utility for transformers for panel data.

    This is now integrated into BaseTransformer, so no longer needed.

    Deprecated from version 0.12.0, will be removed in 0.13.0.

    Returns
    -------
    transformer, reference to input `transformer` (unchanged)
    """
    return transformer
