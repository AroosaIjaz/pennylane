r"""
.. _state_preparation:

State preparation in Forest SDK
================================

In this notebook, we build and optimize a circuit to prepare arbitrary
single-qubit states, including mixed states, using the *Forest* plugin. Along the way, we also show
how to:

1. Construct compact expressions for circuits composed of many layers.
2. Succintly evaluate expectation values of many observables.
3. Estimate expectation values from repeated measurements, as in real
   hardware.

The most general state of a qubit is represented in terms of a positive
semi-definite density matrix :math:`\rho` with unit trace. The density
matrix can be uniquely described in terms of its three-dimensional
*Bloch vector* :math:`\vec{a}=(a_x, a_y, a_z)` as:

.. math:: \rho=\frac{1}{2}(\mathbb{1}+a_x\sigma_x+a_y\sigma_y+a_z\sigma_z),

where :math:`\sigma_x, \sigma_y, \sigma_z` are the Pauli matrices. Any
Bloch vector corresponds to a valid density matrix as long as
:math:`\|\vec{a}\|\leq 1`.

The *purity* of a state is defined as :math:`p=\text{Tr}(\rho^2)`, which
for a qubit is bounded as :math:`1/2\leq p\geq 1`. The state is pure if
:math:`p=1` and maximally mixed if :math:`p=1/2`. In this example, we
select the target state by choosing a random Bloch vector and
renormalize it to have a specified purity.

"""

import pennylane as qml
from pennylane import numpy as np

##############################################################################

# we generate a three-dimensional random vector by sampling
# each entry from a standard normal distribution
v = np.random.normal(0, 1, 3)

# purity of the target state
purity = 0.66

# create a random Bloch vector with the specified purity
bloch_v = np.sqrt(2 * purity - 1) * v / np.sqrt(np.sum(v ** 2))

# array of Pauli matrices (will be useful later)
Paulis = np.zeros((3, 2, 2), dtype=complex)
Paulis[0] = [[0, 1], [1, 0]]
Paulis[1] = [[0, -1j], [1j, 0]]
Paulis[2] = [[1, 0], [0, -1]]

##############################################################################
# Unitary operations map pure states to pure states. So how can we prepare
# mixed states using unitary circuits? The trick is to introduce
# additional qubits and perform a unitary transformation on this larger
# system. By "tracing out" the ancilla qubits, we can prepare mixed states
# in the target register. In this example, we introduce two additional
# qubits, which suffices to prepare arbitrary states.
#
# The ansatz circuit is composed of repeated layers, each of which
# consists of single-qubit rotations along the :math:`x, y,` and :math:`z`
# axes, followed by three CNOT gates entangling all qubits. Initial gate
# parameters are chosen at random from a normal distribution. Importantly,
# when declaring the layer function, we introduce an input parameter
# :math:`j`, which allows us to later call each layer individually.

# number of qubits in the circuit
nr_qubits = 3
# number of layers in the circuit
nr_layers = 2

# randomly initialize parameteres from a normal distribution
params = np.random.normal(0, np.pi, (nr_qubits, nr_layers, 3))

# a layer of the circuit ansatz
def layer(params, j):
    for i in range(nr_qubits):
        qml.RX(params[i, j, 0], wires=i)
        qml.RY(params[i, j, 1], wires=i)
        qml.RZ(params[i, j, 2], wires=i)

    qml.CNOT(wires=[0, 1])
    qml.CNOT(wires=[0, 2])
    qml.CNOT(wires=[1, 2])

##############################################################################
# To set up the device, we select a plugin that is compatible with
# evaluating expectations through sampling: the ``forest.qvm`` plugin. The
# syntax is slightly different than for other plugins; we need to also
# feed a ``device`` keyword specifying the number of qubits in the format
# ``[number of qubits]q-pyqvm``. The keyword ``shots`` indicates the
# number of samples used to estimate expectation values.
#
# When defining the qnode, we introduce as input a Hermitian operator
# :math:`A` that specifies the expectation value being evaluated. This
# choice later allows us to easily evaluate several expectation values
# without having to define a new qnode each time. Useful!

# set up the device
dev = qml.device("forest.qvm", device="3q-pyqvm", shots=1000)

# set up the qnode using a decorator
@qml.qnode(dev)

# We add a Hermitian operator A as an input that specifies the expectation
# value. We set A=None to declare that this is a fixed parameter
def circuit(params, A=None):

    # repeatedly apply each layer in the circuit
    for j in range(nr_layers):
        layer(params, j)

    # returns the expectation of the input matrix A on the first qubit
    return qml.expval.Hermitian(A, wires=0)

##############################################################################
# Our goal is to prepare a state with the same Bloch vector as the target
# state. Therefore, we define a simple cost function
#
# .. math::  C = \sum_{i=1}^3 \left|a_i-a'_i\right|,
#
# where :math:`\vec{a}=(a_1, a_2, a_3)` is the target vector and
# :math:`\vec{a}'=(a'_1, a'_2, a'_3)` is the vector of the state prepared
# by the circuit. Optimization is carried out using the Adam optimizer.
# Finally, we compare the Bloch vectors of the target and output state.

# cost function
def cost_fn(params):
    cost = 0
    for k in range(3):
        cost += np.abs(circuit(params, A=Paulis[k]) - bloch_v[k])

    return cost

##############################################################################

# set up the optimizer
opt = qml.AdamOptimizer()

# number of steps in the optimization routine
steps = 200

# the final stage of optimization isn't always the best, 
# so we keep track of the best parameters along the way
best_cost = cost_fn(params)
best_params = np.zeros((nr_qubits, nr_layers, 3))

print("Cost after 0 steps is {:.4f}".format(cost_fn(params)))

# optimization begins
for n in range(steps):
    params = opt.step(cost_fn, params)
    current_cost = cost_fn(params)

    # keeps track of best parameters
    if current_cost < best_cost:
        best_params = params

    # Keep track of progress every 10 steps
    if n % 10 == 9 or n == steps - 1:
        print("Cost after {} steps is {:.4f}".format(n + 1, current_cost))

# calculate the Bloch vector of the output state
output_bloch_v = np.zeros(3)
for l in range(3):
    output_bloch_v[l] = circuit(best_params, A=Paulis[l])

# print results
print("Target Bloch vector = ", bloch_v)
print("Output Bloch vector = ", output_bloch_v)

##############################################################################
# .. rst-class:: sphx-glr-script-out
#
#  Out:
#
#  .. code-block:: none
#
#    Cost after 0 steps is 1.3770
#    Cost after 10 steps is 0.8878
#    Cost after 20 steps is 0.6018
#    Cost after 30 steps is 0.6690
#    Cost after 40 steps is 0.5798
#    Cost after 50 steps is 0.4378
#    Cost after 60 steps is 0.3798
#    Cost after 70 steps is 0.2890
#    Cost after 80 steps is 0.2098
#    Cost after 90 steps is 0.0562
#    Cost after 100 steps is 0.0670
#    Cost after 110 steps is 0.0518
#    Cost after 120 steps is 0.0662
#    Cost after 130 steps is 0.0730
#    Cost after 140 steps is 0.0882
#    Cost after 150 steps is 0.0378
#    Cost after 160 steps is 0.0390
#    Cost after 170 steps is 0.1218
#    Cost after 180 steps is 0.1590
#    Cost after 190 steps is 0.0862
#    Cost after 200 steps is 0.0650
#    Target Bloch vector =  [-0.36599498  0.42259141 -0.08639547]
#    Output Bloch vector =  [-0.384  0.468 -0.096]