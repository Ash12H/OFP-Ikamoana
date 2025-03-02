from typing import List, Tuple, Union
import numpy as np
import struct
import math
import parcels
from parcels.field import Field, Geographic, GeographicPolar
from parcels.fieldset import FieldSet
from parcels.particle import *
from netCDF4 import num2date
from datetime import datetime

## NOTE: this library is in maintenance mode and should not be used in new code.
# from py import path

from progressbar import ProgressBar
from glob import glob
from xml.dom import minidom

def getGradient(field: Field,
                landmask: Field = None,
                shallow_sea_zero=False,
                time_period=None):

    """
    Gradient calculation for a parcels Field seapodym-equivalent calculation
    requires LandMask forward and backward differencing for domain edges
    and land/shallow sea cells.
    """

    # Method to calculate cell sizes based on numpy.gradient method
    field.calc_cell_edge_sizes()
    # Previous cell sizes are stored in the field.grid.cell_edge_sizes dictionary
    dx, dy = field.grid.cell_edge_sizes['x'], field.grid.cell_edge_sizes['y'] #field.cell_distances()

## NOTE : Define start_time, end_time et tsteps
#
# This function could have the same behavior as the functions computeFeedingHabitat
# and computeEvolvingFeedingHabitat. It would take as arguments time_start,
# time_end, lat_min, lat_max, lon_min, lon_max.

    if time_period is not None:
        # Now we must convert the absolute time to time that is relative to the grid
        start_time = field.grid.time_origin.reltime(time_period[0])
        end_time = field.grid.time_origin.reltime(time_period[1])

        if field.grid.time[0] <= start_time:
            start = np.where(field.grid.time <= start_time)[0][-1]
        else:
            print("Warning! Requested start time for field gradient calculation\
             is before earliest field timestamp %s < %s ! Using first index" \
             % (str(start_time), str(field.grid.time[0])))
            start = 0
        if field.grid.time[-1] >= end_time:
            end = np.where(field.grid.time >= end_time)[0][0]
        else:
            print("Warning! Requested end time for field gradient calculation\
             is after latest field timestamp %s > %s ! Using last index" \
             % (str(end_time), str(field.grid.time[-1])))
            end = len(field.grid.time)
    else:
        start = 0
        end = len(field.grid.time)

    tsteps = range(start, end)

    ## Jules : Sélectionne une partie des données initialise dVdx et dVdy à la même taille

    data = field.data[range(start,end),:,:]
    dVdx = np.zeros(data.shape, dtype=np.float32)
    dVdy = np.zeros(data.shape, dtype=np.float32)

    nlat = len(field.grid.lat)
    nlon = len(field.grid.lon)

    ## Jules : Vérification des tailles de tableaux

## NOTE : What happens when landmask is not defined?

    if landmask is not None:
        landmask = np.transpose(landmask.data[0,:,:])
        if shallow_sea_zero :
            landmask[np.where(landmask == 2)] = 0
        X = nlon if nlon <= landmask.shape[0] else landmask.shape[0]
        Y = nlat if nlat <= landmask.shape[1] else landmask.shape[1]

        ## Jules : Cette boucle calcul le gradient en parcourant les cases une à une. Possiblement long.
        # Cf. Create_Landmask.

        for t in range(len(tsteps)):
            for x in range(1, X-1):
                for y in range(1, Y-1):
                    if landmask[x, y] < 1:

                        if landmask[x+1, y] == 1:
                            dVdx[t,y,x] = (data[t,y,x] - data[t,y,x-1]) / dx[y, x]
                        elif landmask[x-1, y] == 1:
                            dVdx[t,y,x] = (data[t,y,x+1] - data[t,y,x]) / dx[y, x]
                        else:
                            dVdx[t,y,x] = (data[t,y,x+1] - data[t,y,x-1]) / (2*dx[y, x])

                        if landmask[x, y+1] == 1:
                            dVdy[t,y,x] = (data[t,y,x] - data[t,y-1,x]) / dy[y, x]
                        elif landmask[x, y-1] == 1:
                            dVdy[t,y,x] = (data[t,y+1,x] - data[t,y,x]) / dy[y, x]
                        else:
                            dVdy[t,y,x] = (data[t,y+1,x] - data[t,y-1,x]) / (2*dy[y, x])

            ## Jules : Modifie les celules en bordures
            for x in range(nlon):
                dVdy[t, 0, x] = (data[t, 1, x] - data[t, 0, x]) / dy[0, x]
                dVdy[t, nlat-1, x] = (data[t, nlat-1, x] - data[t, nlat-2, x]) / dy[nlat-2, x]
            for y in range(nlat):
                dVdx[t, y, 0] = (data[t, y, 1] - data[t, y, 0]) / dx[y, x]
                dVdx[t, y, nlon-1] = (data[t, y, nlon-1] - data[t, y, nlon-2]) / dx[y, x]

    return (
        Field(
            'd' + field.name + '_dx', dVdx, field.grid.lon, field.grid.lat, field.grid.depth,
            field.grid.time[range(start,end)], time_origin=field.grid.time_origin,
            interp_method=field.interp_method, allow_time_extrapolation=field.allow_time_extrapolation),
        Field(
            'd' + field.name + '_dy', dVdy, field.grid.lon, field.grid.lat, field.grid.depth,
            field.grid.time[range(start,end)], time_origin=field.grid.time_origin,
            interp_method=field.interp_method, allow_time_extrapolation=field.allow_time_extrapolation)
    )


