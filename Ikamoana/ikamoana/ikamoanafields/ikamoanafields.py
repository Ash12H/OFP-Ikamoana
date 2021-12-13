from datetime import time
from typing import Tuple, Union, List

import numpy as np
import parcels
import xarray as xr
from parcels.tools.converters import Geographic, GeographicPolar

from ..feedinghabitat import FeedingHabitat
from .ikamoanafieldsconfigreader import readIkamoanaFieldsXML


def convertToField(field : Union[xr.DataArray, xr.Dataset], name=None) :

    if isinstance(field, xr.DataArray) :
        field = field.to_dataset(name=name if name is not None else field.name)

    return parcels.FieldSet.from_xarray_dataset(
        ((field.reindex(lat=field.lat[::-1]))
         if field.lat[0] > field.lat[-1] else field),
        variables=dict([(i,i) for i in field.keys()]),
        dimensions=dict([(i,i) for i in field.dims.keys()]))

def sliceField(field : Union[xr.DataArray, xr.Dataset],
               time_start: int = None, time_end: int = None,
               lat_min: int = None, lat_max: int = None,
               lon_min: int = None, lon_max: int = None) -> Union[xr.DataArray, xr.Dataset] :

    coords = field.coords

    if (lat_min is not None) :
        if ((lat_min < 0) or (lat_min >= coords['lat'].data.size)) :
            raise ValueError("lat_min out of bounds. Min is %d and Max is %d"%(
                0, coords['lat'].data.size - 1))
    if (lat_max is not None) :
        if ((lat_max < 0) or (lat_max >= coords['lat'].data.size)) :
            raise ValueError("lat_max out of bounds. Min is %d and Max is %d"%(
                0, coords['lat'].data.size - 1))
    if (lat_min is not None) and (lat_max is not None) and (lat_min > lat_max) :
        raise ValueError("lat_min must be <= to lat_max.")

    if (lon_min is not None) :
        if ((lon_min < 0) or (lon_min >= coords['lon'].data.size)) :
            raise ValueError("lon_min out of bounds. Min is %d and Max is %d"%(
                0, coords['lon'].data.size - 1))
    if (lon_max is not None) :
        if ((lon_max < 0) or (lon_max >= coords['lon'].data.size)) :
            raise ValueError("lon_max out of bounds. Min is %d and Max is %d"%(
                0, coords['lon'].data.size - 1))
    if (lon_min is not None) and (lon_max is not None) and (lon_min > lon_max) :
        raise ValueError("lon_min must be <= to lon_max.")

    if (time_start is not None) :
        if ((time_start < 0) or (time_start >= coords['time'].data.size)) :
            raise ValueError("time_start out of bounds. Min is %d and Max is %d"%(
                0, coords['time'].data.size - 1))
    if (time_end is not None) :
        if ((time_end < 0) or (time_end >= coords['time'].data.size)) :
            raise ValueError("time_end out of bounds. Min is %d and Max is %d"%(
                0, coords['time'].data.size - 1))
    if (time_start is not None) and (time_end is not None) and (time_start > time_end) :
        raise ValueError("time_start must be <= to time_end.")

    coord_lat = coords["lat"][lat_min:lat_max+1 if lat_max is not None else None]
    coord_lon = coords["lon"][lon_min:lon_max+1 if lon_max is not None else None]
    coord_time = coords["time"][time_start:time_end+1 if time_end is not None else None]

    return field.sel(time=coord_time, lat=coord_lat, lon=coord_lon)

class IkamoanaFields :

