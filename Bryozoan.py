# -*- coding: utf-8 -*-
"""
Created on Thu Feb  4 17:50:19 2016

@author: Michelangelo

The goal of this project is to identify general principles involved in
function-dependent development by investigating flow-regulated patterning in
bryozoan colonies. Two main questions include: A) Do the consequences of
strengthening connections that experience high use depend significantly on the
underlying connectivity and physics? And B) what features could give stability
to systems that use this kind of feedback?

Bryozoans appear to use a similar form of flow-regulated development (where
conduits with high flow grow and -- possibly, though no data yet -- conduits
with low flow shrink) as blood vessels and plasmodial slime molds, but these
systems have very different geometries, pumps, functions, and evolutionary
history (a similar kind of feedback rule also occurs in the nervous and
skeletal systems and wood, with -- of course -- many differences too).
Looking at bryozoans might suggest some shared princples across these systems.

This script is meant to become a simple resistive-network model of a bryozoan
colony to see if this rule (high-flow -> large conduits; low-flow -> small
conduits) maintain stable chimneys

Questions to address in project:
1) Non-growing colony with constant network among nodes: Can chimney pattern
be maintained? Over what range of variation in the relationships among
conductivity, regulated parameter, and sensed parameter (e.g. shear or flow
speed) can it be maintained?
2) Does chimney pattern remain stable after perturbation (mimicking natural
injuries)?
3) To what extent does flow-regulation of conductivity enhance function (e.g.
reduce costs of pumping + material, or maximize excurrent velocity) when the
algorithm does not match the physics precisely? (e.g. how well does it tolerate
changes in the relationship between geometry and conductivity with epibiont
fouling?)
4) Can flow-regulation of conduit size explain formation of chimney pattern as
the colony grows?

METHODS FOR COLONY CLASS:
_init_: Set up colony network
colonyplot: plot conductivities of internal edges (lines) and edges to outside
(dots); overlays with plot of flow to outside (stars) and (arrows) flow
between nodes
setouterconductivities: Modify conductivity of inner node-to-outside edges.
solveflows: Solve for flows within network (given incurrent flows into nodes)

ATTRIBUTES OF COLONY OBJECTS:
 'Adjacency',
 'InFlow',
 'Incidence',
 'InnerConduits',
 'Laplacian',
 'OutflowConduits',
 'UpperAdjacency'
 'colinds',
 'm',
 'n',
 'rowinds',
 'xs',
 'ys',
 'ysjig'

DESIRED FEATURES:
1) The following methods:
???: Update colony conductivities based on flow.
???: Punch a hole in the colony (locally modify the conductivities, and keep
them fixed).
???: Assess pattern (stability, chimneyishness, function)
???: Grow colony
2) Averaging over nearby edges (conduits) to mimic the effect of having
multiple flow paths, with correlated conductivity, associated with each zooid.
3) Asymmetry in flow response and aging (so zooids can respond differently to
increased vs decreased flow, and old zooids respond differently than young
ones)
#2 would add realism to the model, and may be important for stability, but may
not be common to other similar systems; it is unknown if #3 would add realism
(though seems likely) but similar effects occur in other systems and could
enhance stability.
4) Maybe use tuples in some places I used lists? (tuples immutable), or use 
_attributes?

"""
# The following two lines should reset IPython (clear variables and libraries;
# alternative: type %reset in console).
from IPython import get_ipython
get_ipython().magic('reset -sf')

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from numpy import arange, delete, concatenate, dot, vstack, hstack, stack
from pprint import pprint  # Function to print attributes of object.
from scipy import sparse  # Sparse library
from scipy.sparse.linalg import spsolve
from time import time
from scipy.sparse.linalg import bicgstab


