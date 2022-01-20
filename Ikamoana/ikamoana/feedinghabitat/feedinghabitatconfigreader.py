# -*- coding: utf-8 -*-

"""
This module is used by the feedingHabitat module to setup all variables
and parameters. It use a XML configuration file that link to all the
netCDF or DYM files used to compute de feeding habitat.
It also compute the day length in the area using the PISCES method.

Warnings
--------
0.000001 is automatically added on forage layer to copy SEAPODYM behavior.

See Also
--------
- feedingHabitat.FeedingHabitat : class used to compute feeding habitat

.. E. Maier-Reimer (GBC 1993)
    Day length calculation.

"""

import xml.etree.ElementTree as ET
from math import acos, asin, pi, sin, tan
from os.path import exists, dirname

import numpy as np
import pandas as pd
import xarray as xr

from .. import dymfiles as df

# TODO : à terme, la lecture du fichier configuration de SEAPODYM
# dépasse le cadre de l'habitat d'alimentation. il devrait être lu par
# un module externe qui retournerai les balises ainsi que leurs valeurs.
# Lesquelles seraient utilisées pour produire la structure de données
# de l'habitat (ou bien d'autres modules tels qu'IKAMOANA).

# TODO : Supprimer le champ layer_number s'il n'est plus utile.
# WARNING : 0.000001 is added on forage layer to copy SEAPODYM behavior.

def seapodymFieldConstructor(
        filepath: str, dym_varname : str = None, dym_attributs : dict = None
        ) -> xr.DataArray :
    """
    Return a Seapodym field as a DataArray using NetCDF or Dym method
    according to the file extension : 'nc', 'cdf' or 'dym'.

    Parameters
    ----------
    filepath : str
        The path to the NetCDF or DYM.
    dym_varname : str, optional
        If the file is a DYM, dym_varname is the name of the variable
        represented inside the file. By default None which is replaced
        by the filepath.
    dym_attributs : str, optional
        If the file is a DYM, dym_attributs is , by default None

    Returns
    -------
    xr.DataArray
        [description]
    """
    if exists(filepath) :
        #NetCDF
        if filepath.lower().endswith(('.nc', '.cdf')) :
            return xr.open_dataarray(filepath)
        #DymFile
        if filepath.lower().endswith('.dym') :
            if dym_varname is None :
                dym_varname = filepath
            return df.dym2ToDataArray(infilepath = filepath,
                                      varname = dym_varname,
                                      attributs = dym_attributs)
    else :
        raise ValueError("No such file : {}".format(filepath))

###############################################################################
# ---------------------------- READ XML FILE -------------------------------- #
###############################################################################

def _loadMask(variables_dictionary, from_text=None, expend_time=True) :
    """
    Load a mask file (i.e. texte file) as a dictionary of numpy array.
    Each array corresponds to a pelagic layer (i.e. L1, L2 and L3).

    Parameters
    ----------
    variables_dictionary : dict
        Contains all variables used by the FeedingHabitat module. Must
        contains "temperature_L1".
    from_text : string, optional
        Text file used to compute the mask. If from_text is None, the
        Nan values of the temperature_L(1, 2 and 3) netCDF will be used.
        The default is None.
    expend_time : boolean, optional
        Add a time axis to broadcast mask on variables. Cf. Numpy broadcast.
        The default is True.

    Notes
    -----
    Mask file must contains 4
    values :
        - 0 = Ground / Land / etc...
        - 1 = L1 / epipelagic
        - 2 = L2 / upper mesopelagic
        - 3 = L3 / lower mesopelagic

    Returns
    -------
    global_mask : dict.
        The dictionary contains "mask_L1", "mask_L2", "mask_L3" which are
        numpy arrays.

    """

    # Read mask values #################################################
    if from_text is None :
        tmp_mask = (
            np.isfinite(variables_dictionary["temperature_L1"].sel(
                variables_dictionary["temperature_L1"].time.data[0]))
            + np.isfinite(variables_dictionary["temperature_L2"].sel(
                variables_dictionary["temperature_L2"].time.data[0]))
            + np.isfinite(variables_dictionary["temperature_L3"].sel(
                variables_dictionary["temperature_L3"].time.data[0]))
            )
    else :
        tmp_mask = np.loadtxt(from_text)

    # Add a time axis to broadcast mask on variables ###################
    # i.e. Numpy broadcast method (Numpy)
    if expend_time :
        tmp_mask = tmp_mask[np.newaxis,:,:]

    # Separate each layer ##############################################
    global_mask = {"mask_L1" : ((tmp_mask == 1) + (tmp_mask == 2) + (tmp_mask == 3)),
                   "mask_L2" : ((tmp_mask == 2) + (tmp_mask == 3)),
                   "mask_L3" : (tmp_mask == 3)}

    return global_mask

