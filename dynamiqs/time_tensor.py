from __future__ import annotations

from abc import abstractmethod, abstractproperty
from typing import get_args

import torch
from torch import Tensor

from ._utils import cache, check_time_tensor, obj_type_str, type_str
from .utils.tensor_types import (
    ArrayLike,
    Number,
    dtype_complex_to_real,
    get_cdtype,
    to_device,
    to_tensor,
)

__all__ = ['totime']


def totime(
    x: (
        ArrayLike
        | callable[[float], Tensor]
        | tuple[ArrayLike, ArrayLike, ArrayLike]
        | tuple[callable[[float], Tensor], ArrayLike]
    ),
    *,
    dtype: torch.dtype | None = None,
    device: str | torch.device | None = None,
) -> TimeTensor:
    dtype = dtype or get_cdtype(dtype)  # assume complex by default
    device = to_device(device)

    # PWC time tensor
    if isinstance(x, tuple) and len(x) == 3:
        return _factory_pwc(x, dtype=dtype, device=device)
    # modulated time tensor
    if isinstance(x, tuple) and len(x) == 2:
        return _factory_modulated(x, dtype=dtype, device=device)
    # constant time tensor
    if isinstance(x, get_args(ArrayLike)):
        return _factory_constant(x, dtype=dtype, device=device)
    # callable time tensor
    elif callable(x):
        return _factory_callable(x, dtype=dtype, device=device)
    else:
        raise TypeError(
            'For time-dependent tensors, argument `x` must be one of 4 types: (1)'
            ' ArrayLike; (2) 2-tuple with type (function, ArrayLike) where function'
            ' has signature (t: float) -> Tensor; (3) 3-tuple with type (ArrayLike,'
            ' ArrayLike, ArrayLike); (4) function with signature (t: float) -> Tensor.'
            f' The provided `x` has type {obj_type_str(x)}.'
        )


def _factory_constant(
    x: ArrayLike, *, dtype: torch.dtype, device: torch.device
) -> ConstantTimeTensor:
    x = to_tensor(x, dtype=dtype, device=device)
    return ConstantTimeTensor(x)


def _factory_callable(
    x: callable[[float], Tensor], *, dtype: torch.dtype, device: torch.device
) -> CallableTimeTensor:
    f0 = x(0.0)

    # check type, dtype and device match
    if not isinstance(f0, Tensor):
        raise TypeError(
            f'The time-dependent operator must be a {type_str(Tensor)}, but has'
            f' type {obj_type_str(f0)}. The provided function must return a tensor,'
            ' to avoid costly type conversion at each time solver step.'
        )
    elif f0.dtype != dtype:
        raise TypeError(
            f'The time-dependent operator must have dtype `{dtype}`, but has dtype'
            f' `{f0.dtype}`. The provided function must return a tensor with the'
            ' same `dtype` as provided to the solver, to avoid costly dtype'
            ' conversion at each solver time step.'
        )
    elif f0.device != device:
        raise TypeError(
            f'The time-dependent operator must be on device `{device}`, but is on'
            f' device `{f0.device}`. The provided function must return a tensor on'
            ' the same device as provided to the solver, to avoid costly device'
            ' transfer at each solver time step.'
        )

    return CallableTimeTensor(x, f0)


def _factory_pwc(
    x: tuple[ArrayLike, ArrayLike, ArrayLike],
    *,
    dtype: torch.dtype,
    device: torch.device,
) -> PWCTimeTensor:
    times, values, tensor = x

    # get real-valued dtype
    if dtype in (torch.complex64, torch.complex128):
        rdtype = dtype_complex_to_real(dtype)
    else:
        rdtype = dtype

    # times
    times = to_tensor(times, dtype=rdtype, device=device)
    check_time_tensor(times, arg_name='times')

    # values
    values = to_tensor(values, dtype=dtype, device=device)
    if values.shape[0] != len(times) - 1:
        raise TypeError(
            'For a PWC tensor `(times, values, tensor)`, argument `values` must'
            ' have shape `(len(times)-1, ...)`, but has shape'
            f' {tuple(values.shape)}.'
        )

    # tensor
    tensor = to_tensor(tensor, dtype=dtype, device=device)
    if tensor.ndim != 2 or tensor.shape[-1] != tensor.shape[-2]:
        raise TypeError(
            'For a PWC tensor `(times, values, tensor)`, argument `tensor` must be'
            f' a square matrix, but has shape {tuple(tensor.shape)}.'
        )

    factors = [_PWCFactor(times, values)]
    tensors = tensor.unsqueeze(0)  # (1, n, n)
    return PWCTimeTensor(factors, tensors)