def V_max(L, a=2.225841100458143, b=0.8348850216641774):
    V = a * np.power(L, b)
    return V

def V_max_C(monthly_age):
    a=2.225841100458143# 0.7343607395421234 old parameters
    b=0.8348850216641774# 0.5006692114850767 old parameters
    L = GetLengthFromAge(monthly_age)
    V = a * math.pow(L, b)
    return V

def GetLengthFromAge(age, lengths=[3.00, 4.51, 6.02, 11.65, 16.91, 21.83, 26.43, 30.72, 34.73, 38.49, 41.99, 45.27,
                                  48.33, 51.19, 53.86, 56.36, 58.70, 60.88, 62.92, 64.83, 66.61, 68.27, 69.83, 71.28,
                                  72.64, 73.91, 75.10, 76.21, 77.25, 78.22, 79.12, 79.97, 80.76, 81.50, 82.19, 82.83,
                                  83.44, 84.00, 84.53, 85.02, 85.48, 85.91, 86.31, 86.69, 87.04, 87.37, 87.68, 87.96,
                                  88.23, 88.48, 88.71, 88.93, 89.14, 89.33, 89.51, 89.67, 89.83, 89.97, 90.11, 90.24,
                                  90.36, 90.47, 90.57, 90.67, 91.16]):
    age -= 1
    if age >= len(lengths):
        age = len(lengths)-1
    return lengths[age]/100 # Convert to meters

def Mortality(age, MPmax=0.3, MPexp=0.1008314958945224, MSmax=0.006109001382111822, MSslope=0.8158285706493162,
              Mrange=1.430156372206337e-05, H=1):
    Mnat = MPmax*np.exp(-MPexp*age) + MSmax*np.power(age, MSslope)
    Mvar = Mnat * np.power(1 - Mrange, 1-H/2)
    return Mvar

def Mortality_C(age, H):
    MPmax=0.3
    MPexp=0.1008314958945224
    MSmax=0.006109001382111822
    MSslope=0.8158285706493162
    Mrange=1.430156372206337e-05
    Mnat = MPmax*math.exp(-MPexp*age) + MSmax*math.pow(age, MSslope)
    Mvar = Mnat * math.pow(1 - Mrange, 1-H/2)
    return Mvar

def getPopFromDensityField(grid, density_field='Start'):
    area = np.zeros(np.shape(grid.U.data[0, :, :]), dtype=np.float32)
    U = grid.U
    V = grid.V
    dy = (V.lon[1] - V.lon[0])/V.units.to_target(1, V.lon[0], V.lat[0])
    for y in range(len(U.lat)):
        dx = (U.lon[1] - U.lon[0])/U.units.to_target(1, U.lon[0], U.lat[y])
        area[y, :] = dy * dx
    # Convert to km^2
    area /= 1000*1000
    # Total fish is density*area
    total_fish = np.sum(getattr(grid, density_field).data * area)
    return total_fish

def Create_Landmask(fields, lim=1e-45):
    """
    Seapodym landmask defined as where either there is no bathymetric 
    currently velocities (too shallow), or habitat data not defined.
    """

    assert hasattr(fields, 'H'), "H field must be loaded into ocean fieldset to create landmask"
    assert hasattr(fields, 'Ubathy'), "bathy field must be loaded into ocean fieldset to create landmask"

## NOTE : I'm not sure to understand the isOcean signification

    def isOcean(p, lim):
        return p < lim
    def isShallow(p, lim):
        return p < lim

    nx = fields.H.grid.lon.size
    ny = fields.H.grid.lat.size
    # both bathy and H fields must have the same grid map_dimensions
    assert(nx == fields.Ubathy.grid.lon.size), "Lon dimension must be the same for H AND bathy grids"
    assert(ny == fields.Ubathy.grid.lat.size), "Lat dimension must be the same for H AND bathy grids"

## NOTE :
# Is that good ?
# mask == 2 -> is Shallow
# mask == 1 -> is Land or No_Data
# mask == 0 -> deep ocean with habitat data