def _dayLengthPISCES(jday, lat) :
    """
    Compute the day length depending on latitude and the day. New
    function provided by Laurent Bopp as used in the PISCES model and
    used by SEAPODYM in 2020.

    Parameters
    ----------
    jday : float
        Day of the year.
    lat : float
        Latitude.

    Modification
    ------------
    original       : E. Maier-Reimer (GBC 1993)
	additions      : C. Le Quere (1999)
	modifications  : O. Aumont (2004)
    	Adapted to C      : P. Lehodey (2005)
        Adapted to Python : J. Lehodey (2021)

    Returns
    -------
    float
        The duration of the day (i.e. while the sun is shining) as a ratio in
        range [0,1].

    """

    rum = (jday - 80.0) / 365.25
    delta = sin(rum * pi * 2.0) * sin(pi * 23.5 / 180.0)
    codel = asin(delta)
    phi = lat * pi / 180.0

    argu = tan(codel) * tan(phi)
    argu = min(1.,argu)
    argu = max(-1.,argu)

    day_length = 24.0 - (2.0 * acos(argu) * 180.0 / pi / 15 )
    day_length = max(day_length,0.0)

    return day_length / 24.0

def _daysLength(coords, model=None, float_32=True) :
    """
    Compute the day length using _dayLengthPISCES method.

    Parameters
    ----------
    coords : xarray.DataArray.coords
        Time, latitude and longitude from the temperature_L1 field.
    model : TYPE, optional
        Base the time, latitude and longitude on model.
        If model is None, base on coords (i.e. xarray.DataArray.coords).
        The default is None.
    float_32 : boolean, optional
        Set the time in float 32 or 64. If True, it is float 32.
        The default is True.

    Returns
    -------
    xarray.DataArray
        Contains the day length of each position on the studied area.

    """

    if model is not None :
        days_of_year = pd.DatetimeIndex(
            model['time'].data.astype('datetime64[D]')).dayofyear
        latitude = model['lat'].data
        longitude = model['lon'].data
    else :
        days_of_year = pd.DatetimeIndex(
            coords['time'].data.astype('datetime64[D]')).dayofyear
        latitude = coords['lat'].data
        longitude = coords['lon'].data

    buffer_list = []
    for day in days_of_year :
        for lat in latitude :
            day_length = _dayLengthPISCES(day, lat)
            if float_32 :
                day_length = np.float32(day_length)
            buffer_list.extend([day_length] * len(longitude))

    days_length = np.ndarray((len(days_of_year),len(latitude),len(longitude)),
                             buffer=np.array(buffer_list),
                             dtype=(np.float32 if float_32 else np.float64))

    return xr.DataArray(data=days_length,dims=["time", "lat", "lon"],
                        coords=dict(lon=longitude,lat=latitude,
                                    time=coords['time']),
                        attrs=dict(description="Day length.",units="hour"))