def _factory_modulated(
    x: tuple[callable[[float], Tensor], Tensor],
    *,
    dtype: torch.dtype,
    device: torch.device,
) -> ModulatedTimeTensor:
    f, tensor = x

    # get real-valued dtype
    if dtype in (torch.complex64, torch.complex128):
        rdtype = dtype_complex_to_real(dtype)
    else:
        rdtype = dtype

    # check f
    if not callable(f):
        raise TypeError(
            'For a modulated time tensor `(f, tensor)`, argument `f` must'
            f' be a function, but has type {obj_type_str(f)}.'
        )
    f0 = f(0.0)
    if not isinstance(f0, Tensor):
        raise TypeError(
            'For a modulated time tensor `(f, tensor)`, argument `f` must'
            f' return a tensor, but returns type {obj_type_str(f0)}.'
        )
    if f0.device != device:
        raise TypeError(
            'For a modulated time tensor, the tensor returned by the function must'
            f' be on device `{device}`, but is on device `{f0.device}`. This is'
            ' necessary to avoid costly device transfer at each solver time step.'
        )
    elif f0.dtype not in [dtype, rdtype]:
        dtypes = f'`{dtype}`' if dtype == rdtype else f'`{dtype}` or `{rdtype}`'
        raise TypeError(
            'For a modulated time tensor, the tensor returned by the function must'
            f' have dtype `{dtypes}`, but has dtype `{f0.dtype}`. This is necessary'
            ' to avoid costly dtype conversion at each solver time step.'
        )

    # tensor
    tensor = to_tensor(tensor, dtype=dtype, device=device)
    if tensor.ndim != 2 or tensor.shape[-1] != tensor.shape[-2]:
        raise TypeError(
            'For a modulated time tensor `(f, tensor)`, argument `tensor` must'
            f' be a square matrix, but has shape {tuple(tensor.shape)}.'
        )

    factors = [_ModulatedFactor(f, f0)]
    tensors = tensor.unsqueeze(0)  # (1, n, n)
    return ModulatedTimeTensor(factors, tensors)


class TimeTensor:
    # Subclasses should implement:
    # - the properties: dtype, device, shape
    # - the methods: __call__, view, adjoint, __neg__, __mul__, __add__

    # Special care should be taken when implementing `__call__` for caching to work
    # properly. The `@cache` decorator checks the tensor `__hash__`, which is
    # implemented as its address in memory. Thus, when two consecutive calls to a
    # `TimeTensor` should return a tensor with the same values, these two tensors must
    # not only be equal, they should be the same object in memory.

    # Note that a subclass implementation of `__add__` only need to support addition
    # with `Tensor`, `ConstantTimeTensor` and the subclass type itself.

    @abstractproperty
    def dtype(self) -> torch.dtype:
        """Data type."""
        pass

    @abstractproperty
    def device(self) -> torch.device:
        """Device."""
        pass

    @abstractproperty
    def shape(self) -> torch.Size:
        """Shape."""
        pass

    @abstractmethod
    def __call__(self, t: float) -> Tensor:
        """Evaluate at a given time"""
        pass

    @abstractmethod
    def view(self, *shape: int) -> TimeTensor:
        """Returns a new tensor with the same data but of a different shape."""
        pass

    @abstractmethod
    def adjoint(self) -> TimeTensor:
        pass

    @property
    def mH(self) -> TimeTensor:
        return self.adjoint()

    @abstractmethod
    def __neg__(self) -> TimeTensor:
        pass

    @abstractmethod
    def __mul__(self, other: Number | Tensor) -> TimeTensor:
        pass

    def __rmul__(self, other: Number | Tensor) -> TimeTensor:
        return self * other

    @abstractmethod
    def __add__(self, other: Tensor | TimeTensor) -> TimeTensor:
        pass

    def __radd__(self, other: Tensor | TimeTensor) -> TimeTensor:
        return self + other

    def __sub__(self, other: Tensor | TimeTensor) -> TimeTensor:
        return self + (-other)

    def __rsub__(self, other: Tensor | TimeTensor) -> TimeTensor:
        return other + (-self)

    def __repr__(self) -> str:
        return str(type(self).__name__)

    def __str__(self) -> str:
        return self.__repr__()

    def size(self, dim: int) -> int:
        """Size along a given dimension."""
        return self.shape[dim]

    def dim(self) -> int:
        """Get the number of dimensions."""
        return len(self.shape)

    @property
    def ndim(self) -> int:
        """Number of dimensions."""
        return self.dim()