## NOTE :
# In FeedingHabitat (H), mask is represented by NaN value. There is no
# need to compare to lowest value (lim).
#
# In Ubathy (which should be 'lower meso' if my remember of the conversation
# I had with Patrick is good) it is reprenseted by 0.
#
# Other solution :
# ----------------
# Landmask can also be taken from the FeedingHabitatDataStructure mask.
# It corresponds to :
# - FeedingHabitatDataStructure.fh.data_structure.global_mask['mask_L3']

    mask = np.zeros([nx, ny, 1], dtype=np.int8)
    pbar = ProgressBar()
    for i in pbar(range(nx)):
        for j in range(1, ny-1):
            if isShallow(np.abs(fields.Ubathy.data[0, j, i]), lim) :
                mask[i,j] = 2
            if isOcean(fields.H.data[0, j, i], lim) :
                mask[i,j] = 1

    Mask = Field('LandMask', mask, fields.H.grid.lon, fields.H.grid.lat,
                 transpose=True, allow_time_extrapolation=True)
    Mask.interp_method = 'nearest'
    return Mask

def Create_SEAPODYM_F_Field(Effort, length_classes, name='F', start_age=4, verbose=False,
                            q=0.001032652877899101, selectivity_func=3, mu= 52.56103941719986, sigma=8.614813906820441,
                            r_asymp=0.2456242856428466, time_period=None, timestep=30*24*7*7):
    
    """
    This is a function that compiles separate effort fields into instantaneous fishing
    mortality fields which are combined elsewhere
    """

    #fisheries = fishery_parameters['Fisheries']
    if time_period is not None:
        # Now we must convert the absolute time to time that is relative to the grid
        start_time = Effort.grid.time_origin.reltime(time_period[0])
        end_time = Effort.grid.time_origin.reltime(time_period[1])
        start = np.where(Effort.grid.time <= start_time)[0]

        if len(start) > 0:
            start = start[-1]
        else:
            print("Effort data does not exist for start time of %s! Using earliest timestamp %s" %
                  (datetime.fromtimestamp(time_period[0]), datetime.fromtimestamp(Effort.grid.time[0])))
            start = 0
        if Effort.grid.time[-1] > start_time:
            end = np.where(Effort.grid.time > end_time)[0][0]
        else:
            end = len(Effort.grid.time) + 1
    else:
        start = 0
        end = len(Effort.grid.time)
    Esteps = range(start,end)
    tsteps = np.arange(start_time, end_time, timestep)

    E_scaler = (1.0/30.0)*7.0
    F_scaler = 30.0 / 7.0 / 7.0

    F_Data = np.zeros([len(tsteps),len(Effort.grid.lat), len(Effort.grid.lon)], dtype=np.float32)
    sigma_sq = pow(sigma, 2)
    for t in range(len(tsteps)):
        age = int(start_age + t)
        l = GetLengthFromAge(age, length_classes)*100 #back to cm for selectivity
    # NOTE : Calcul de la sélectivité
        if selectivity_func == 3.0:
            if l > mu:
                Selectivity = (1-r_asymp)*np.exp(-(pow(l-mu,2)/(sigma_sq)))+r_asymp
            else:
                Selectivity = np.exp(-(pow(l-mu,2)/(sigma_sq)))
        elif selectivity_func == 2.0:
            Selectivity = pow(1 + np.exp(-sigma*(l-mu)),-1)
        else:
            print("Selectivity Function not supported! q set to 0")
            Selectivity = 0

        idx = np.argmin(abs((Effort.grid.time[Esteps] - start_time) - (t*timestep)))
    # NOTE : Application de la capture
        F_Data[t,:,:] += F_scaler*E_scaler*Effort.data[idx,:,:] * q * Selectivity
        if verbose:
            date = datetime.fromtimestamp(start_time + t*timestep).strftime('%Y-%m-%d %H:%M:%S')
            print("Date = %s, Age = %s, Length = %scm, Selectivity = %s" % (date, age, l, Selectivity))
            print("max F %s" % np.max(F_Data[t,:,:]))
            print("Effort time index is %s" % idx)
            print(Effort.grid.time[idx])
            print(datetime.fromtimestamp(Effort.grid.time[idx]).strftime('%Y-%m-%d %H:%M:%S'))
    time = np.arange(start_time, end_time, timestep)
    return(Field(name, F_Data, Effort.grid.lon, Effort.grid.lat, time=time,
           time_origin=Effort.grid.time_origin, interp_method='nearest'))