def dCdt_fun_gen(Cs, dPs, **kwargs):
    """
    Calculate dConductivity/dt (dC/dt) and S ('shear-like') quantifier.
    
    S captures the notion that large conduits should
    carry more flow than small conduits. It should be monotonically
    increasing function of flow (current, flux, etc) and monotonically
    decreasing function of conductivity. Shear (e.g. in blood vessels) is
    one example analogized here:

    Parameters
    ----------
    Cs : array, dim = 1
        1-by-n array of conductivities (floats)
    dPs : array, dim = 1
        1-by-n array of pressure differences (floats; same length as Cs)
    kwargs : parameters for model

    Returns
    -------
    tuple : length 2, first part is an array of values for dConductivity/dt,
        second part is an array of values for quantifier S. Both arrays are
        have 1 dimension, same length as input arrays.

    Justification for form of S & dC/dt:
    ------------------------------------
    shear*perimeter*length = pressureDrop*crosssectionArea

    h = parameter with units of length (radius, width, height...)
        describing conduit width

    perimeter ~ C*h^x, 0 ≤ x ≤ 1 (x = 0 if h is separation between infinite
        parallel plates; x = 1 if h is radius or width of conduit that
        scales isotropically, e.g. radius of cylindrical pipe).
    crosssectionArea ~ K*h^y, 1 ≤ y ≤ 2 (y = 1 if h is separation between
        infinite parallel plates; y = 2 if h is radius or width of conduit
        that scales isotropically (e.g. radius of cylindrical pipe);
        BUT, for height of vertical parallel plates, area and perimeter
        both x and y increase in direct proporion to height: y = x = 1.
    Therefore, assuming conduit length is constant:
    shear ~ pressureDrop*c*h^(y-x) : 0 ≤ (y-x) ≤ 1 (with c = K/(C*length)).

    conductivity ~ d*h^w, 1 ≤ w ≤ 4 (w = 3 if h is separation of plates;
        w = 4 if h is radius of cylindrical pipe; w = 1 if h is height of
        parallel vertical plates (assuming their separation is much smaller
        than their height)).

    Hence: h ~ (conductivity/d)^(1/w) and:
    shear ~ pressureDrop*(c/(d^z))*conductivity^z; z=(y-x)/w, b=c/(d^z)

    For the three cases above:
        separation between parallel plates: x = 0, y = 1, w = 3 : z = 1/3
        height of vertical parallel plates: x = 1, y = 1, w = 1 : z = 0
        radius of cylinder:                 x = 1, y = 2, w = 4 : z = 1/4

    Therefore, set S = b*(conductivity^z)*pressureDrop, 0 ≤ z ≤ 1/3
    As matrices (conductivity as diagonal matrix)
        S = abs(sum(conductivity[i,j]^z*sum(Incidence[j,k]*Pressures[k])
    """
    if type(Cs) is numpy.ndarray and type(dPs) is numpy.ndarray:
        if Cs.shape ==dPs.shape:
            S = abs(kwargs.get('b')*(Cs**kwargs.get('z'))*dPs)
            dCdt = kwargs.get('r')*(S -1)
            return dCdt, S
            
