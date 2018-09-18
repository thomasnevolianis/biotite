# This source code is part of the Biotite package and is distributed
# under the 3-Clause BSD License. Please see 'LICENSE.rst' for further
# information.

"""
This module provides functions for hydrogen bonding calculation.
"""

__author__ = "Daniel Bauer, Patrick Kunzmann"
__all__ = ["hbond", "hbond_frequency"]

from .geometry import distance, angle
import numpy as np
from .atoms import AtomArrayStack, stack
from .celllist import CellList


def hbond(atoms, selection1=None, selection2=None, selection1_type='both',
          cutoff_dist=2.5, cutoff_angle=120,
          donor_elements=('O', 'N', 'S'), acceptor_elements=('O', 'N', 'S')):
    """
    Find hydrogen bonds in a structure.
    
    The default criteria is: :math:`\\theta > 120deg` and :math
    :math:`\\text(H..Acceptor) <= 2.5 A` [1]_
    
    Parameters
    ----------
    atoms : AtomArray or AtomArrayStack
        The atoms to find hydrogen bonds in.
    selection1, selection2: ndarray or None
        Boolean mask for atoms to limit the hydrogen bond search to
        specific sections of the model. The shape must match the
        shape of the `atoms` argument. If None is given, the whole atoms
        stack is used instead. (Default: None)
    selection1_type: {'acceptor', 'donor', 'both'}, optional (default: 'both')
        Determines the type of `selection1`.
        The type of `selection2` is chosen accordingly
        ('both' or the opposite).
        (Default: 'both')
    cutoff_dist: float
        The maximal distance between the hydrogen and acceptor to be
        considered a hydrogen bond. (Default: 2.5)
    cutoff_angle: float
        The angle cutoff in degree between Donor-H..Acceptor to be
        considered a hydrogen bond (default: 120).
    donor_elements, acceptor_elements: tuple of str
        Elements to be considered as possible donors or acceptors
        (default: O, N, S).
    vectorized: bool
        Enable/Disable vectorization across models. Vectorization is
        faster, but requires more memory (default: True).
        
    Returns
    -------
    triplets : ndarray, dtype=int, shape=(n,3)
        *n x 3* matrix containing the indices of every Donor-H..Acceptor
        interaction that is available in any of the models.
        *n* is the number of found interactions.
        The three matrix columns are *D_index*, *H_index*, *A_index*.
        If only one model (`AtomArray`) is given, `triplets` contains
        all of its hydrogen bonds.
    mask : ndarry, dtype=bool, shape=(m,n)
        *m x n* matrix that shows if an interaction with index *n* in
        `triplets` is present in the model *m* of the input `atoms`.
        Only returned if `atoms` is an `AtomArrayStack`.
        
    Examples
    --------
    Calculate the number and frequency of each hydrogen bond between
    the p-Helix and the selecivity filter of KcsA (PDB: 2KB1)

    >>> stack = load_structure("2KB1.pdb")
    >>> a = a[:, a.chain_id == 'A']
    >>> p_helix = (a.res_id >= 40) & (a.res_id <= 52)
    >>> sf = (a.res_id >= 53) & (a.res_id <= 58)

    Get hydrogen bonds and frequency :

    >>> triplets, mask = hbond(a, selection1=p_helix, selection2=sf)
    >>> freq = hbond_frequency(mask)

    Create names of individual bonds:
    >>> label = "{d_resid}{d_resnm}-{d_a} -- {a_resid}{a_resnm}-{a_a}"
    >>> names = [label.format(
    >>>     d_resid=a.res_id[donor],
    >>>     d_resnm=a.res_name[donor],
    >>>     d_a=a.atom_name[donor],
    >>>     a_resid=a.res_id[acceptor],
    >>>     a_resnm=a.res_name[acceptor],
    >>>     a_a=a.atom_name[acceptor]) for donor, _, acceptor in triplets]
    
    Print hydrogen bonds with their frequency:
    >>> for name, freq in zip(names, freq):
    >>>     print("{}: {}%".format(name, freq*100))
    53THR-N -- 49VAL-O: 10.0%
    53THR-N -- 50GLU-O: 25.0%
    53THR-N -- 51THR-O: 5.0%
    53THR-OG1 -- 49VAL-O: 5.0%
    53THR-OG1 -- 50GLU-O: 10.0%
    54THR-N -- 51THR-O: 90.0%
    54THR-N -- 52ALA-O: 5.0%
    55VAL-N -- 50GLU-O: 15.0%
    56GLY-N -- 50GLU-O: 20.0%
    57TYR-N -- 50GLU-OE1: 15.0%

    See Also
    --------
    hbond_frequency

    References
    ----------
    
    .. [1] EN Baker and RE Hubbard,
       "Hydrogen bonding in globular proteins"
       Prog Biophys Mol Biol, 44, 97-179 (1984).
    """

    # Create AtomArrayStack from AtomArray
    if not isinstance(atoms, AtomArrayStack):
        atoms = stack([atoms])
        single_model = True
    else:
        single_model = False
    
    # Mask for donor/acceptor elements
    donor_element_mask = np.isin(atoms.element, donor_elements)
    acceptor_element_mask = np.isin(atoms.element, acceptor_elements)

    if selection1 is None:
        selection1 = np.ones(atoms.array_length(), dtype=bool)
    if selection2 is None:
        selection2 = np.ones(atoms.array_length(), dtype=bool)

    if selection1_type == 'both':
        # The two selections are separated into three selections:
        # the original ones without the overlaping part
        # and one containing the overlap
        # This prevents redundant triplets and unnecessary computation 
        overlap_selection = selection1 & selection2
        # Original selections without overlaping part
        exclusive_selection1 = selection1 & (~overlap_selection)
        exclusive_selection2 = selection2 & (~overlap_selection)
        
        # Put selections to list for cleaner iteration
        selections = [
            exclusive_selection1, exclusive_selection2, overlap_selection
        ]
        selection_combinations = [
            #(0,0),   is not excluded, would be same selection
            #         as donor and acceptor simultaneously
            (0,1),
            (0,2),
            (1,0),
            #(1,1),   # same reason above
            (1,2),
            (2,0),
            (2,1),
            (2,2)     # overlaping part, combination is necessary
        ]
        
        all_comb_triplets = []
        all_comb_mask = []
        for selection_index1, selection_index2 in selection_combinations:
            donor_mask = selections[selection_index1]
            acceptor_mask = selections[selection_index2]
            if  np.count_nonzero(donor_mask) != 0 and \
                np.count_nonzero(acceptor_mask) != 0:
                    # Calculate triplets and mask
                    triplets, mask = _hbond(
                        atoms, donor_mask, acceptor_mask,
                        donor_element_mask, acceptor_element_mask,
                        cutoff_dist, cutoff_angle,
                        donor_elements, acceptor_elements
                    )
                    all_comb_triplets.append(triplets)
                    all_comb_mask.append(mask)
        # Merge results from all combinations
        triplets = np.concatenate(all_comb_triplets, axis=0)
        mask = np.concatenate(all_comb_mask, axis=1)

    elif selection1_type == 'donor':
        triplets, mask = _hbond(
            atoms, selection1, selection2,
            donor_element_mask, acceptor_element_mask,
            cutoff_dist, cutoff_angle,
            donor_elements, acceptor_elements
        )
    
    elif selection1_type == 'acceptor':
        triplets, mask = _hbond(
            atoms, selection2, selection1,
            donor_element_mask, acceptor_element_mask,
            cutoff_dist, cutoff_angle,
            donor_elements, acceptor_elements
        )
    
    else:
        raise ValueError(f"Unkown selection type '{selection1_type}'")

    if single_model:
        # For a atom array (not stack),
        # hbond_mask contains only 'True' values,
        # since all interaction are in the one model
        # -> Simply return triplets without hbond_mask
        return triplets
    else:
        return triplets, mask