def Create_SEAPODYM_Diffusion_Field(H, length_classes, timestep=30*24*60*60, sigma=0.1769952864978924, c=0.662573993401526, P=3,
                                    start_age=4, Vmax_slope=1, units='m_per_s',
                                    diffusion_boost=0, diffusion_scale=1, sig_scale=1, c_scale=1,
                                    verbose=False, time_period=None):
    #This is simply calculating the required indices of the forcing for this sim
    if time_period is not None:
        # we must convert the absolute time to
        # time that is relative to the grid in parcels
        start_time = H.grid.time_origin.reltime(time_period[0])
        end_time = H.grid.time_origin.reltime(time_period[1])
        start = np.where(H.grid.time <= start_time)[0][-1]
        if H.grid.time[-1] > end_time:
            end = np.where(H.grid.time >= end_time)[0][0]
        else:
            end = len(H.grid.time)
    else:
        start = 0
        end = len(H.grid.time)
    tsteps = range(start,end)
    if verbose :
        print("Creating diffusion field of %s timesteps" % len(tsteps))
    Hdata = H.data[tsteps, :, :] #Get the raw habitat data array from the field object
    K = np.zeros(np.shape(Hdata), dtype=np.float32)
    age_class = start_age
    for t in range(len(tsteps)):
        # Increase age in age_classes if required, to incorporate appropriate Vmax
        age = (start_age*timestep) + H.grid.time[tsteps[t]] - H.grid.time[0] #(start_age+t)*30*24*60*60
        if age - (age_class*timestep) >= (timestep): #
            age_class += 1
        if verbose:
            print('age in days = %s' % (age/(24*60*60)))
            print("Calculating diffusivity for fish aged %s age_classes" % age_class)
        if units == 'nm_per_timestep':
            Dmax = ((np.power(GetLengthFromAge(age_class, length_classes)
                             * (timestep / 1852), 2)
                    / 4 )
                    * timestep / timestep) #vmax = L for diffusion
        else:
            Dmax = (np.power(GetLengthFromAge(age_class, length_classes), 2) / 4) * timestep
        if verbose :
            print("Sigma = %s, Dmax = %s" % (sigma, Dmax))
        sig_D = sigma * Dmax
        #Now loop through every cell of our K array calculate value
        for x in range(H.grid.lon.size):
            for y in range(H.grid.lat.size):
                K[t, y, x] = sig_scale * sig_D * (1 - c_scale * c * np.power(Hdata[t, y, x], P)) * diffusion_scale + diffusion_boost
        if verbose:
            print("")
            print("K range is %s to %s" % (np.min(K[t,:,:]), np.max(K[t,:,:])))
    #Return as a new Parcels field object
    return Field('K', K, H.grid.lon, H.grid.lat, time=H.grid.time[tsteps], time_origin=H.grid.time_origin, interp_method='nearest', allow_time_extrapolation=True)

## TODO : Add the calculation of the Taxis field for cohorts that evolve over time.
# => Take into account different sizes and speeds.
def Create_SEAPODYM_Taxis_Fields(
    dHdx: Field, dHdy: Field, length_classes: List[int],
    start_age=4, taxis_scale=1, units='m_per_s',
    vmax_a=2.225841100458143, vmax_b=0.8348850216641774,
    time_period=None, timestep=30*24*60*60) -> Tuple[Field,Field] :

    """
    Calculation of the Taxi field from the gradient.
    """

    if time_period is not None:
        # Now we must convert the absolute time to time that is relative to the grid
        start_time = dHdx.grid.time_origin.reltime(time_period[0])
        end_time = dHdx.grid.time_origin.reltime(time_period[1])
        start = np.where(dHdx.grid.time <= start_time)[0][-1]
        if dHdx.grid.time[-1] >= end_time:
            end = np.where(dHdx.grid.time > end_time)[0][0]
        else:
            end = len(dHdx.grid.time)
    else:
        start = 0
        end = len(dHdx.grid.time)
    tsteps = range(start,end)
    xData = dHdx.data[tsteps, :, :]
    yData = dHdy.data[tsteps, :, :]
    Tx = np.zeros(xData.shape, dtype=np.float32)
    Ty = np.zeros(yData.shape, dtype=np.float32)
    age_class = start_age
    print("Taxis for %s steps" % len(tsteps))
    for t in range(len(tsteps)):
        age = (start_age+t)*timestep
        if age - (age_class*timestep) >= (timestep):
            age_class += 1
        l = GetLengthFromAge(age_class, length_classes)
        if units == 'nm_per_timestep':
            for x in range(dHdx.grid.lon.size):
                for y in range(dHdx.grid.lat.size):
                    Tx[t, y, x] = (V_max(l, vmax_a, vmax_b)*((timestep)/1852)
                                   * xData[t, y, x] * taxis_scale * (1000*1.852*60
                                   * math.cos(dHdx.lat[y]*math.pi/180)) * 1/timestep)
                    Ty[t, y, x] = (V_max(l, vmax_a, vmax_b)*((timestep)/1852)
                                   * yData[t, y, x] * taxis_scale * (1000*1.852*60)
                                   * 1/timestep)
        else:
            for x in range(dHdx.grid.lon.size):
                for y in range(dHdx.grid.lat.size):
                    Tx[t, y, x] = (V_max(l, vmax_a, vmax_b) * xData[t, y, x] * taxis_scale
                                   * (250*1.852*15 * math.cos(dHdx.lat[y]*math.pi/180)))
                    Ty[t, y, x] = (V_max(l, vmax_a, vmax_b) * yData[t, y, x]
                                   * taxis_scale * (250*1.852*15))

    return (Field('Tx', Tx, dHdx.grid.lon, dHdx.grid.lat, time=dHdx.grid.time[tsteps],
                  time_origin=dHdx.grid.time_origin, interp_method=dHdx.interp_method,
                  allow_time_extrapolation=dHdx.allow_time_extrapolation),
            Field('Ty', Ty, dHdx.grid.lon, dHdx.grid.lat, time=dHdx.grid.time[tsteps],
                  time_origin=dHdx.grid.time_origin, interp_method=dHdx.interp_method,
                  allow_time_extrapolation=dHdx.allow_time_extrapolation))