class ConstantTimeTensor(TimeTensor):
    def __init__(self, tensor: Tensor):
        self.tensor = tensor

    @property
    def dtype(self) -> torch.dtype:
        return self.tensor.dtype

    @property
    def device(self) -> torch.device:
        return self.tensor.device

    @property
    def shape(self) -> torch.Size:
        return self.tensor.shape

    def __call__(self, t: float) -> Tensor:
        return self.tensor

    def view(self, *shape: int) -> TimeTensor:
        return ConstantTimeTensor(self.tensor.view(*shape))

    def adjoint(self) -> TimeTensor:
        return ConstantTimeTensor(self.tensor.adjoint())

    def __neg__(self) -> TimeTensor:
        return ConstantTimeTensor(-self.tensor)

    def __mul__(self, other: Number | Tensor) -> TimeTensor:
        return ConstantTimeTensor(self.tensor * other)

    def __add__(self, other: Tensor | TimeTensor) -> TimeTensor:
        if isinstance(other, Tensor):
            return ConstantTimeTensor(self.tensor + other)
        elif isinstance(other, ConstantTimeTensor):
            return self + other.tensor
        else:
            return NotImplemented


class CallableTimeTensor(TimeTensor):
    def __init__(self, f: callable[[float], Tensor], f0: Tensor):
        # f0 carries all the transformation on the shape
        self.f = f
        self.f0 = f0

    @property
    def dtype(self) -> torch.dtype:
        return self.f0.dtype

    @property
    def device(self) -> torch.device:
        return self.f0.device

    @property
    def shape(self) -> torch.Size:
        return self.f0.shape

    @cache
    def __call__(self, t: float) -> Tensor:
        # cached if called twice with the same time, otherwise we recompute `f(t)`
        return self.f(t).view(self.shape)

    def view(self, *shape: int) -> TimeTensor:
        f = self.f
        f0 = self.f0.view(*shape)
        return CallableTimeTensor(f, f0)

    @abstractmethod
    def adjoint(self) -> TimeTensor:
        f = lambda t: self.f(t).adjoint()
        f0 = self.f0.adjoint()
        return CallableTimeTensor(f, f0)

    def __neg__(self) -> TimeTensor:
        f = lambda t: -self.f(t)
        f0 = -self.f0
        return CallableTimeTensor(f, f0)

    def __mul__(self, other: Number | Tensor) -> TimeTensor:
        f = lambda t: self.f(t) * other
        f0 = self.f0 * other
        return CallableTimeTensor(f, f0)

    def __add__(self, other: Tensor | TimeTensor) -> TimeTensor:
        if isinstance(other, Tensor):
            f = lambda t: self.f(t) + other
            f0 = self.f0 + other
            return CallableTimeTensor(f, f0)
        elif isinstance(other, ConstantTimeTensor):
            return self + other.tensor
        elif isinstance(other, CallableTimeTensor):
            f = lambda t: self.f(t) + other.f(t)
            f0 = self.f0 + other.f0
            return CallableTimeTensor(f, f0)
        else:
            return NotImplemented