def _hbond(atoms, donor_mask, acceptor_mask,
           donor_element_mask, acceptor_element_mask,
           cutoff_dist, cutoff_angle, donor_elements, acceptor_elements):
    
    # Filter donor/acceptor elements
    donor_mask    &= donor_element_mask
    acceptor_mask &= acceptor_element_mask
    
    def _get_bonded_hydrogens(array, donor_mask, cutoff=1.5):
        """
        Helper function to find indices of associated hydrogens in atoms
        for all donors in atoms[donor_mask].
        The criterium is that the hydrogen must be in the same residue
        and the distance must be smaller than the cutoff.

        """
        coord = array.coord
        res_id = array.res_id
        hydrogen_mask = (array.element == "H")
        
        donor_hydrogen_mask = np.zeros(len(array), dtype=bool)
        associated_donor_indices = np.full(len(array), -1, dtype=int)

        donor_indices = np.where(donor_mask)[0]
        for donor_i in donor_indices:
            candidate_mask = hydrogen_mask & (res_id == res_id[donor_i])
            distances = distance(
                coord[donor_i], coord[candidate_mask]
            )
            donor_h_indices = np.where(candidate_mask)[0][distances <= cutoff]
            for i in donor_h_indices:
                associated_donor_indices[i] = donor_i
                donor_hydrogen_mask[i] = True
        
        return donor_hydrogen_mask, associated_donor_indices
            

    # TODO use BondList if available
    donor_h_mask, associated_donor_indices \
        = _get_bonded_hydrogens(atoms[0], donor_mask)
    donor_h_i = np.where(donor_h_mask)[0]
    acceptor_i = np.where(acceptor_mask)[0]
    if len(donor_h_i) == 0 or len(acceptor_i) == 0:
        # Return empty triplets and mask
        return (
            np.zeros((0,3), dtype=int),
            np.zeros((atoms.stack_depth(),0), dtype=bool)
        )
    
    # Narrow the amount of possible acceptor to donor-H connections
    # down via the distance cutoff parameter using a cell list
    # Save in acceptor-to-hydrogen matrix
    # (true when distance smaller than cutoff)
    coord = atoms.coord
    possible_bonds = np.zeros(
        (len(acceptor_i), len(donor_h_i)),
        dtype=bool
    )
    for model_i in range(atoms.stack_depth()):
        donor_h_coord = coord[model_i, donor_h_mask]
        acceptor_coord = coord[model_i, acceptor_mask]
        cell_list = CellList(donor_h_coord, cell_size=cutoff_dist)
        possible_bonds |= cell_list.get_atoms_in_cells(
            acceptor_coord, as_mask=True
        )
    possible_bonds_i = np.where(possible_bonds)
    # Narrow down
    acceptor_i = acceptor_i[possible_bonds_i[0]]
    donor_h_i = donor_h_i[possible_bonds_i[1]]
    
    # Build D-H..A triplets
    donor_i = associated_donor_indices[donor_h_i]
    triplets = np.stack((donor_i, donor_h_i, acceptor_i), axis=1)
    # Remove entries where donor and acceptor are the same
    triplets = triplets[donor_i != acceptor_i]

     # Filter triplets that meet distance and angle condition
    def _is_hbond(donor, donor_h, acceptor, cutoff_dist=2.5, cutoff_angle=120):
        cutoff_angle_rad = np.deg2rad(cutoff_angle)
        theta = angle(donor, donor_h, acceptor)
        dist = distance(donor_h, acceptor)
        return (theta > cutoff_angle_rad) & (dist <= cutoff_dist)
    
    hbond_mask = _is_hbond(
        coord[:, triplets[:,0]],  # donors
        coord[:, triplets[:,1]],  # donor hydrogens
        coord[:, triplets[:,2]],  # acceptors
        cutoff_dist=cutoff_dist, cutoff_angle=cutoff_angle
    )

    # Reduce output to contain only triplets counted at least once
    is_counted = hbond_mask.any(axis=0)
    triplets = triplets[is_counted]
    hbond_mask = hbond_mask[:, is_counted]

    return triplets, hbond_mask