def readSEAPODYM_parfile(file):
    variables = ['sigma_species', 'c_diff_fish', 'MSS_species', 'MSS_size_slope',  # movement params
                 'Mp_mean_max', 'Mp_mean_exp', 'Ms_mean_max', 'Ms_mean_slope', 'M_mean_range']  # mortality params
    if file is not None:
        parfile = minidom.parse(file)
        SEAPODYM_Params = {}
        for var in variables:
            v = parfile.getElementsByTagName(var)
            SEAPODYM_Params[var] = float(v[0].attributes['skj'].value)
        # Fishery parameters
        F_names = parfile.getElementsByTagName('list_fishery_name')
        print(str(parfile.getElementsByTagName('mask_fishery_sp')[0].getElementsByTagName('skj')[0].firstChild.nodeValue))
        F_toUse = [int(n) for n in str(parfile.getElementsByTagName('mask_fishery_sp')[0].getElementsByTagName('skj')[0].firstChild.nodeValue).split()]
        print(F_toUse)
        print([int(F) for F in np.where([F != 1 for F in F_toUse])[0]])
        SEAPODYM_Params['Fisheries'] = str(F_names[0].firstChild.nodeValue).split()
        for F in [int(F) for F in np.where([F != 1 for F in F_toUse])[0]]:
            SEAPODYM_Params['Fisheries'].pop(F)
        #SEAPODYM_Params['Fisheries'].pop([int(F) for F in np.where([F is not 1 for F in F_toUse])[0]])
        SEAPODYM_Params['Q'] = {}
        Q = parfile.getElementsByTagName('q_sp_fishery')
        for f in SEAPODYM_Params['Fisheries']:
            SEAPODYM_Params[f] = {}
            SEAPODYM_Params[f]['q'] = float(Q[0].getElementsByTagName(f)[0].attributes['skj'].value)
        S = parfile.getElementsByTagName('s_sp_fishery')
        for f in SEAPODYM_Params['Fisheries']:
            SEAPODYM_Params[f].update({'sigma': float(S[0].getElementsByTagName(f)[0].attributes['skj'].value)})
            SEAPODYM_Params[f]['function_type'] = float(S[0].getElementsByTagName(f)[0].getElementsByTagName('function_type')[0].attributes['value'].value)
            SEAPODYM_Params[f]['mu'] = float(S[0].getElementsByTagName(f)[0].getElementsByTagName('length_threshold')[0].attributes['skj'].value)
            SEAPODYM_Params[f]['right_asymptote'] = float(S[0].getElementsByTagName(f)[0].getElementsByTagName('right_asymptote')[0].attributes['skj'].value)
        SEAPODYM_Params['Length_Classes'] = [float(l) for l in parfile.getElementsByTagName('length')[0].getElementsByTagName('skj')[0].childNodes[0].data.split()]
        SEAPODYM_Params['SEAPODYM_dt'] = int(parfile.getElementsByTagName('deltaT')[0].attributes['value'].value) *24*60*60
    else:  # Some defaults
        SEAPODYM_Params = {'sigma_species': 0.1769952864978924, 'c_diff_fish': 0.662573993401526,
                           'MSS_species': 2.225841100458143, 'MSS_size_slope': 0.8348850216641774}
    print(SEAPODYM_Params)
    return SEAPODYM_Params

## NOTE : I had to comment this function because py.path import is missing.
# Can be uncommented if needed.

# def Create_SEAPODYM_Grid(forcing_files, startD=None, startD_dims=None,
#                          forcing_vars={'U': 'u', 'V': 'v', 'H': 'habitat'},
#                          forcing_dims={'lon': 'lon', 'lat': 'lon', 'time': 'time'}, K_timestep=30*24*60*60,
#                          diffusion_file=None, field_units='m_per_s',
#                          diffusion_dims={'lon': 'longitude', 'lat': 'latitude', 'time': 'time', 'data': 'skipjack_diffusion_rate'},
#                          scaleH=None, start_age=4, output_density=False, diffusion_scale=1, sig_scale=1, c_scale=1,
#                          parameter_file=None, verbose=False):

#     """
#     A wrapper function designed to generate all the required parcels fields
#     objects for a suite of seapodym forcings and parameters
#     """

#     if startD_dims is None:
#         startD_dims = forcing_dims
#     if verbose:
#         print("Creating Grid\nLoading files:")
#         for f in forcing_files.values():
#             print(f)

#     grid = FieldSet.from_netcdf(filenames=forcing_files, variables=forcing_vars, dimensions=forcing_dims,
#                             vmin=-200, vmax=1e34, interp_method='nearest', allow_time_extrapolation=True)
#     print(forcing_files['U'])
#     Depthdata = Field.from_netcdf('u', dimensions={'lon': 'longitude', 'lat': 'latitude', 'time': 'time', 'depth': 'depth'},
#                                      filenames=forcing_files['U'], allow_time_extrapolation=True)
#     Depthdata.name = 'bathy'
#     grid.add_field(Depthdata)