class _PWCFactor:
    # Defined by a tuple of 2 tensors (times, values), where
    # - times: (nv+1) are the time points between which the PWC tensor take constant
    #          values, where nv is the number of time intervals
    # - values: (..., nv) are the constant values for each time interval, where
    #           (...) is an arbitrary batching size

    def __init__(self, times: Tensor, values: Tensor):
        self.times = times  # (nv+1)
        self.values = values  # (..., nv)
        self.nv = self.values.shape[-1]

    @property
    def shape(self) -> torch.Size:
        return self.values.shape[:-1]  # (...)

    def conj(self) -> _PWCFactor:
        return _PWCFactor(self.times, self.values.conj())

    def __call__(self, t: float) -> Tensor:
        if t < self.times[0] or t >= self.times[-1]:
            return torch.zeros_like(self.values[..., 0])  # (...)
        else:
            # find the index $k$ such that $t \in [t_k, t_{k+1})$
            idx = torch.searchsorted(self.times, t, side='right') - 1
            return self.values[..., idx]  # (...)

    def view(self, *shape: int) -> _PWCFactor:
        return _PWCFactor(self.times, self.values.view(*shape, self.nv))


class PWCTimeTensor(TimeTensor):
    # Arbitrary sum of tensors with PWC factors.

    def __init__(
        self, factors: list[_PWCFactor], tensors: Tensor, static: Tensor | None = None
    ):
        # factors must be non-empty
        self.factors = factors  # list of length (nf)
        self.tensors = tensors  # (nf, n, n)
        self.n = tensors.shape[-1]
        self.static = torch.zeros_like(self.tensors[0]) if static is None else static

        # merge all times
        self.times = torch.cat([x.times for x in self.factors]).unique(sorted=True)

    @property
    def dtype(self) -> torch.dtype:
        return self.tensors.dtype

    @property
    def device(self) -> torch.device:
        return self.tensors.device

    @property
    def shape(self) -> torch.Size:
        return torch.Size((*self.factors[0].shape, self.n, self.n))  # (..., n, n)

    @cache
    def _call(self, idx: int) -> Tensor:
        # cache on the index in self.times

        if idx < 0 or idx >= len(self.times) - 1:
            static = self.static.expand(*self.shape)  # (..., n, n)
            return static  # (..., n, n)
        else:
            t = self.times[idx]
            values = torch.stack([x(t) for x in self.factors], dim=-1)  # (..., nf)
            values = values.view(*values.shape, 1, 1)  # (..., nf, n, n)
            return (values * self.tensors).sum(-3) + self.static  # (..., n, n)

    def __call__(self, t: float) -> Tensor:
        # find the index $k$ such that $t \in [t_k, t_{k+1})$, `idx = -1` if
        # `t < times[0]` and `idx = len(times) - 1` if `t >= times[-1]`
        idx = torch.searchsorted(self.times, t, side='right') - 1
        return self._call(idx.item())

    def view(self, *shape: int) -> TimeTensor:
        # shape: (..., n, n)
        factors = [x.view(*shape[:-2]) for x in self.factors]
        return PWCTimeTensor(factors, self.tensors, static=self.static)

    def adjoint(self) -> TimeTensor:
        factors = [x.conj() for x in self.factors]
        return PWCTimeTensor(factors, self.tensors.mH, static=self.static.mH)

    def __neg__(self) -> TimeTensor:
        return PWCTimeTensor(self.factors, -self.tensors, static=-self.static)

    def __mul__(self, other: Number | Tensor) -> TimeTensor:
        return PWCTimeTensor(
            self.factors, self.tensors * other, static=self.static * other
        )

    def __add__(self, other: Tensor | TimeTensor) -> TimeTensor:
        if isinstance(other, Tensor):
            static = self.static + other
            return PWCTimeTensor(self.factors, self.tensors, static=static)
        elif isinstance(other, ConstantTimeTensor):
            return self + other.tensor
        elif isinstance(other, PWCTimeTensor):
            factors = self.factors + other.factors  # list of length (nf1 + nf2)
            tensors = torch.cat((self.tensors, other.tensors))  # (nf1 + nf2, n, n)
            static = self.static + other.static  # (n, n)
            return PWCTimeTensor(factors, tensors, static=static)
        else:
            return NotImplemented