def hbond_frequency(mask):
    """
    Get the relative frequency of each hydrogen bond in a multi-model
    structure.

    The frequency is the amount of models, where the respective bond
    exists divided by the total amount of models.
    
    Parameters
    ----------
    mask: ndarray, dtype=bool, shape=(m,n)
        Input mask obtained from `hbond` function.
    
    Returns
    -------
    ndarray, dtype=Float
        For each individual interaction *n* of the mask, returns the
        percentage of models *m*, in which this hydrogen bond is
        present.

    See Also
    --------
    hbond

    Examples
    --------

    >>> stack = load_structure("path/to/1l2y.pdb")
    >>> triplets, mask = hbond(stack)
    >>> freq = hbond_frequency(mask)
    >>> print(freq)
    [0.10526316 0.23684211 0.02631579 0.23684211 0.05263158 0.26315789
     0.02631579 0.28947368 0.10526316 0.39473684 1.         1.
     1.         1.         0.02631579 0.02631579 0.02631579 0.02631579
     0.02631579 0.42105263 0.31578947 0.92105263 0.81578947 0.86842105
     0.02631579 0.21052632 0.10526316 0.92105263 0.07894737 0.02631579
     0.34210526 0.10526316 0.02631579 0.31578947 0.23684211 0.42105263
     0.13157895 0.07894737 0.02631579 0.05263158 0.02631579 0.15789474
     0.02631579 0.05263158 0.13157895 0.18421053]
    """
    return mask.sum(axis=0)/len(mask)