#     if startD is not None:
#         grid.add_field(Field.from_netcdf('Start', dimensions=startD_dims,
#                                          filenames=path.local(startD), vmax=1000,
#                                          interp_method='nearest', allow_time_extrapolation=True))

#     if output_density:
#         # Add a density field that will hold particle densities
#         grid.add_field(Field('Density', np.full([grid.U.lon.size, grid.U.lat.size, grid.U.time.size],-1, dtype=np.float64),
#                        grid.U.lon, grid.U.lat, depth=grid.U.depth, time=grid.U.time, transpose=True))

#     LandMask = Create_Landmask(grid)
#     grid.add_field(LandMask)
#     grid.U.data[grid.U.data > 1e5] = 0
#     grid.V.data[grid.V.data > 1e5] = 0
#     grid.H.data[grid.H.data > 1e5] = 0
#     # Scale the H field between zero and one if required
#     if scaleH is not None:
#         grid.H.data /= np.max(grid.H.data)
#         grid.H.data[np.where(grid.H.data < 0)] = 0
#         grid.H.data *= scaleH

#     # SEAPODYM Specific fields

#     # Offline calculate the 'diffusion' grid as a function of habitat
#     if verbose:
#         print("Creating Diffusion Field")
#     if diffusion_file is None:
#         K = Create_SEAPODYM_Diffusion_Field(grid.H, timestep=K_timestep, start_age=start_age,
#                                             diffusion_scale=diffusion_scale, units=field_units,
#                                             sig_scale=sig_scale, c_scale=c_scale, verbose=verbose)
#     else:
#         if verbose:
#             print("Loading from file: %s" % diffusion_file)
#         K = Field.from_netcdf('K', diffusion_dims, [diffusion_file], interp_method='nearest', vmax=1000000)
#         if diffusion_units == 'nm2_per_mon':
#             K.data *= 1.30427305

#     grid.add_field(K)

#     if verbose:
#         print("Calculating H Gradient Fields")
#     dHdx, dHdy = getGradient(grid.H, grid.LandMask)
#     grid.add_field(dHdx)
#     grid.add_field(dHdy)
#     #gradients = grid.H.gradient()
#     #for field in gradients:
#     #    grid.add_field(field)

#     if verbose:
#         print("Calculating Taxis Fields")
#     T_Fields = Create_SEAPODYM_Taxis_Fields(grid.dH_dx, grid.dH_dy, start_age=start_age, units=field_units)
#     for field in T_Fields:
#         grid.add_field(field)

#     if verbose:
#         print("Creating combined Taxis and Advection field")
#     grid.add_field(Field('TU', grid.U.data+grid.Tx.data, grid.U.lon, grid.U.lat, time=grid.U.time, vmin=-200, vmax=1e34,
#                          interp_method='nearest', allow_time_extrapolation=True))# units=unit_converters('spherical')[0]))
#     grid.add_field(Field('TV', grid.V.data+grid.Ty.data, grid.U.lon, grid.U.lat, time=grid.U.time, vmin=-200, vmax=1e34,
#                          interp_method='nearest', allow_time_extrapolation=True))#, units=unit_converters('spherical')[1]))


#     if verbose:
#         print("Calculating K Gradient Fields")
#     #K_gradients = grid.K.gradient()
#     #for field in K_gradients:
#     #    grid.add_field(field)
#     dKdx, dKdy = getGradient(grid.K, grid.LandMask, False)
#     grid.add_field(dKdx)
#     grid.add_field(dKdy)
#     grid.K.interp_method = grid.dK_dx.interp_method = grid.dK_dy.interp_method = grid.H.interp_method = \
#                            grid.dH_dx.interp_method = grid.dH_dy.interp_method = grid.U.interp_method = grid.V.interp_method = 'nearest'

#     #grid.K.allow_time_extrapolation = grid.dK_dx.allow_time_extrapolation = grid.dK_dy.allow_time_extrapolation = \
#     #                                  grid.H.allow_time_extrapolation = grid.dH_dx.allow_time_extrapolation = \
#     #                                  grid.dH_dy.allow_time_extrapolation = grid.U.allow_time_extrapolation = \
#     #                                  grid.V.allow_time_extrapolation = True

#     return grid