def _readXmlConfigFilepaths(root, root_directory, layers_number) :
    """Reads the NetCDF filepaths from the XML configuration file and
    returns them as a tuple."""

    # TEMPERATURE ######################################################
    temperature_filepaths = []
    for temp_file in root.find('strfile_t').attrib.values() :
        temperature_filepaths.append(root_directory +temp_file)

    # OXYGEN ###########################################################
    oxygen_filepaths = []
    for oxy_file in root.find('strfile_oxy').attrib.values() :
        oxygen_filepaths.append(root_directory+oxy_file)

    partial_oxygen_time_axis = int(root.find('type_oxy').attrib['value'])

    # FORAGE ###########################################################
    tmp_day = root.find('day_layer').attrib
    tmp_night = root.find('night_layer').attrib

    tmp_ordered_forage = {}
    ordered_forage = []

    for k_a, v_a in tmp_day.items() :
        for k_b, v_b in tmp_night.items() :
            if k_a == k_b :
                tmp_ordered_forage[k_a] = (v_a, v_b)

    key_list = list(tmp_ordered_forage.keys())
    val_list = list(tmp_ordered_forage.values())

    for x in range(layers_number) :
        for y in reversed(range(x+1)) :
            tmp_position = val_list.index((str(x),str(y)))
            ordered_forage.append(key_list[tmp_position])

    forage_directory  = root.find('strdir_forage').attrib['value']
    forage_filepaths = []
    #We will assume if the temp files are in dym format, so are the forage
    forage_filetype = ".dym" if temperature_filepaths[0].lower().endswith('.dym') else ".nc"
    for forage in ordered_forage :
        forage_filepaths.append(
            root_directory+forage_directory+'Fbiom_'+forage+forage_filetype)

    # SST #####################################################################
    if root.find('strfile_sst') is None :
        sst_filepath = None
    else :
        sst_filepath = root_directory + root.find('strfile_sst').attrib['value']

    # VLD #####################################################################
    if root.find('strfile_vld') is None :
        vld_filepath = None
    else :
        vld_filepath = root_directory + root.find('strfile_vld').attrib['value']

    # MASK ####################################################################
    if root.find('str_file_mask') == None :
        mask_filepath = None
    else :
        mask_filepath = root_directory + root.find('str_file_mask').attrib['value']

    return (temperature_filepaths, oxygen_filepaths, forage_filepaths, sst_filepath,
            vld_filepath, mask_filepath, partial_oxygen_time_axis)

def _readXmlConfigParameters(root) :
    """Reads the parameters from the XML configuration file and stores
    them in a dictionary."""

    parameters_dictionary = {}
    species_dictionary = {}

    # Species #################################################################
    sp_name = root.find('sp_name').text
    species_dictionary['sp_name'] = sp_name

    species_dictionary['nb_life_stages'] = int(
        root.find('nb_life_stages').attrib[sp_name])

    species_dictionary['life_stage'] = (
        root.find('life_stage').find(sp_name).text.split())

    species_dictionary['nb_cohort_life_stage'] = [
        int(x) for x in root.find('nb_cohort_life_stage').find(sp_name
                                                               ).text.split()]

    # Habitat parameters ######################################################
    parameters_dictionary["eF_list"] = [
        float(x.attrib[sp_name]) for x in root.find('eF_habitat')]

    parameters_dictionary["sigma_0"] = float(
        root.find('a_sst_spawning').attrib[sp_name])
    parameters_dictionary["sigma_K"] = float(
        root.find('a_sst_habitat').attrib[sp_name])

    parameters_dictionary["T_star_1"] = float(
        root.find('b_sst_spawning').attrib[sp_name])
    parameters_dictionary["T_star_K"] = float(
        root.find('b_sst_habitat').attrib[sp_name])

    parameters_dictionary["bT"] = float(
        root.find('T_age_size_slope').attrib[sp_name])

    parameters_dictionary["gamma"] = float(
        root.find('a_oxy_habitat').attrib[sp_name])

    parameters_dictionary["o_star"] = float(
        root.find('b_oxy_habitat').attrib[sp_name])

    parameters_dictionary["deltaT"] = float(
        root.find('deltaT').attrib["value"])

    ## NOTE :
    # - "space_reso" : Resolution in degrees
    # - "deltaX/Y" : Resolution in nautic miles
    parameters_dictionary["space_reso"] = float(
        root.find('space_reso').attrib["value"])

    return parameters_dictionary, species_dictionary

