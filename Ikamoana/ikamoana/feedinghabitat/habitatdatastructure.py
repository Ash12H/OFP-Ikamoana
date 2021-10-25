"""
This module is used to declare the data structure that will store all
the data that the feedinghabitat module will use to calculate the
feeding habitat.
"""

from typing import List
import xarray as xr
import numpy as np
import warnings

def equalCoords(data_array_1: xr.DataArray,
                data_array_2: xr.DataArray,
                verbose: bool = False) -> bool :
    """Compare two DataArray coordinates"""

    if data_array_1.shape != data_array_2.shape :
        message_equalCoords = (
            ("Array_1(%s) and Array_2(%s) have different shapes :\n\t- Array_1 -> "%(
                data_array_1.name, data_array_2.name))
            + str(data_array_1.shape) + "\n\t- Array_2 -> " + str(data_array_2.shape)
        )
        warnings.warn(message_equalCoords)
        return False
    
    lat_comparison = data_array_1.lat.data == data_array_2.lat.data
    lat_condition = not (False in lat_comparison)
    
    lon_comparison = data_array_1.lon.data == data_array_2.lon.data
    lon_condition  = not (False in lon_comparison)
    
    time_comparison = data_array_1.time.data == data_array_2.time.data
    time_condition = not (False in time_comparison)
    
    if verbose :
        if not lat_condition :
            print("Latitude coordinates are different : %d errors for %d values."%(
                lat_comparison.size - np.sum(lat_comparison), lat_comparison.size))
        if not lon_condition :
            print("Longitude coordinates are different : %d errors for %d values."%(
                lon_comparison.size - np.sum(lon_comparison), lon_comparison.size))
        if not time_condition :
            print("Time coordinates are different : %d errors for %d values."%(
                time_comparison.size - np.sum(time_comparison), time_comparison.size))
    
    return lat_condition and lon_condition and time_condition

def groupArrayByCoords(variables_dictionary: dict) -> list :
    list_compare = []
    for _, item in variables_dictionary.items() :
        list_tmp = []
        for name_i, item_i in variables_dictionary.items() :
            if equalCoords(item, item_i) :
                list_tmp.append(name_i)
        list_compare.append(tuple(list_tmp))
    return list(set(list_compare))

def compareDims(data_array_1: xr.DataArray,
                data_array_2: xr.DataArray,
                dim: str,
                head: int = None):
    """Compare to DataArray coordinates along the 'dim' specified
    by user"""

    dim1 = data_array_1.coords[dim].data
    dim2 = data_array_2.coords[dim].data
    
    dim_comparison = dim1 == dim2
    
    if head is None :
        head = dim_comparison.size
    ite = 0
    for i in range(dim_comparison.size) :
        if (not dim_comparison[i]) and (ite < head) :
            print(dim1[i],'\t|||\t',dim2[i])
            ite = ite + 1
    if ite < dim_comparison.size :
        print('[...]')

class HabitatDataStructure :

    def __init__(self, kargs: dict) -> None :
        """
        Initialize the data structure according to the XML file used in
        the FeedingHabitat Class.

        Notes
        -----
        variables_dictionary contains :
            {"forage_epi", "forage_meso", "forage_mumeso",
             "forage_lmeso", "forage_mlmeso", "forage_hmlmeso" ,
             "temperature_L1", "temperature_L2", "temperature_L3",
             "oxygen_L1", "oxygen_L2", "oxygen_L3",
             "days_length",
             "zeu", "sst" }
        
        parameters_dictionary contains :
            {"eF_list",
             "sigma_0", "sigma_K", "T_star_1", "T_star_K", "bT",
             "gamma", "o_star" }
        
        species_dictionary contains :
            {'sp_name', 'nb_life_stages', 'life_stage',
             'nb_cohort_life_stage',
             'cohorts_mean_length', 'cohorts_mean_weight'}
        """
        
        self.root_directory           = kargs['root_directory']
        self.output_directory         = kargs['output_directory']
        self.layers_number            = kargs['layers_number']
        self.cohorts_number           = kargs['cohorts_number']
        self.cohorts_to_compute       = kargs['cohorts_to_compute']
        self.partial_oxygen_time_axis = kargs['partial_oxygen_time_axis']
        self.global_mask              = kargs['global_mask']
        self.coords                   = kargs['coords']
        self.variables_dictionary     = kargs['variables_dictionary']
        self.parameters_dictionary    = kargs['parameters_dictionary']
        self.species_dictionary       = kargs['species_dictionary']


    def setCohorts_to_compute(self, cohorts_to_compute: List[int]) -> None :
        """
        You can change the list of cohorts you want to compute the habitat at
        any moment by using this setter.

        Parameters
        ----------
        cohorts_to_compute : list of int
            If you want to perform a partial feeding habitat computation, you
            can  specify a group of cohort using a number corresponding to the
            position in the cohort list.
            Warning : The first cohort is number 0.
            For example, if you want to compute the feeding habitat of the
            second and third cohort : partial_cohorts_computation = [1,2].

        """
        self.cohorts_to_compute = cohorts_to_compute

    def summary(self) :

        #separator = "\n\n# ------------------------------------------------------------------- #\n\n"

        print("# ------------------------------ #")
        print("# Summary of this data structure #")
        print("# ------------------------------ #", end='\n\n')

        print('Root directory is :\t'+self.root_directory, end='\n')
        print('Output directory is :\t'+self.output_directory, end='')

        print("\n\n# -------------------------------SPECIES----------------------------- #\n\n")

        print('The short name of the species is %s.'%(self.species_dictionary["sp_name"]),end='\n')
        print('There is(are) %d\tlife stages considered in the model which are : '%(
            self.species_dictionary['nb_life_stages']),end='')
        print(self.species_dictionary['life_stage'],end='\n')
        for name, number in zip(self.species_dictionary['life_stage'], self.species_dictionary['nb_cohort_life_stage']) :
            print("\t- There is(are) %d\tcohort(s) in life stage %s."%(number, name))
        np.set_printoptions(suppress=True)
        print('\nMean length for each cohort is :\n', self.species_dictionary['cohorts_mean_length'])
        print('\nMean weight for each cohort is :\n', self.species_dictionary['cohorts_mean_weight'], end='')

        print("\n\n# -----------------------------PARAMETERS---------------------------- #\n\n")

        print('The parameters used are the following :')
        for name, value in self.parameters_dictionary.items() :
            print("\t- ",name,"   \t:", value)
        print("Reminder : \n\t- Forage \t-> eF\n\t- Temperature\t-> sigma, T* and bT\n\t- Oxygen \t-> gamma and O*",end='')

        print("\n\n# ------------------------------FIELDS------------------------------- #\n\n")

        print('WARNING : Fields must start on the same date !\n')

        print('Fields are grouped by coordinates :')

        for group in groupArrayByCoords(self.variables_dictionary) :
            print('\n#\t#\t#\t#\t#')
            print('Group :', group)
            print('Their coordinates are :\n',self.variables_dictionary[group[0]].coords)
        
        print('\n#\t#\t#\t#\t#\n')
        print('Day Length is calculated using the main coordinates which are based on temperature (L1) field.')

        if self.partial_oxygen_time_axis :
            print('\n#\t#\t#\t#\t#\n')
            print('Oxygen is a climatologic field. It meen that only 1 year is modelized in the DataArray.')

        print('\n#\t#\t#\t#\t#\n')
        print('TIPS : The user can use equalCoords() or compareDims() functions to compare Coordinates.',end='')
        
        print("\n\n# ------------------------------------------------------------------- #\n\n")