def Field_from_DYM(filename, name=None, xlim=None, ylim=None, fromyear=None, frommonth=0, toyear=None, tomonth=0):

    if name is None:
        name = str.split(filename, '/')[-1]
    print("Name = %s" % name)

    def lat_to_j(lat, latmax, deltaY):
        j = (int) ((latmax - lat)/deltaY + 1.5)
        return j-1

    def lon_to_i(lon, lonmin, deltaX):
        if lon < 0:
            lon = lon+360
        i = (int) ((lon - lonmin)/deltaX + 1.5)
        return i-1

    def get_tcount_start(zlevel, nlevel, date):
        n = 0
        while date > zlevel[n] and n < (nlevel-1):
            n += 1
        return n

    def get_tcount_end(zlevel, nlevel, date):
        n = nlevel-1
        while date < zlevel[n] and n > 0:
            n -= 1
        return n

    class DymReader:
        # Map well-known type names into struct format characters.
        typeNames = {
        'int32'  :'i',
        'uint32' :'I',
        'int64'  :'q',
        'uint64' :'Q',
        'float'  :'f',
        'double' :'d',
        'char'   :'s'}

        x1 = x2 = 0

        def __init__(self, fileName):
            self.file = open(fileName, 'rb')

        def read(self, typeName):
            typeFormat = DymReader.typeNames[typeName.lower()]
            scale = 1
            if(typeFormat == 's'):
                scale = self.DymInputSize
            typeSize = struct.calcsize(typeFormat) * scale
            value = self.file.read(typeSize)
            decoded = struct.unpack(typeFormat*scale, value)
            #print(decoded)
            decoded = [x for x in decoded]

            if(typeFormat == 's'):
                decoded = ''.join(decoded)
                return decoded
            return decoded[0]

        def move(self, pos):
            self.file.seek(pos, 1)

        def close(self):
            self.file.close()

    if xlim is not None:
        x1 = xlim[0]
        x2 = xlim[1]
    else:
        x1 = x2 = 0

    if ylim is not None:
        y1 = ylim[0]
        y2 = ylim[1]
    else:
        y1 = y2 = 0

    file = DymReader(filename)

    # Get header
    print("-- Reading .dym file --")
    idformat = file.read('char')
    print("ID Format = %s" % idformat)
    idfunc = file.read('int32')
    print("IF Function = %s" % idfunc)
    minval = file.read('float')
    print("minval = %s" % minval)
    maxval = file.read('float')
    print("maxval = %s" % maxval)
    nlon = file.read('int32')
    print("nlon = %s" % nlon)
    nlat = file.read('int32')
    print("nlat = %s" % nlat)
    nlevel = file.read('int32')
    print("nlevel = %s" % nlevel)
    startdate = file.read('float')
    print("startdate = %s" % startdate)
    enddate = file.read('float')
    print("enddate = %s" % enddate)

    if fromyear is None:
        fromyear = np.floor(startdate)
    if toyear is None:
        toyear = np.floor(enddate)

    x = np.zeros([nlat, nlon], dtype=np.float32)
    y = np.zeros([nlat, nlon], dtype=np.float32)

    for i in range(nlat):
        for j in range(nlon):
            x[i, j] = file.read('float')

    for i in range(nlat):
        for j in range(nlon):
            y[i, j] = file.read('float')

    dx = x[0, 1] - x[0, 0]
    dy = y[0, 0] - y[1, 0]

    i1 = lon_to_i(x1, x[0, 0], dx)
    i2 = lon_to_i(x2, x[0, 0], dx)
    j1 = lat_to_j(y2, y[0, 0], dy)
    j2 = lat_to_j(y1, y[0, 0], dy)
    if xlim is None:
        i1 = 0
        i2 = nlon
    if ylim is None:
        j1 = 0
        j2 = nlat
    nlon_new = i2 - i1
    nlat_new = j2 - j1

    if xlim is None:
        nlon_new = nlon
        nlat_new = nlat
        i1 = 0
        i2 = nlon
        j1 = 0
        j2 = nlat

    for j in range(nlat_new):
        for i in range(nlon_new):
            x[j, i] = x[j+j1, i+i1]
            y[j, i] = y[j+j1, i+i1]

    mask = np.zeros([nlat_new, nlon_new], dtype=np.float32)

    zlevel = np.zeros(nlevel, dtype=np.float32)
    for n in range(nlevel):
        zlevel[n] = file.read('float')
    nlevel_new = nlevel
    ts1 = 0
    firstdate = fromyear + (frommonth-1)/12  #start at the beginning of a given month
    lastdate = toyear + tomonth/12  ## stop at the end of a given month
    ts1 = get_tcount_start(zlevel, nlevel, firstdate)
    ts2 = get_tcount_end(zlevel, nlevel, lastdate)
    nlevel_new = ts2-ts1+1

    zlevel_new = np.zeros(nlevel_new, dtype=np.float32)
    for n in range(nlevel_new):
        zlevel_new[n] = zlevel[n+ts1]

    for j in range(nlat):
        for i in range(nlon):
            temp = file.read('int32')
            if i2 > i >= i1 and j2 > j >= j1:
                mask[j-j1, i-i1] = temp

    data = np.zeros([nlevel_new, nlat_new, nlon_new], dtype=np.float32)
    t_count = ts1
    if t_count < 0:
        t_count = 0

    print("Start reading data time series skipping %s and reading for %s time steps" % (t_count, nlevel_new))

    nbytetoskip = nlon*nlat*t_count * 4
    file.move(nbytetoskip)

    val = 0
    for n in range(nlevel_new):
        for j in range(nlat)[::-1]:
            for i in range(nlon):
                val = file.read('float')
                if i2 > i >= i1 and j2 > j >= j1:
                    data[n, j-j1, i-i1] = val*1852/(30*24*60*60)  #Convert from nm/m to m/s

    file.close()


    # Create datetime objects for t index
    times = [0] * nlevel_new
    dt = np.round((enddate-startdate)/nlevel*365)
    for t in range(nlevel_new):
        times[t] = datetime(int(fromyear + np.floor(t/12)), (t%12)+1, 15, 0, 0, 0)
    origin = datetime(1970, 1, 1, 0, 0, 0)
    times_in_s = times
    for t in range(len(times)):
        times_in_s[t] = (times[t] - origin).total_seconds()
    times_in_s = np.array(times_in_s, dtype=np.float32)

    return Field(name, data, lon=x[0,:], lat=y[:,0][::-1], time=times_in_s, time_origin=origin)

