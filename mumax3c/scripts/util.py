import contextlib
import itertools
import numbers

import discretisedfield as df
import numpy as np


def _identify_subregions(system):
    subregion_indices = np.zeros((*system.m.mesh.n, 1), dtype=int)
    subregion_dict = {0: ""}
    if system.m.mesh.subregions:
        subregion_dict.update(zip(itertools.count(start=1), system.m.mesh.subregions))
        # Reversed to get same functionality as oommf if subregions overlap
        for sr_index, sr_name in reversed(subregion_dict.items()):
            with contextlib.suppress(KeyError):
                slices = system.m.mesh.region2slices(system.m[sr_name].mesh.region)
                subregion_indices[slices] = sr_index
    return subregion_indices, subregion_dict


def mumax3_regions(system):
    """Convert ubermag subregions and changing Ms values into mumax3 regions.

    In this method, 'region' refers to mumax3, 'subregion refers to ubermag.
    """
    mx3 = ""
    sr_indices, sr_dict = _identify_subregions(system)

    Ms_array = system.m.norm.array
    if np.any(np.isnan(Ms_array)):  # Not sure about this.
        raise ValueError("Ms values cannot be nan.")
    if 0 in Ms_array:
        region_indices = np.full((*system.m.mesh.n, 1), fill_value=255)
        mx3 += "Msat.setRegion(255, 0.0)\n"
        max_index = 254
    else:
        region_indices = np.empty((*system.m.mesh.n, 1))
        max_index = 255

    # dict.fromkeys(..., []) would use the same list for all items
    region_relator = dict.fromkeys(sr_dict.values())
    for key in region_relator:
        region_relator[key] = []
    unique_index = -1

    for sr_index, sr_name in sr_dict.items():
        for ms in unique_with_accuracy(Ms_array[sr_indices == sr_index]):
            if ms == 0:
                continue
            unique_index += 1
            mx3 += f"Msat.setregion({unique_index}, {ms})\n"
            region_indices[
                (sr_indices == sr_index) & np.isclose(Ms_array, ms)
            ] = unique_index
            region_relator[sr_name].append(unique_index)

    if unique_index > max_index:
        raise ValueError(
            "mumax3 does not allow more than 256 seperate regions to be set. The"
            " number of mumax3 regions is determined by the number of unique"
            " combinations of `discretisedfield` subregions and saturation"
            f" magnetisation values. Found {len(system.m.mesh.subregions)} subregions"
            f" and {len(unique_with_accuracy(Ms_array))} Ms values resulting in"
            f" {unique_index} mumax3 regions."
        )

    df.Field(system.m.mesh, dim=1, value=region_indices).write("mumax3_regions.omf")
    system.region_relator = region_relator
    mx3 += '\nregions.LoadFile("mumax3_regions.omf")\n\n'
    return mx3


def unique_with_accuracy(array, accuracy=14):
    """Find unique float values with accuracy post-decimal digits.

    The method divides the input by its maximum value to ensure that the values have the
    form 0.xxx. Rounding is then done with ``accuracy`` post-decimal digits.

    """
    if len(array.flat) <= 1:
        return np.array(array.flat)
    array_max = np.max(array)
    return np.unique(np.round(array / array_max, decimals=accuracy)) * array_max


def set_parameter(parameter, name, system):
    mx3 = ""
    # Spatially constant scalar parameter.
    if isinstance(parameter, numbers.Real):
        mx3 += f"{name} = {parameter}\n"

    # Spatially constant vector parameter.
    elif isinstance(parameter, (list, tuple, np.ndarray)):
        mx3 += "{} = vector({}, {}, {})\n".format(name, *parameter)

    # Spatially varying parameter defined using subregions.
    elif isinstance(parameter, dict):
        for key, value in parameter.items():
            if ":" in key:
                mx3 += _set_inter_reg_params(key, value, name, system)
            else:
                for region in system.region_relator[key]:
                    if isinstance(value, numbers.Real):
                        mx3 += f"{name}.setregion({region}, {value})\n"
                    elif isinstance(value, (list, tuple, np.ndarray)):
                        mx3 += (
                            f"{name}.setregion({region}, "
                            "vector({}, {}, {}))\n".format(*value)
                        )

    else:
        # In mumax3, the parameter cannot be set using Field.
        msg = f"Cannot use {type(parameter)} to set parameter."
        raise TypeError(msg)

    return mx3


def _set_inter_reg_params(key, value, name, system):
    sub_regions = key.split(":")
    if name not in {"Aex", "Dind"}:  # ext_InterDbulk not available.
        raise ValueError(
            "Only Aex and Dind can be set for different region in mumax3."
            f" Cannot set inter region {name}"
        )
    # elif np.any([len(system.region_relator[sub_reg]) > 1 for sub_reg in sub_regions]):
    #     raise ValueError(
    #         "For now, cannot set inter subregion Exchange or DMI when one of"
    #         " the subregions has more than one Ms values excluding Ms = 0."
    #         f" The subregions to mumax3 regions relation is {system.region_relator}"
    #     )
    else:
        reg_combinations = itertools.product(
            system.region_relator[sub_regions[0]], system.region_relator[sub_regions[1]]
        )
        for reg_pair in reg_combinations:
            if name == "Aex":
                return f"\next_InterExchange({reg_pair[0]}, {reg_pair[1]}, {value})\n"
            else:
                return f"\next_InterDind({reg_pair[0]}, {reg_pair[1]}, {value})\n"