def _loadVariablesFromFilepaths(
        root, temperature_filepaths, oxygen_filepaths, forage_filepaths,
        sst_filepath, vld_filepath, mask_filepath, sp_name, float_32=True) :
    """Load all Seapodym Fields using the seapodymFieldConstructor
    method. Their are stored in a dictionary and returned."""

    variables_dictionary = {}

    # COORDS ##################################################################
    coords = seapodymFieldConstructor(temperature_filepaths[0], 'coords').coords

    # OXYGEN ##################################################################
    variables_dictionary["oxygen_L1"] = xr.apply_ufunc(
        np.nan_to_num,
        seapodymFieldConstructor(oxygen_filepaths[0], "oxygen_L1"))

    variables_dictionary["oxygen_L2"] = xr.apply_ufunc(
        np.nan_to_num,
        seapodymFieldConstructor(oxygen_filepaths[1], "oxygen_L2"))

    variables_dictionary["oxygen_L3"] = xr.apply_ufunc(
        np.nan_to_num,
        seapodymFieldConstructor(oxygen_filepaths[2], "oxygen_L3"))


    # TEMPERATURE #############################################################
    variables_dictionary["temperature_L1"] = xr.apply_ufunc(
        np.nan_to_num,
        seapodymFieldConstructor(temperature_filepaths[0], "temperature_L1"))

    variables_dictionary["temperature_L2"] = xr.apply_ufunc(
        np.nan_to_num,
        seapodymFieldConstructor(temperature_filepaths[1], "temperature_L2"))

    variables_dictionary["temperature_L3"] = xr.apply_ufunc(
        np.nan_to_num,
        seapodymFieldConstructor(temperature_filepaths[2], "temperature_L3"))


    # FORAGE ##################################################################
    # TODO : 0.000001 is added on forage layer to copy SEAPODYM behavior.
    #        Should it be removed ?
    def nan_add(data_array):
        return np.nan_to_num(data_array + 0.000001)

    variables_dictionary["forage_epi"] = xr.apply_ufunc(
        nan_add,
        seapodymFieldConstructor(forage_filepaths[0], "forage_epi"))

    variables_dictionary["forage_umeso"] = xr.apply_ufunc(
        nan_add,
        seapodymFieldConstructor(forage_filepaths[1], "forage_umeso"))

    variables_dictionary["forage_mumeso"] = xr.apply_ufunc(
        nan_add,
        seapodymFieldConstructor(forage_filepaths[2], "forage_mumeso"))

    variables_dictionary["forage_lmeso"] = xr.apply_ufunc(
        nan_add,
        seapodymFieldConstructor(forage_filepaths[3], "forage_lmeso"))

    variables_dictionary["forage_mlmeso"] = xr.apply_ufunc(
        nan_add,
        seapodymFieldConstructor(forage_filepaths[4], "forage_mlmeso"))

    variables_dictionary["forage_hmlmeso"] = xr.apply_ufunc(
        nan_add,
        seapodymFieldConstructor(forage_filepaths[5], "forage_hmlmeso"))


    # SST #####################################################################
    variables_dictionary["sst"] = xr.apply_ufunc(
        np.nan_to_num,
        seapodymFieldConstructor(sst_filepath, "sst"))

    # VLD #####################################################################
    variables_dictionary["vld"] = xr.apply_ufunc(
        np.nan_to_num,
        seapodymFieldConstructor(vld_filepath, "vld"))

    # LENGTHS, WEIGHT & AGE ###################################################
    cohorts_mean_length = np.array(
        [float(x) for x in root.find('length').find(sp_name).text.split()])
    cohorts_mean_weight = np.array(
        [float(x) for x in root.find('weight').find(sp_name).text.split()])
    cohorts_sp_unit = np.array(
        [float(x) for x in root.find('sp_unit_cohort').find(sp_name).text.split()])

    # MASK ####################################################################
    global_mask = _loadMask(variables_dictionary, from_text=mask_filepath)

    # DAY LENGTH ##############################################################
    variables_dictionary['days_length'] = _daysLength(coords, float_32=float_32)

    return (variables_dictionary,
            global_mask, coords,
            cohorts_mean_length,
            cohorts_mean_weight,
            cohorts_sp_unit)