# ------------------------- CORE FUNCTIONS ------------------------- #

    def __init__(self,
                 #xml_fields : str,
                 xml_feeding_habitat : str,
                 feeding_habitat : xr.DataArray = None):
        """Create a IkamoanaFields class. Can compute Taxis, Current and Diffusion
        fields."""

        #self.ikamoana_fields_structure = readIkamoanaFieldsXML(xml_fields)
        self.ikamoana_fields_structure = readIkamoanaFieldsXML(None)
        self.feeding_habitat_structure = FeedingHabitat(xml_feeding_habitat)
        if (feeding_habitat is None) or isinstance(feeding_habitat,xr.DataArray) :
            self.feeding_habitat = feeding_habitat
        else :
            raise TypeError("feeding_habitat must be a Xarray.DataArray or None. Actual type is : %s"%(str(type(feeding_habitat))))

    def vMax(self, length : float) -> float :
        """Return the maximum velocity of a fish with a given length."""

        return (self.ikamoana_fields_structure.vmax_a
             * np.power(length, self.ikamoana_fields_structure.vmax_b))

    def landmask(self, habitat_field : xr.DataArray = None,
                 shallow_sea_to_ocean=False, lim=1e-45) -> xr.DataArray :
        """Return the landmask of a given habitat or FeedingHabitat.global_mask.
        Mask values :
            2 -> is Shallow
            1 -> is Land or No_Data
            0 -> deep ocean with habitat data

        Note:
        -----
            Landmask in Original (with Parcels Fields) is flipped on latitude axis.
        """

        if habitat_field is None :
            mask_L1 = np.invert(
                self.feeding_habitat_structure.data_structure.global_mask['mask_L1'])[0,:,:]
            mask_L3 = np.invert(
                self.feeding_habitat_structure.data_structure.global_mask['mask_L3'])[0,:,:]

            landmask = np.zeros(mask_L1.shape, dtype=np.int8)
            if not shallow_sea_to_ocean : landmask[mask_L3] = 2
            landmask[mask_L1] = 1

            coords = self.feeding_habitat_structure.data_structure.coords

        else :
            habitat_f = habitat_field[0,:,:]
            ## TODO : Should I use temperature_L3 rather than forage_lmeso ?
            lmeso_f = self.feeding_habitat_structure.data_structure.variables_dictionary['forage_lmeso'][0,:,:]
            if habitat_f.shape != lmeso_f.shape :
                raise ValueError("Habitat and forage_lmeso must have the same dimension.")

            landmask = np.zeros_like(habitat_f)
            if not shallow_sea_to_ocean :
                landmask[(np.abs(lmeso_f) <= lim) | np.isnan(lmeso_f)] = 2
            landmask[(np.abs(habitat_f) <= lim) | np.isnan(habitat_f)] = 1

            coords = habitat_field.coords

        ## TODO : Ask why lon is between 1 and ny-1
        # Answer -> in-coming
        landmask[-1,:] = landmask[0,:] = 0

        return xr.DataArray(
                data=landmask,
                name='landmask',
                coords={'lat':coords['lat'],
                        'lon':coords['lon']},
                dims=('lat', 'lon')
            )

    def gradient(self, field: xr.DataArray, landmask: xr.DataArray,
                 name: str = None) -> Tuple[xr.DataArray]:

        """
        Gradient calculation for a Xarray DataArray seapodym-equivalent calculation
        requires LandMask forward and backward differencing for domain edges
        and land/shallow sea cells.
        """

        if ((field.lat.size != landmask.lat.size)
                or (field.lon.size != landmask.lon.size)) :
            raise ValueError("Field and landmask must have the same dimension.")

        ## WARNING : To have the same behavior as original gradient function,
        # latitude must be south-north rather than north-south.

        flip_lat = field.lat[0] > field.lat[-1]
        if flip_lat :
            field = field.reindex(lat=field.lat[::-1])
        if landmask.lat[0] > landmask.lat[-1] :
            landmask = landmask.reindex(lat=landmask.lat[::-1])

        def getCellEdgeSizes(field) :
            """Copy of the Field.calc_cell_edge_sizes() function in Parcels.
            Avoid the convertion of DataArray into Field."""

            field_grid = parcels.grid.RectilinearZGrid(
                field.lon.data, field.lat.data,
                depth=None, time=None, time_origin=None,
                mesh='spherical') # In degrees

            field_grid.cell_edge_sizes['x'] = np.zeros((field_grid.ydim, field_grid.xdim), dtype=np.float32)
            field_grid.cell_edge_sizes['y'] = np.zeros((field_grid.ydim, field_grid.xdim), dtype=np.float32)

            x_conv = GeographicPolar()
            y_conv = Geographic()

            for y, (lat, dlat) in enumerate(zip(field_grid.lat, np.gradient(field_grid.lat))):
                for x, (lon, dlon) in enumerate(zip(field_grid.lon, np.gradient(field_grid.lon))):
                    field_grid.cell_edge_sizes['x'][y, x] = x_conv.to_source(dlon, lon, lat, field_grid.depth[0])
                    field_grid.cell_edge_sizes['y'][y, x] = y_conv.to_source(dlat, lon, lat, field_grid.depth[0])

            return field_grid.cell_edge_sizes['x'], field_grid.cell_edge_sizes['y']

        dlon, dlat = getCellEdgeSizes(field)

        nlat = field.lat.size
        nlon = field.lon.size

        data = np.nan_to_num(field.data)
        landmask = landmask.data
        dVdlon = np.zeros(data.shape, dtype=np.float32)
        dVdlat = np.zeros(data.shape, dtype=np.float32)

        ## NOTE : Parallelised execution may help to do it faster.
        # I think it can also be vectorized.
        for t in range(field.time.size):
            for lon in range(1, nlon-1):
                for lat in range(1, nlat-1):
                    if landmask[lat, lon] < 1:
                        if landmask[lat, lon+1] == 1:
                            dVdlon[t,lat,lon] = (data[t,lat,lon] - data[t,lat,lon-1]) / dlon[lat, lon]
                        elif landmask[lat, lon-1] == 1:
                            dVdlon[t,lat,lon] = (data[t,lat,lon+1] - data[t,lat,lon]) / dlon[lat, lon]
                        else:
                            dVdlon[t,lat,lon] = (data[t,lat,lon+1] - data[t,lat,lon-1]) / (2*dlon[lat, lon])

                        if landmask[lat+1, lon] == 1:
                            dVdlat[t,lat,lon] = (data[t,lat,lon] - data[t,lat-1,lon]) / dlat[lat, lon]
                        elif landmask[lat-1, lon] == 1:
                            dVdlat[t,lat,lon] = (data[t,lat+1,lon] - data[t,lat,lon]) / dlat[lat, lon]
                        else:
                            dVdlat[t,lat,lon] = (data[t,lat+1,lon] - data[t,lat-1,lon]) / (2*dlat[lat, lon])

            for lon in range(nlon):
                dVdlat[t,0,lon] = (data[t,1,lon] - data[t,0,lon]) / dlat[0,lon]
                dVdlat[t,-1,lon] = (data[t,-1,lon] - data[t,-2,lon]) / dlat[-2,lon]
            for lat in range(nlat):
                dVdlon[t,lat,0] = (data[t,lat,1] - data[t,lat,0]) / dlon[lat,-1]
                dVdlon[t,lat,-1] = (data[t,lat,-1] - data[t,lat,-2]) / dlon[lat,-1]

        if flip_lat : field = field = field.reindex(lat=field.lat[::-1])

        return (xr.DataArray(
                    name = "Gradient_longitude_"+(field.name if name is None else name),
                    data = dVdlon,
                    coords = field.coords,
                    dims=('time','lat','lon'),
                    attrs=field.attrs),
                xr.DataArray(
                    name = "Gradient_latitude_"+(field.name if name is None else name),
                    data = np.flip(dVdlat, axis=1) if flip_lat else dVdlat,
                    coords = field.coords,
                    dims=('time','lat','lon'),
                    attrs=field.attrs))

    def taxis(self, dHdlon: xr.DataArray, dHdlat: xr.DataArray,
              name: str = None) -> Tuple[xr.DataArray,xr.DataArray] :
        """
        Calculation of the Taxis field from the gradient.
        """

        def argumentCheck(array) :
            if array.attrs.get('cohort_start') is not None :
                is_evolving = True
                age = array.cohorts
            elif array.attrs.get('Cohort number') is not None :
                is_evolving = False
                age = array.attrs.get('Cohort number')
            else :
                raise ValueError("Fields must contain either 'cohort_start' or 'Cohort number'")
            return is_evolving, age

        is_evolving, age = argumentCheck(dHdlon)
        Tlon = np.zeros(dHdlon.data.shape, dtype=np.float32)
        Tlat = np.zeros(dHdlat.data.shape, dtype=np.float32)
        lat_tile_transpose_cos = np.cos(
            np.tile(dHdlon.lat.data, (dHdlon.lon.size, 1)).T
            * np.pi/180)
        factor = self.ikamoana_fields_structure.taxis_scale * 250 * 1.852 * 15
        f_length = self.feeding_habitat_structure.data_structure.findLengthByCohort

        for t in range(dHdlon.time.size):
            t_age = age[t] if is_evolving else age
            # Convert cm to meter (/100) : See original function
            t_length = f_length(t_age) / 100

            Tlon[t,:,:] = (self.vMax(t_length)
                           * dHdlon.data[t,:,:]
                           * factor * lat_tile_transpose_cos)
            Tlat[t,:,:] = (self.vMax(t_length)
                           * dHdlat.data[t,:,:]
                           * factor)

        if self.ikamoana_fields_structure.units == 'nm_per_timestep':
            Tlon *= (16/1852)
            Tlat *= (16/1852)
        ## NOTE :       (timestep/1852) * (1000*1.852*60) * 1/timestep
        #           <=> (250*1.852*15) * (16/1852)

        return (xr.DataArray(name = "Taxis_longitude_"+(dHdlon.name if name is None else name),
                             data = Tlon,
                             coords = dHdlon.coords,
                             dims=('time','lat','lon'),
                             attrs=dHdlon.attrs),
                xr.DataArray(name = "Taxis_longitude_"+(dHdlat.name if name is None else name),
                             data = Tlat,
                             coords = dHdlat.coords,
                             dims=('time','lat','lon'),
                             attrs=dHdlat.attrs))

    def diffusion(self, habitat: xr.DataArray, name: str = None) -> xr.DataArray :
        """DESCRIPTION : This is simply calculating the required indices of the
        forcing for this simulation."""

        def argumentCheck(array) :
            if array.attrs.get('cohort_start') is not None :
                is_evolving = True
                age = array.cohorts
            elif array.attrs.get('Cohort number') is not None :
                is_evolving = False
                age = array.attrs.get('Cohort number')
            else :
                raise ValueError("Fields must contain either 'cohort_start' or 'Cohort number'")
            return is_evolving, age

        is_evolving, age = argumentCheck(habitat)
        timestep = self.ikamoana_fields_structure.timestep

        end = habitat.time.size
        ## TODO : How do we manage NaN values ?
        # Hdata = habitat.data
        Hdata = np.nan_to_num(habitat.data)
        K = np.zeros_like(Hdata)
        f_length = self.feeding_habitat_structure.data_structure.findLengthByCohort

        for t in range(end):

            t_age = age[t] if is_evolving else age
            t_length = f_length(t_age) / 100 # Convert into meter

            if self.ikamoana_fields_structure.units == 'nm_per_timestep':
                Dmax = (t_length*(timestep/1852))**2 / 4
            else:
                Dmax = (t_length**2 / 4) * timestep
            sig_D = self.ikamoana_fields_structure.sigma * Dmax

            ## VECTORIZED
            K[t,:,:] = (
                self.ikamoana_fields_structure.sig_scale
                * sig_D
                * (1 - self.ikamoana_fields_structure.c_scale
                    * self.ikamoana_fields_structure.c
                    * np.power(Hdata[t,:,:], self.ikamoana_fields_structure.P))
                * self.ikamoana_fields_structure.diffusion_scale
                + self.ikamoana_fields_structure.diffusion_boost
            )


        return xr.DataArray(data=K,
                            name="K_" + (habitat.name if name is None else name),
                            coords=habitat.coords,
                            dims=("time","lat","lon"),
                            attrs=habitat.attrs)

