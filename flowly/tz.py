"""Additional toolz.
"""
from __future__ import print_function, division, absolute_import

import functools as ft
import itertools as it
import operator as op

# TODO: add proper __all__


class ShowImpl(object):
    def __init__(self, fmt='{!r}'):
        self.fmt = fmt

    def __call__(self, obj):
        print(self.fmt.format(obj))
        return obj

    def __or__(self, obj):
        return self(obj)

    def __mod__(self, fmt):
        return ShowImpl(fmt)


show = ShowImpl()


class itemsetter(object):
    def __init__(self, *prototypes, **assigments):
        self.assigments = list(prototypes) + [dict(assigments)]

    def __call__(self, obj):
        obj = obj.copy()
        for assigment in self.assigments:
            for k, func in assigment.items():
                obj[k] = func(obj)

        return obj


class build_dict(object):
    def __init__(self, *prototypes, **assigments):
        self.assigments = list(prototypes) + [dict(assigments)]

    def __call__(self, obj):
        res = {}
        for assigment in self.assigments:
            for k, func in assigment.items():
                res[k] = func(obj)

        return res


class chained(object):
    """Represent the composition of functions.

    When the resulting object is called with a single argument, the passed
    object is transformed by passing it through all given functions.
    For example::

        a = chained(
            math.sqrt,
            math.log,
            math.cos,
        )(5.0)

    is equivalent to::

        a = 5.0
        a = math.sqrt(a)
        a = math.log(a)
        a = math.cos(a)

    Different chains can be composed via ``+``.
    For example, the chain above can be written as::

        chained(math.sqrt, math.log) + chained(math.cos)

    """
    def __init__(self, *funcs):
        self.funcs = funcs

    def __call__(self, obj):
        for func in self.funcs:
            obj = func(obj)

        return obj

    def __add__(self, other):
        return chained(*(list(self.funcs) + list(other.funcs)))


class _apply_concat_base(object):
    def __init__(self, funcs, chunks=None):
        self.funcs = list(funcs)
        self.chunks = chunks


class apply_concat(_apply_concat_base):
    """Apply the functions in parallel and concatenate the results.

    .. note::

        The order of the result is not guaranteed.

        Also care has to be taken for iterable arguments. They must be iterable
        repeatedly or or only a single function may iterate over the object.

    Equivalent to::

        it.chain.from_iterable(func(obj, *args, **kwargs) for func in funcs)

    Each function should map from an iterable to an iterable. The result will
    be the concatenation of all items in the results for all functions.

    :param Iterable[Callable[Any,...]] funcs:
        The functions to apply. Needs to be finite.

    :param Optional[int] chunks:
        A hint to parallel executors about the desired chunk size.
    """
    def __call__(self, obj):
        return list(it.chain.from_iterable(func(obj) for func in self.funcs))


class apply_map_concat(_apply_concat_base):
    """TODO: describe, decide which way to order

    Equivalent to::

        it.chain.from_iterable((func(item) for func in funcs) for item in obj)

    Each function should map from a single item to a transformed item. The
    result will be the concatenation of the transformed items of all functions.

    Note: the order is not guaranteed.

    :param Iterable[Callable[Any,...]] funcs:
        The functions to apply. Needs to be finite.

    :param Optional[int] chunks:
        A hint to parallel executors about the desired chunk size.
    """
    def __call__(self, obj):
        return it.chain.from_iterable(
            (func(item) for func in self.funcs)
            for item in obj
        )


def frequencies(obj):
    """In contrast to ``toolz.frequencies``, return ``(item, count)`` pairs.
    """
    result = {}

    for item in obj:
        result[item] = result.get(item, 0) + 1

    return list(result.items())


class groupby(object):
    """In contrast to ``toolz.groupby``, return ``(item, count)`` pairs.
    """
    def __init__(self, key):
        self.key = key

    def __call__(self, obj):
        result = {}
        for item in obj:
            result.setdefault(self.key(item), []).append(item)

        return list(result.items())


# TODO: add support for initial value
class reduceby(object):
    def __init__(self, key, binop):
        self.key = key
        self.binop = binop

    def __call__(self, seq):
        return [
            (key, ft.reduce(self.binop, subseq))
            for (key, subseq) in groupby(self.key)(seq)
        ]


# TODO: handle perpartition=None, i.e., reduction(None, sum) = reduction(sum, sum)
class reduction(object):
    def __init__(self, perpartition, aggregate, split_every=None):
        self.perpartition = perpartition
        self.aggregate = aggregate
        self.split_every = split_every

    def __call__(self, obj):
        return self.aggregate([self.perpartition(obj)])


