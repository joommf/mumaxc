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
    """Convert ubermag subregions and changing Ms values into mumax3 regions."""
    # region refers to mumax3; subregion refers to ubermag
    system.m.orientation.write("m0.omf")  # TODO: 3 lines can be moved to drive script.
    mx3 = "// Magnetisation\n"
    mx3 += 'm.LoadFile("m0.omf")\n'

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
    unique_index = 0

    for sr_index, sr_name in sr_dict.items():
        for ms in np.unique(Ms_array[sr_indices == sr_index]):
            if ms == 0:
                continue
            if unique_index > max_index:
                raise ValueError(
                    "mumax3 does not allow more than 256 seperate regions to be set."
                    " The number of mumax3 regions is determined by the number of"
                    " unique combinations of `discretisedfield` subregions and"
                    " saturation magnetisation values."
                )
            mx3 += f"Msat.setregion({unique_index}, {ms})\n"
            region_indices[(sr_indices == sr_index) & (Ms_array == ms)] = unique_index
            region_relator[sr_name].append(unique_index)
            unique_index += 1

    df.Field(system.m.mesh, dim=1, value=region_indices).write("mumax3_regions.omf")
    system.region_relator = region_relator
    mx3 += '\nregions.LoadFile("mumax3_regions.omf")\n\n'
    return mx3


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
        names = system.m.mesh.subregions.keys()
        subregions_dict = dict(zip(names, range(len(names))))

        for key, value in parameter.items():
            if isinstance(value, numbers.Real):
                mx3 += f"{name}.setregion({subregions_dict[key]}, {value})\n"

            elif isinstance(value, (list, tuple, np.ndarray)):
                mx3 += (
                    f"{name}.setregion({subregions_dict[key]}, "
                    "vector({}, {}, {}))\n".format(*value)
                )

    else:
        # In mumax3, the parameter cannot be set using Field.
        msg = f"Cannot use {type(parameter)} to set parameter."
        raise TypeError(msg)

    return mx3