class Colony:
    """
        Colony class represents the connections and arrangement of zooids in
        a sheet-like bryozoan colony.
    """
    def __init__(self, nz=1, mz=1, InnerConductivity=1,
                 OutflowConductivity=1, Incurrents=-1,
                 dCdt_inner=None, dCdt_outer=None):
        """
        Create a new colony given the following inputs:

        Parameters
        ----------
        nz : int
            number of zooid columns (run proximal-distal)
        mz : int
            number of zooid rows (run left-right)
        InnerConductivity : float
            Conductivity for edges (conduits) connecting nodes within colony
            (inner nodes).
        OutflowConductivity : float 
            Conductivity between inner nodes and outside node.
        Incurrents : float
            Flow into colony (negative = inflow)
        Sfunc_... : Functions
            Calculate S, which measures match between conductivities & flow
            (using pressure differences). ...inner, ...outer are for conduits
            connecting inner-inner (or inner-growth zone), or inner-outer nodes
        """
        # Set up numbers of nodes.
        n = nz * 2  # 2 nodes added for every zooid from left-right;
        m = mz  # 1 node added for every zooid proximal-distal
        mn = arange(0, m * n)  # Number nodes. One node added on distal end
        # for every zooid row added.
        self.n = n
        self.m = m

        # Determine y and x coordinates.
        self.ys = mn // n  # Y position of nodes.
        self.xs = mn % n+self.ys  # X position of nodes
        self.ysjig = self.ys + 0.2 * (mn % 2)  # Y positions, shifted to
        # make hexagons for plotting.

        # Define indices for node-node connections in adjacency matrix.
        # Rowinds and colinds define arrays of indices for which internal nodes
        # connect to each other (in upper triangular matrix).
        # Each node from 0 to m*n-1 connects to next node in the network.
        rowinds = arange(0, m*n)
        colinds = arange(1, m*n+1)
        # delete edges connecting nodes at end of one row to beginning of next
        rowinds = delete(rowinds, arange(n-1, m*n, n))
        colinds = delete(colinds, arange(n-1, m*n, n))
        # add edges connecting beginning of row to end of row
        rowinds = concatenate((rowinds, arange(0, (m-1)*n+1, n)), axis=0)
        colinds = concatenate((colinds, arange(n-1, m*n, n)), axis=0)
        # add edges connecting every other node to node in row ahead.
        rowinds = concatenate((rowinds, arange(1, (m-1)*n, 2)), axis=0)
        colinds = concatenate((colinds, arange(n, m*n, 2)), axis=0)
        self.rowinds = rowinds
        self.colinds = colinds

        # Define conductivity among interior nodes. Fill in one value,
        # InnerConduits, for conductivities among nodes within colony.
        self.InnerConduits = np.array([InnerConductivity] * len(rowinds))

        # Combine node connection indices to form upper triangular part of
        # adjacency matrix for internal nodes
        UpperAdjacency = sparse.coo_matrix(
            ([1] * len(rowinds), (rowinds, colinds)), [m*n, m*n])
        self.UpperAdjacency = UpperAdjacency
        Adjacency = UpperAdjacency + UpperAdjacency.transpose()
        self.Adjacency = Adjacency.tocsr()

        # Create degree matrix (connections per node) for internal nodes
        Degree = sparse.diags(
            Adjacency.sum(axis=1).transpose().tolist()[0], 0)

        # Create Laplacian matrix of internal nodes
        self.Laplacian = (Adjacency - Degree).tocsr()

        # COO matrix sorts row indices, so convenient for finding sorted edges
        # to make incidence matrix for internal nodes.
        self.Incidence = (sparse.coo_matrix(([-1]*len(rowinds),
            (arange(len(rowinds)), rowinds)), [UpperAdjacency.nnz, n*m]) +
            sparse.coo_matrix(([1]*len(colinds),
            (arange(len(colinds)), colinds)), [len(rowinds), n*m]))

        # Define default conductivity for leakage from internal nodes to
        # outside node.
        self.OutflowConduits = np.array([OutflowConductivity]*(m*n))

        # Set default inflow magnitudes at each node
        self.InFlow = np.array([Incurrents]*(m*n))

        # Still need to add A) edges going out of colony

        # Set parameters for function for determining dConductivity/dt.
        self.dCdt_inner = dCdt_inner
        self.dCdt_outer = dCdt_outer

    def setouterconductivities(self, nodeinds, NewOuterConductivities):
        """
        Modify conductivity of edges connecting inner nodes (colony) to
        outside.
        
        Parameters
        ----------
        nodeinds : list
            List of indices of nodes to change (m*n>int>0)
        NewOuterConductivities : list
            List of new conductivities to apply (numeric & >0, same length as
            nodeinds)
        """
        if not (isinstance(NewOuterConductivities, list) and
                isinstance(nodeinds, list)):
            print('Arguments must be lists. No action taken.')
            return
        elif len(NewOuterConductivities) != len(nodeinds):
            print('List lengths must match. No action taken.')
            return
        elif (max(nodeinds) > (self.m*self.n)):
            print('At least one node index is >m*n. No action taken.')
            return
        elif (min(nodeinds) < 0):
            print('At least one node index is <0. No action taken.')
            return
        elif any(not isinstance(item, int) for item in nodeinds):
            print('At least one node index is not an int. No action taken.')
            return
        elif any(item < 0 and isinstance(item, (int, float))
                    for item in NewOuterConductivities):
            print('Conductivities must be floats or ints ≥0. No action taken.')
            return
        else:
            for k in range(len(nodeinds)):
                self.OutflowConduits[nodeinds[k]] = NewOuterConductivities[k]

    def solvecolony(self, calcflows=True, calcdCdt = False, **kwargs):
        """
        Solve matrix equations for pressures at nodes, flows between nodes, and
        'shear-like' property (S) and dC/dt (a function of S).

        Because often want to pass different results of different steps in
        calculating pressures to other calculations, bring them all togeher 
        here.

        First: Combines vectors of conductivities of internal edges
        (conduits) and edges connecting internal (colony) nodes to outside
        into one diagonal matrix. (conductivitymat = C)

        Second: Adds edges connecting internal nodes to outside to incidence
        matrix. (IncidenceFull = E)

        Third: Calculates pressures based on given inflow rates (from pumps)
        assuming volume conservation (Kirschoff's law). Vector of inflow rates,
        InFlow = q Pressure list = Pressures = p.
        Therefore, solve transpose(E)*C*E*p == q for p

        Fourth: Calculate flows (f) among all nodes (including outside node) as
        C*E*p = f

        Finally: Calculate dC/dt & 'S' (quantifier of flow vs conductivity). 

        Parameters
        ----------
        self : colony object
        **kwargs : dictionary
            Can contain full conductivity matrix and full incidence matrix
            (as sparse matrices), plus pressure matrix. Allows passing
            approximate solutions (from earlier calls) to future calls to this
            function.
        calcflows : boolean
            True: caclulate flows based on pressures
        calcshearlike : boolean
            True: caclulate S based on pressures

        Returns
        -------
        dictionary : 
            dictionary stores conductivitymat (diagonal matrix of all 
            conductivities, inner and outer), IncidenceFull (incidence matrix
            including inner & outer connections), pressures, flows, S, & dC/dt
        """
        # Combine inner and outflow conduits into one diagonal conductivity
        # matrix.
        if (kwargs.get('conductivityfull') is None):
            conductivityfull = sparse.diags(concatenate(
                (self.InnerConduits, self.OutflowConduits)), 0)
        else:
            conductivityfull = kwargs.get('conductivityfull')
            
        # Add edges to outside to incidence matrix. Note that only add entry
        # for internal node (tail of edge) not outside, because including
        # including outer node makes matrix only solvable to an additive
        # constant.
        if (kwargs.get('IncidenceFull') is None):
            IncidenceFull = sparse.vstack((
                self.Incidence, sparse.diags(([-1]*(self.m*self.n)), 0).tocsr()
                ))
        else:
            IncidenceFull = kwargs.get('IncidenceFull')
            
        # Calculate pressures based on Kirchoff's current law. A few tests 
        # indicate that the biconjugate gradient stabilized method (bicgstab)
        # is almost 100x faster than the direct method; with an initial
        # pressure solution, it may be 2x faster still (though my test for that
        # may be biased: I used the direct solution as the initial estimate, so
        # it was already right on the best value.
        if (kwargs.get('Pressures') is None):
            Pressures = bicgstab(
                    IncidenceFull.transpose()*conductivityfull
                    *IncidenceFull, np.asmatrix(self.InFlow).transpose())[0]            
        else: 
            Pressures = bicgstab(
                IncidenceFull.transpose()*sparse.diags(conductivityfull,0)
                *IncidenceFull, np.asmatrix(self.InFlow).transpose(), 
                x0=kwargs.get('Pressures'))[0]

        networksols = {"Pressures": Pressures, "conductivityfull":
            conductivityfull, "IncidenceFull": IncidenceFull}
            
        # Calculate flows based on pressure, conductivities, and connectivity
        if calcflows:
            networksols["Flows"] = conductivityfull*IncidenceFull*np.asmatrix(
                    Pressures).transpose()

        # Calculate match between flow and conduit size ('S' ~ shear in
        # Murray's Law) based on pressure, conductivities, and connectivity
        if calcdCdt and not (self.dCdt_inner is None) and not (
                            self.dCdt_outer is None):
            dP = np.asarray(
                abs(
                IncidenceFull * np.asmatrix(Pressures).transpose())).flatten()
            dPinner = dP[:self.InnerConduits.size]
            dPouter = dP[self.InnerConduits.size:]
            dCdt_i, S_i = self.dCdt_inner(self.InnerConduits, dPinner)
            dCdt_o, S_o = self.dCdt_outer(self.OutflowConduits, dPouter)
            networksols["S"] = concatenate((S_i, S_o))
            networksols["dCdt"] = concatenate((dCdt_i, dCdt_o))

        return networksols

    def colonyplot(self, addspy=True, linescale=1, dotscale=10,
                   outflowscale=10, innerflowscale=40):
        """
        Create plots of colony object properties
         self: Colony object
         addspy: create optional colony object
         linescale: multiply line widths (inner conductivities) by scalar.
         dotscale: multiply dot sizes (conductivity to outside) by scalar.
         outflowscale: multiplies symbol for outflow width
         innerflowscale: magnitude of inner flow vectors divided by
         innerflowscale for the plot.

        Plots produced: Plots circles for nodes (scaled by conductivity to
        outside node), lines for edges between nodes (width scaled to
        conductivity), and quiver plot for flows between internal nodes.
        """
        # Plot lines for edges among internal nodes; line width: conductivity
        # Convert coordinates of node-pairs to x-y coordinates of line segments
        segments = stack((
            vstack((self.xs[self.rowinds], self.xs[self.colinds])), 
            vstack((self.ysjig[self.rowinds], self.ysjig[self.colinds]))
            )).transpose()
        # Create matplotlib.collections.LineCollection object from segments,
        # with widths defined by conduit conductivity
        edges = LineCollection(segments,
                               linewidths = dot(linescale, self.InnerConduits))
        # Plot segments.
        plt.gca().add_collection(edges)
        # Only included these two lines setting xlim & ylim for ease if want to
        # plot just this part; not necessary if scatter plot defines x-y axes.
        plt.xlim(-0.5, self.xs.max() + 0.5)
        plt.ylim(-0.5, self.ysjig.max() + 0.5)

        # Make scatter plot of outflow conduit conductivities (conductivities
        # between internal nodes and outside.)
        plt.scatter(self.xs, self.ysjig,
                    s=dot(dotscale, self.OutflowConduits))

        # Solve for flows in network. solveflow returns flows; convert flow
        # matrix to array.
        Flows = np.array(self.solvecolony().get("Flows"))
        # Separate inner and outer flows
        OuterFlows = Flows[len(self.rowinds):]
        InnerFlows = Flows[:len(self.rowinds)].flatten()
        # Plot flow from nodes to outside
        plt.scatter(self.xs, self.ysjig, s=(outflowscale*OuterFlows).tolist(),
                    c='r', marker='*')
        # Plot flows between inner nodes. First get orientation vector (not a
        # unit vector) and its magnitude to use to determine x, y components of
        # flow vectors.
        Orientation_Vect = vstack((self.xs[self.colinds]-self.xs[self.rowinds],
                        self.ysjig[self.colinds] - self.ysjig[self.rowinds]))
        Mag_Orientation_Vect = sum(Orientation_Vect**2)**(0.5)
        plt.quiver((self.xs[self.rowinds] + self.xs[self.colinds])/2,
                   (self.ysjig[self.rowinds] + self.ysjig[self.colinds])/2,
                    InnerFlows*Orientation_Vect[0,:]/Mag_Orientation_Vect,
                    InnerFlows*Orientation_Vect[1,:]/Mag_Orientation_Vect,
                    pivot='mid', scale=innerflowscale)

        # Optional plot of adjacency matrix.
        if addspy:
            plt.figure()
            plt.spy(self.Adjacency)

# Demonstration.
c1 = Colony(2, 3, OutflowConductivity=0.1, 
            dCdt_inner=lambda x, y: dCdt_fun_gen(x, y, z=0.33, b=1, r=1), 
        dCdt_outer= lambda x, y: dCdt_fun_gen(x, y, z=0.33, b=1, r=1))  # Create colony object.
c1.colonyplot(False, 1, 100, 100)
c1.setouterconductivities([5, 6], [10, 10])
plt.figure()
c1.colonyplot(False, 1, 100, 100)