class reductionby(object):
    def __init__(self, key, perpartition, aggregate, split_every=None):
        self.key = key
        self.perpartition = perpartition
        self.aggregate = aggregate
        self.split_every = split_every

    def __call__(self, obj):
        grouped = groupby(self.key)(obj)
        if self.perpartition is None:
            return [
                (key, self.aggregate(group))
                for (key, group) in grouped
            ]

        else:
            return [
                (key, self.aggregate([self.perpartition(group)]))
                for (key, group) in grouped
            ]


def seq(*items):
    """Turn one or multiple values into a list.

    Examples::

        >>> seq(1)
        [1]
        >>> seq(1, 2, 3)
        [1, 2, 3]
        >>> seq([1], [2])
        [[1], [2]]
    """
    return list(items)


class kv_keymap(object):
    def __init__(self, func):
        self.func = func

    def __call__(self, obj):
        return (
            (self.func(key), value)
            for (key, value) in obj
        )


class kv_valmap(object):
    def __init__(self, func):
        self.func = func

    def __call__(self, obj):
        return (
            (key, self.func(value))
            for (key, value) in obj
        )


class kv_reduceby(object):
    """Reduce for key value pairs, only values are seend by the reducer.

    In contrast to :func:`flowly.tz.reduceby`, the data should be a list of
    key-value pairs.
    The groups are formed by the key part of each item and the reducer is only
    applied to the values.
    This function is designed to map from a list of key-value pairs to another
    list of key-value pairs.

    :param Callable[Any,Any,Any] binop:
        a binary function that maps to values to an aggregated value.
    """
    def __init__(self, binop):
        self.binop = binop

    def __call__(self, obj):
        return [
            (key, ft.reduce(self.binop, [val for _, val in group]))
            for (key, group) in groupby(op.itemgetter(0))(obj)
        ]


class kv_reductionby(object):
    """Reduction for key value pairs, only values are seend by the reducer.

    In contrast to :func:`flowly.tz.reductionby`, the data should be a list of
    key-value pairs.
    The groups are formed by the key part of each item and the reduction is only
    applied to the values.
    This function is designed to map from a list of key-value pairs to another
    list of key-value pairs.
    """
    def __init__(self, perpartition, aggregate, split_every=None):
        self.perpartition = perpartition
        self.aggregate = aggregate
        self.split_every = split_every

    def __call__(self, obj):
        if self.perpartition is None:
            reducer = self.aggregate

        else:
            def reducer(obj):
                return self.aggregate([self.perpartition(obj)])

        return [
            (key, reducer([val for _, val in group]))
            for (key, group) in groupby(op.itemgetter(0))(obj)
        ]


def optional(val):
    """Wrap any value with the optional moand.

    Usage::

        val = +optional(val).or_else(default_value).get()

        val = +optional(val).or_else_call(expensive_function, arg1, arg2).get()
    """
    return Just(val) if val is not None else Nothing()


def try_call(func, *args, **kwargs):
    """Try to call the function and return a Try monad.

    Usage::

        result = +try_call(func, arg1, arg2).recover(altnative_operation).get()
    """
    try:
        result = func(*args, **kwargs)

    except Exception as e:
        return Failure(e)

    else:
        return Success(result)


def raise_(exc_class, *args, **kwargs):
    raise exc_class(*args, **kwargs)


class _Gettable(object):
    def __pos__(self):
        return self.get()

    def get(self):  # pragma: no cover
        raise NotImplementedError()


class _Maybe(_Gettable):
    pass


class Nothing(_Maybe):
    def __init__(self):
        pass

    def transform(self, func, *args, **kwargs):
        return self

    def get(self):
        raise ValueError()

    def or_else(self, val):
        return optional(val)

    def or_else_call(self, func, *args, **kwargs):
        return optional(func(*args, **kwargs))


class Just(_Maybe):
    def __init__(self, value):
        self.value = value

    def transform(self, func, *args, **kwargs):
        return optional(func(self.value, *args, **kwargs))

    def get(self):
        return self.value

    def or_else(self, val):
        return self

    def or_else_call(self, func, *args, **kwargs):
        return self


class _Try(_Gettable):
    pass


class Success(_Try):
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def then(self, func, *args, **kwargs):
        return try_call(func, self.value, *args, **kwargs)

    def recover(self, func, *args, **kwargs):
        return self


class Failure(_Try):
    def __init__(self, exception):
        self.exception = exception

    def get(self):
        raise self.exception

    def then(self, func, *args, **kwargs):
        return self

    def recover(self, func, *args, **kwargs):
        return try_call(func, self.exception, *args, **kwargs)