def Create_TaggedFish_Class(type=JITParticle):
    """Another Ikamoana class definition"""

    class TaggedFish(type):
        monthly_age = Variable("monthly_age", dtype=np.int32)
        age = Variable('age', to_write=False)
        Vmax = Variable('Vmax', to_write=False)
        Dv_max = Variable('Dv_max', to_write=False)
        H = Variable('H', to_write=False)
        Dx = Variable('Dx', to_write=False)
        Dy = Variable('Dy', to_write=False)
        Cx = Variable('Cx', to_write=False)
        Cy = Variable('Cy', to_write=False)
        Vx = Variable('Vx', to_write=False)
        Vy = Variable('Vy', to_write=False)
        Ax = Variable('Ax', to_write=False)
        Ay = Variable('Ay', to_write=False)
        taxis_scale = Variable('taxis_scale', to_write=False)
        release_time = Variable('release_time', dtype=np.float32, initial=0, to_write=False)

        def __init__(self, *args, **kwargs):
            """Custom initialisation function which calls the base
            initialisation and adds the instance variable p"""
            super(TaggedFish, self).__init__(*args, **kwargs)
            self.setAge(4.)
            self.H = self.Dx = self.Dy = self.Cx = self.Cy = self.Vx = self.Vy = self.Ax = self.Ay = 0
            self.taxis_scale = 0
            self.active = 0
            self.release_time = 0

        def setAge(self, months):
            self.age = months*30*24*60*60
            self.monthly_age = int(self.age/(30*24*60*60))
            self.Vmax = V_max(self.monthly_age)

    return TaggedFish

def getSEAPODYMarguments(run="SEAPODYM_2003"):
    """A function that was just defined to create some minimum information
    without an Ikamoana or Seapodym parameter file"""
    args = {}
    if run == "SEAPODYM_2003":
        args.update({'ForcingFiles': {'U': 'SEAPODYM_Forcing_Data/Latest/PHYSICAL/2003Run/2003run_PHYS_month*.nc',
                                      'V': 'SEAPODYM_Forcing_Data/Latest/PHYSICAL/2003Run/2003run_PHYS_month*.nc',
                                      'H': 'SEAPODYM_Forcing_Data/Latest/HABITAT/2003Run/INTERIM-NEMO-PISCES_skipjack_habitat_index_*.nc',
                                      'start': 'SEAPODYM_Forcing_Data/Latest/DENSITY/INTERIM-NEMO-PISCES_skipjack_cohort_20021015_density_M0_20030115.nc',
                                      'E': 'SEAPODYM_Forcing_Data/Latest/FISHERIES/P3_E_Data.nc'}})
        args.update({'ForcingVariables': {'U': 'u',
                                          'V': 'v',
                                          'H': 'skipjack_habitat_index',
                                          'start': 'skipjack_cohort_20021015_density_M0',
                                          'E': 'P3'}})
        args.update({'LandMaskFile': 'SEAPODYM_Forcing_Data/Latest/PHYSICAL/2003Run/2003run_PHYS_month01.nc'})
        args.update({'Filestems': {'U': 'm',
                                   'V': 'm',
                                   'H': 'd'}})
        args.update({'Kernels': ['Advection_C',
                                 'LagrangianDiffusion',
                                 'TaxisRK4',
                                 'FishingMortality',
                                 'NaturalMortality',
                                 'MoveWithLandCheck',
                                 'AgeAnimal']})

    if run == "DiffusionTest":
        print("in")
        args.update({'ForcingFiles': {'U': 'DiffusionExample/DiffusionExampleCurrents.nc',
                                      'V': 'DiffusionExample/DiffusionExampleCurrents.nc',
                                      'H': 'DiffusionExample/DiffusionExampleHabitat.nc'}})
        args.update({'ForcingVariables': {'U': 'u',
                                          'V': 'v',
                                          'H': 'skipjack_habitat_index'}})
        args.update({'Filestems': {'U': 'm',
                                   'V': 'm',
                                   'H': 'd'}})
        args.update({'Kernels': ['LagrangianDiffusion',
                                 'Move',
                                 'MoveOffLand']})
    return args