# ------------------------- WRAPPER ------------------------- #

## TODO : Prise en compte des limites dans la structure de données ?
# Manuel ou automatique ?
    def computeTaxis(
            self,
            cohort: int = None,
            time_start: int = None, time_end: int = None,
            lat_min: int = None, lat_max: int = None,
            lon_min: int = None, lon_max: int = None,
            name: str = None, use_already_computed_habitat: bool = True,
            verbose: bool = False) -> Tuple[xr.DataArray,xr.DataArray] :
        """Description
        See Also:
        ---------
            FeedingHabitat.computeFeedingHabitat
        """

        if (self.feeding_habitat is None) or (not use_already_computed_habitat) :
            if cohort is None :
                raise ValueError("cohort argument must be specified. Actual is %s."%(str(cohort)))
            feeding_habitat = self.feeding_habitat_structure.computeFeedingHabitat(
                cohort,time_start,time_end,lat_min,lat_max,lon_min,lon_max,verbose)
            fh_name = list(feeding_habitat.var()).pop()
            feeding_habitat = feeding_habitat[fh_name]
        else :
            feeding_habitat = self.feeding_habitat

        landmask = self.landmask(
            habitat_field=(feeding_habitat
                if self.ikamoana_fields_structure.landmask_from_habitat else None),
            shallow_sea_to_ocean=self.ikamoana_fields_structure.shallow_sea_to_ocean)

        grad_lon, grad_lat = self.gradient(feeding_habitat, landmask)

        return self.taxis(grad_lon, grad_lat, name=feeding_habitat.name if name is None else name)

    def computeEvolvingTaxis(
            self,
            cohort_start: int = None, cohort_end: int = None,
            time_start: int = None, time_end: int = None,
            lat_min: int = None, lat_max: int = None,
            lon_min: int = None, lon_max: int = None,
            name: str = None, use_already_computed_habitat: bool = True,
            verbose: bool = False) -> Tuple[xr.DataArray,xr.DataArray] :
        """Description
        See Also:
        ---------
            FeedingHabitat.computeEvolvingFeedingHabitat
        """
        # TODO : Use verbose ?
        if (self.feeding_habitat is None) or (not use_already_computed_habitat) :
            feeding_habitat = self.feeding_habitat_structure.computeEvolvingFeedingHabitat(
                cohort_start,cohort_end,time_start,time_end,lat_min,lat_max,lon_min,lon_max,verbose)
        else :
            feeding_habitat = self.feeding_habitat

        landmask = self.landmask(
            habitat_field=(feeding_habitat
                if self.ikamoana_fields_structure.landmask_from_habitat else None),
            shallow_sea_to_ocean=self.ikamoana_fields_structure.shallow_sea_to_ocean)

        grad_lon, grad_lat = self.gradient(feeding_habitat, landmask)

        return self.taxis(grad_lon, grad_lat, name=feeding_habitat.name if name is None else name)