class _ModulatedFactor:
    # Defined by two objects (f, f0), where
    # - f is a callable that takes a time and returns a tensor of shape (...)
    # - f0 is the tensor of shape (...) returned by f(0.0)
    # f0 holds information about the shape of the tensor returned by f(t).

    def __init__(self, f: callable[[float], Tensor], f0: Tensor):
        self.f = f  # (float) -> (...)
        self.f0 = f0  # (...)

    @property
    def shape(self) -> torch.Size:
        return self.f0.shape

    def conj(self) -> _ModulatedFactor:
        f = lambda t: self.f(t).conj()
        f0 = self.f0.conj()
        return _ModulatedFactor(f, f0)

    def __call__(self, t: float) -> Tensor:
        return self.f(t).view(self.shape)

    def view(self, *shape: int) -> _ModulatedFactor:
        f = self.f
        f0 = self.f0.view(*shape)
        return _ModulatedFactor(f, f0)


class ModulatedTimeTensor(TimeTensor):
    # Sum of tensors with callable factors.

    def __init__(
        self,
        factors: list[_ModulatedFactor],
        tensors: Tensor,
        static: Tensor | None = None,
    ):
        # factors must be non-empty
        self.factors = factors  # list of length (nf)
        self.tensors = tensors  # (nf, n, n)
        self.n = tensors.shape[-1]
        self.static = torch.zeros_like(self.tensors[0]) if static is None else static

    @property
    def dtype(self) -> torch.dtype:
        return self.tensors.dtype

    @property
    def device(self) -> torch.device:
        return self.tensors.device

    @property
    def shape(self) -> torch.Size:
        return torch.Size((*self.factors[0].shape, self.n, self.n))  # (..., n, n)

    def __call__(self, t: float) -> Tensor:
        values = torch.stack([x(t) for x in self.factors], dim=-1)  # (..., nf)
        values = values.view(*values.shape, 1, 1)  # (..., nf, n, n)
        return (values * self.tensors).sum(-3) + self.static  # (..., n, n)

    def view(self, *shape: int) -> TimeTensor:
        # shape: (..., n, n)
        factors = [x.view(*shape[:-2]) for x in self.factors]
        return ModulatedTimeTensor(factors, self.tensors, static=self.static)

    def adjoint(self) -> TimeTensor:
        factors = [x.conj() for x in self.factors]
        return ModulatedTimeTensor(factors, self.tensors.mH, static=self.static.mH)

    def __neg__(self) -> TimeTensor:
        return ModulatedTimeTensor(self.factors, -self.tensors, static=-self.static)

    def __mul__(self, other: Number | Tensor) -> TimeTensor:
        return ModulatedTimeTensor(
            self.factors, self.tensors * other, static=self.static * other
        )

    def __add__(self, other: Tensor | TimeTensor) -> TimeTensor:
        if isinstance(other, Tensor):
            static = self.static + other
            return ModulatedTimeTensor(self.factors, self.tensors, static=static)
        elif isinstance(other, ConstantTimeTensor):
            return self + other.tensor
        elif isinstance(other, ModulatedTimeTensor):
            factors = self.factors + other.factors  # list of length (nf1 + nf2)
            tensors = torch.cat((self.tensors, other.tensors))  # (nf1 + nf2, n, n)
            static = self.static + other.static  # (n, n)
            return ModulatedTimeTensor(factors, tensors, static=static)
        else:
            return NotImplemented
