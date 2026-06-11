"""
Table-level structural transforms: join, union, aggregate, pivot, unpivot, lookup.
Multi-DataFrame transforms receive a dict of named DataFrames via config['inputs'].
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.transforms.base import BaseTransform, TransformError
from layer2_pipeline.transforms.registry import register


class InnerJoin(BaseTransform):
    """
    Inner join the primary DataFrame with a named secondary DataFrame.
    The secondary DataFrame must be provided in context-level 'named_frames' dict.
    """

    transform_type = "inner_join"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        right_name = config["right_frame"]
        on = config.get("on")
        left_on = config.get("left_on")
        right_on = config.get("right_on")
        suffixes = tuple(config.get("suffixes", ("_left", "_right")))

        named_frames: dict[str, pd.DataFrame] = config.get("_named_frames", {})
        if right_name not in named_frames:
            raise TransformError(f"inner_join: named frame {right_name!r} not available")
        right = named_frames[right_name]

        join_kwargs: dict[str, Any] = {"how": "inner", "suffixes": suffixes}
        if on:
            join_kwargs["on"] = on
        elif left_on and right_on:
            join_kwargs["left_on"] = left_on
            join_kwargs["right_on"] = right_on
        else:
            raise TransformError("inner_join: 'on' or 'left_on'+'right_on' required")

        return df.merge(right, **join_kwargs).reset_index(drop=True)


class LeftJoin(BaseTransform):
    """Left join with a named secondary DataFrame."""

    transform_type = "left_join"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        right_name = config["right_frame"]
        on = config.get("on")
        left_on = config.get("left_on")
        right_on = config.get("right_on")
        suffixes = tuple(config.get("suffixes", ("", "_right")))

        named_frames: dict[str, pd.DataFrame] = config.get("_named_frames", {})
        if right_name not in named_frames:
            raise TransformError(f"left_join: named frame {right_name!r} not available")
        right = named_frames[right_name]

        join_kwargs: dict[str, Any] = {"how": "left", "suffixes": suffixes}
        if on:
            join_kwargs["on"] = on
        elif left_on and right_on:
            join_kwargs["left_on"] = left_on
            join_kwargs["right_on"] = right_on
        else:
            raise TransformError("left_join: 'on' or 'left_on'+'right_on' required")

        return df.merge(right, **join_kwargs).reset_index(drop=True)


class Union(BaseTransform):
    """
    Stack the primary DataFrame with one or more named DataFrames.
    Columns are aligned; missing columns are filled with NaN.
    """

    transform_type = "union"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        other_names: list[str] = config.get("frames", [])
        named_frames: dict[str, pd.DataFrame] = config.get("_named_frames", {})
        frames = [df]
        for name in other_names:
            if name not in named_frames:
                raise TransformError(f"union: named frame {name!r} not available")
            frames.append(named_frames[name])
        return pd.concat(frames, ignore_index=True)


class Aggregate(BaseTransform):
    """
    Group-by aggregation.
    config:
      group_by: [col1, col2]
      aggregations: {col: agg_func, ...}  # agg_func: sum|mean|count|min|max|first|last|nunique
    """

    transform_type = "aggregate"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        group_by: list[str] = config.get("group_by", [])
        aggregations: dict[str, str] = config.get("aggregations", {})
        if not group_by:
            raise TransformError("aggregate: 'group_by' is required")
        if not aggregations:
            raise TransformError("aggregate: 'aggregations' is required")
        missing = [c for c in group_by if c not in df.columns]
        if missing:
            raise TransformError(f"aggregate: group_by columns not found: {missing}")
        result = df.groupby(group_by, as_index=False).agg(aggregations)
        # Flatten MultiIndex columns if any
        if isinstance(result.columns, pd.MultiIndex):
            result.columns = ["_".join(filter(None, c)) for c in result.columns]
        return result.reset_index(drop=True)

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        errors = []
        if not config.get("group_by"):
            errors.append("aggregate: 'group_by' is required")
        if not config.get("aggregations"):
            errors.append("aggregate: 'aggregations' is required")
        return errors


class Pivot(BaseTransform):
    """
    Pivot a long-format DataFrame to wide.
    config: index (list), columns (str), values (str), aggfunc (str)
    """

    transform_type = "pivot"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        index = config["index"]
        columns_col = config["columns"]
        values_col = config["values"]
        aggfunc = config.get("aggfunc", "first")
        result = df.pivot_table(
            index=index, columns=columns_col, values=values_col, aggfunc=aggfunc
        )
        result.columns.name = None
        result = result.reset_index()
        # Flatten any remaining MultiIndex
        result.columns = [str(c) for c in result.columns]
        return result


class Unpivot(BaseTransform):
    """
    Melt wide-format DataFrame to long (unpivot / melt).
    config: id_vars (list), value_vars (list), var_name (str), value_name (str)
    """

    transform_type = "unpivot"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        id_vars = config.get("id_vars", [])
        value_vars = config.get("value_vars")
        var_name = config.get("var_name", "variable")
        value_name = config.get("value_name", "value")
        return df.melt(
            id_vars=id_vars,
            value_vars=value_vars,
            var_name=var_name,
            value_name=value_name,
        ).reset_index(drop=True)


class Lookup(BaseTransform):
    """
    Enrich the primary DataFrame by looking up values from a named reference frame.
    Like a LEFT JOIN but optimised for reference/dimension tables.
    config: right_frame, left_key, right_key, value_columns (list), default (any)
    """

    transform_type = "lookup"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        right_name = config["right_frame"]
        left_key = config["left_key"]
        right_key = config.get("right_key", left_key)
        value_columns: list[str] = config["value_columns"]
        default = config.get("default")

        named_frames: dict[str, pd.DataFrame] = config.get("_named_frames", {})
        if right_name not in named_frames:
            raise TransformError(f"lookup: named frame {right_name!r} not available")
        ref = named_frames[right_name][[right_key] + value_columns].drop_duplicates(subset=[right_key])

        result = df.merge(ref, left_on=left_key, right_on=right_key, how="left")
        if right_key != left_key and right_key in result.columns:
            result = result.drop(columns=[right_key])

        if default is not None:
            for col in value_columns:
                if col in result.columns:
                    result[col] = result[col].fillna(default)
        return result.reset_index(drop=True)


register(InnerJoin())
register(LeftJoin())
register(Union())
register(Aggregate())
register(Pivot())
register(Unpivot())
register(Lookup())
