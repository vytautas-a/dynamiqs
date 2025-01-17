<h1 align="center">
    <img src="./docs/media/dynamiqs-logo.png" width="520" alt="dynamiqs library logo">
</h1>

[P. Guilmin](https://github.com/pierreguilmin), [R. Gautier](https://github.com/gautierronan), [A. Bocquet](https://github.com/abocquet), [E. Genois](https://github.com/eliegenois)

[![ci](https://github.com/dynamiqs/dynamiqs/actions/workflows/ci.yml/badge.svg)](https://github.com/dynamiqs/dynamiqs/actions/workflows/ci.yml?query=branch%3Amain)  ![python version](https://img.shields.io/badge/python-3.8%2B-blue) [![chat](https://badgen.net/badge/icon/on%20slack?icon=slack&label=chat&color=orange)](https://join.slack.com/t/dynamiqs-org/shared_invite/zt-1z4mw08mo-qDLoNx19JBRtKzXlmlFYLA) [![license: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-yellow)](https://github.com/dynamiqs/dynamiqs/blob/main/LICENSE) [![code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

High-performance quantum systems simulation with PyTorch.

The **dynamiqs** library enables GPU simulation of large quantum systems, and computation of gradients based on the evolved quantum state. Differentiable solvers are available for the Schrödinger equation, the Lindblad master equation, and the stochastic master equation. The library is fully built on PyTorch and can efficiently run on CPUs and GPUs.

:hammer_and_wrench: This library is under active development and while the APIs and solvers are still finding their footing, we're working hard to make it worth the wait. Check back soon for the grand opening!

Some exciting features of dynamiqs include:

- Running simulations on **GPUs**, with a significant speedup for large Hilbert space dimensions.
- **Batching** many simulations of different Hamiltonians, jump operators or initial states to run them concurrently.
- Exploring solvers **tailored to quantum** simulations that preserve the properties of the state, such as trace and positivity.
- Computing **gradients** of any function of the evolved quantum state with respect to any parameter of the Hamiltonian, jump operators, or initial state.
- Using the library as a drop-in replacement for [QuTiP](https://qutip.org/) by directly passing QuTiP-defined quantum objects to our solvers.
- Implementing your own solvers with ease by subclassing our base solver class and focusing directly on the solver logic.
- Enjoy reading our carefully crafted documentation on our website: <https://www.dynamiqs.org>.

We hope that this library will prove beneficial to the community for e.g. simulations of large quantum systems, gradient-based parameter estimation, or large-scale quantum optimal control.

## Installation

We will soon make a first release of the library on PyPi. In the meantime, you can install directly from source:

```shell
pip install git+https://github.com/dynamiqs/dynamiqs.git
```

## Examples

### Simulate a lossy quantum harmonic oscillator

This first example shows simulation of a lossy harmonic oscillator with Hamiltonian $H=\omega a^\dagger a$ and a single jump operator $L=\sqrt{\kappa} a$ using QuTiP-defined objects:

```python
import dynamiqs as dq
import numpy as np
import qutip as qt
import torch

# parameters
n = 128       # Hilbert space dimension
omega = 1.0   # frequency
kappa = 0.1   # decay rate
alpha0 = 1.0  # initial coherent state amplitude

# QuTiP operators, initial state and saving times
a = qt.destroy(n)
H = omega * a.dag() * a
jump_ops = [np.sqrt(kappa) * a]
psi0 = qt.coherent(n, alpha0)
tsave = np.linspace(0, 1.0, 101)

# run on GPU if available, otherwise on CPU
torch.set_default_device('cuda' if torch.cuda.is_available() else 'cpu')

# run simulation
result = dq.mesolve(H, jump_ops, psi0, tsave)
print(result)
```

```text
|██████████| 100.0% - time 00:00/00:00
==== Result ====
Method       : Dopri5
Start        : 2023-09-10 16:57:34
End          : 2023-09-10 16:57:35
Total time   : 0.48 s
states       : Tensor (101, 128, 128) | 12.62 Mb
```

### Compute gradients with respect to some parameters

Suppose that in the above example, we want to compute the gradient of the number of photons in the final state, $\bar{n} = \mathrm{Tr}[a^\dagger a \rho(t_f)]$, with respect to the decay rate $\kappa$ and the initial coherent state amplitude $\alpha_0$. For this computation, we will define the objects with dynamiqs:

```python
import dynamiqs as dq
import torch

# parameters
n = 128
omega = 1.0
kappa = torch.tensor([0.1], requires_grad=True)
alpha0 = torch.tensor([1.0], requires_grad=True)

# dynamiqs operators, initial state and saving times
a = dq.destroy(n)
H = omega * dq.dag(a) @ a
jump_ops = [torch.sqrt(kappa) * a]
psi0 = dq.coherent(n, alpha0)
tsave = torch.linspace(0, 1.0, 101)

# run on GPU if available, otherwise on CPU
torch.set_default_device('cuda' if torch.cuda.is_available() else 'cpu')

# run simulation
result = dq.mesolve(
    H, jump_ops, psi0, tsave,
    gradient=dq.gradient.Autograd(),
    options=dict(verbose=False),
)

# gradient computation
loss = dq.expect(dq.dag(a) @ a, result.states[-1]).real
loss.backward()
print(kappa.grad)
print(alpha0.grad)
```

```text
tensor([-0.9048])
tensor([1.8097])
```

## Let's talk!

If you're curious, have questions or suggestions, wish to contribute or simply want to say hello, please don't hesitate to engage with us, we're always happy to chat! You can join the community on Slack via [this invite link](https://join.slack.com/t/dynamiqs-org/shared_invite/zt-1z4mw08mo-qDLoNx19JBRtKzXlmlFYLA), open an issue on GitHub, or contact the lead developer via email at <pierreguilmin@gmail.com>.

## Contributing

We warmly welcome all contributions. Please refer to [CONTRIBUTING.md](https://github.com/dynamiqs/dynamiqs/blob/main/CONTRIBUTING.md) for detailed instructions.