###############################################################################
# ----------------------------- MAIN FUNCTION ------------------------------- #
###############################################################################

def loadFromXml(
        xml_filepath: str, root_directory: str = None,
        days_length_float_32: bool = True
        ) -> dict :
    """
    This is the main function used by the feedingHabitat module. It is
    used to read the XML configuration file and load all variables and
    parameters in the main class and also compute the day length.

    Parameters
    ----------
    xml_filepath : str
        The filepath to the FeedingHabitat XML configuration file.
    root_directory : str, optional
        If the configuration file is not in the root of the working
        directory, this directory path must be specified.
    days_length_float_32 : bool, optional
        Specify if the day length must be convert from float 64 to
        float32.

    Returns
    -------
    dict
        A dictionary containing all needed data by the FeedingHabitat
        constructor. Which are :
        - root_directory : str
        - output_directory : str
        - layers_number : int
        - cohorts_number : int
        - partial_oxygen_time_axis : bool
        - global_mask : dict
        - coords : xr.DataArray.coords
        - variables_dictionary : dict
        - parameters_dictionary : dict
        - species_dictionary : dict
    """

    # INITIALIZATION ##########################################################
    tree = ET.parse(xml_filepath)
    root = tree.getroot()

    # TODO : Verify
    # WARNING : os.path module is always the path module suitable
    # for the operating system Python is running on. dirname should
    # work on windows but it must be verified.
    if root_directory is None :
        prefix = dirname(xml_filepath)
        # Support windows paths using backslash ("\")
        prefix += "\\" if "\\" in prefix else "/"
    else :
        prefix = dirname(xml_filepath) if root_directory is None else root_directory

    root_directory = prefix + root.find('strdir').attrib['value']
    output_directory = root_directory + root.find('strdir_output').attrib['value']
    layers_number = int(root.find('nb_layer').attrib['value'])

    # Variables Filepaths #####################################################
    (temperature_filepaths,
     oxygen_filepaths,
     forage_filepaths,
     sst_filepath,
     vld_filepath,
     mask_filepath,
     partial_oxygen_time_axis) = _readXmlConfigFilepaths(
         root, root_directory, layers_number)

    # Parameters ##############################################################
    parameters_dictionary, species_dictionary = _readXmlConfigParameters(root)
    cohorts_number = sum([int(x) for x in (
        root.find('nb_cohort_life_stage').find(
            species_dictionary['sp_name']).text.split(' ')
        )])

    # Variables ###############################################################
    (variables_dictionary,
     global_mask, coords,
     cohorts_mean_length,
     cohorts_mean_weight,
     cohorts_sp_unit) = _loadVariablesFromFilepaths(root,
                                                    temperature_filepaths,
                                                    oxygen_filepaths,
                                                    forage_filepaths,
                                                    sst_filepath,
                                                    vld_filepath,
                                                    mask_filepath,
                                                    species_dictionary['sp_name'],
                                                    days_length_float_32)

    species_dictionary['cohorts_mean_length'] = cohorts_mean_length
    species_dictionary['cohorts_mean_weight'] = cohorts_mean_weight
    species_dictionary['cohorts_sp_unit'] = cohorts_sp_unit

    return dict(root_directory=root_directory,
                output_directory=output_directory,
                layers_number=layers_number,
                cohorts_number=cohorts_number,
                partial_oxygen_time_axis=partial_oxygen_time_axis,
                global_mask=global_mask,
                coords=coords,
                variables_dictionary=variables_dictionary,
                parameters_dictionary=parameters_dictionary,
                species_dictionary=species_dictionary)
