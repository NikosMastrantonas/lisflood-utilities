# -*- coding: utf-8 -*-
"""
Created on Mon Apr  4 17:31:52 2022

@author: tilloal
"""

#!/usr/bin/env python  
# -*- coding: utf-8 -*-

__author__ = "Hylke E. Beck"
__email__ = "hylke.beck@gmail.com"
__date__ = "January 2022"

import os, sys, glob, time, pdb
import pandas as pd
import numpy as np
from config_comp import *
import netCDF4 as nc
from netCDF4 import Dataset
from skimage.transform import resize
from skimage.transform import downscale_local_mean
from datetime import datetime, timedelta
from scipy import ndimage as nd
#import rasterio
from skimage.io import imread
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable



#print(meteo_vars_config['tp'][KEY_OFFSET])
#%%

# function to compute mean wind speed from u and v components of wind
def wind_uv_to_spd(U,V):
    """
    Calculates the wind speed from the u and v wind components
    Inputs:
      U = west/east direction (wind from the west is positive, from the east is negative)
      V = south/noth direction (wind from the south is positive, from the north is negative)
    """
    WSPD=np.sqrt(U**2+V**2)
    return WSPD


def load_country_code_map(filepath,mapsize):
    
    #src = rasterio.open(filepath)
    src=imread(filepath)
    country_code_map = src.astype(np.single)
    country_code_map_refmatrix = src.get_transform()
    #src.close()

    # Check if country border raster covers entire globe
    assert (country_code_map_refmatrix[0]==-180) & (country_code_map_refmatrix[3]==90)

    country_code_map = resize(country_code_map,mapsize,order=0,mode='edge',anti_aliasing=False)
    country_code_map[country_code_map==158] = 156 # Add Taiwan to China
    country_code_map[country_code_map==736] = 729 # South Sudan missing from map
    country_code_map[country_code_map==0] = np.NaN
    
    return country_code_map
    
def load_us_state_code_map(filepath,mapsize):
    
    #src = rasterio.open(filepath)
    src=imread(filepath)
    state_code_map = src.astype(np.single)
    state_code_map = resize(state_code_map,mapsize,order=0,mode='edge',anti_aliasing=False)
    state_code_map_refmatrix = src.get_transform()
    #src.close()

    # Check if state border raster covers entire globe
    assert (state_code_map_refmatrix[0]==-180) & (state_code_map_refmatrix[3]==90)

    return state_code_map
    
def latlon2rowcol(lat,lon,res,lat_upper,lon_left):
    row = np.round((lat_upper-lat)/res-0.5).astype(int)
    col = np.round((lon-lon_left)/res-0.5).astype(int)    
    return row.squeeze(),col.squeeze()

def rowcol2latlon(row,col,res,lat_upper,lon_left):
    lat = lat_upper-row*res-res/2
    lon = lon_left+col*res+res/2
    return lat.squeeze(),lon.squeeze()
            
def imresize_mean(oldarray,newshape):
    '''Resample an array using simple averaging'''
    
    oldshape = oldarray.shape
    
    factor = oldshape[0]/newshape[0]
    
    if factor==int(factor):
        factor = int(factor)
        newarray = downscale_local_mean(oldarray,(factor,factor))
        
    else:
        factor = 1
        while newshape[0]*factor<oldshape[0]:
            factor = factor+1        
        intarray = resize(oldarray,(int(newshape[0]*factor),int(newshape[1]*factor)),order=0,mode='constant',anti_aliasing=False)
        newarray = downscale_local_mean(intarray,(factor,factor))

    return newarray
   
def fill(data, invalid=None):
    '''Nearest neighbor interpolation gap fill by Juh_'''
    
    if invalid is None: invalid = np.isnan(data)
    ind = nd.distance_transform_edt(invalid, return_distances=False, return_indices=True)
    return data[tuple(ind)]    

def load_config(filepath):
    '''Load configuration file into dict'''
    
    df = pd.read_csv(filepath,header=None,index_col=False)
    config = {}
    for ii in np.arange(len(df)): 
        string = df.iloc[ii,0].replace(" ","")
        varname = string.rpartition('=')[0]
        varcontents = string.rpartition('=')[2]
        try:
            varcontents = float(varcontents)
        except:
            pass
        config[varname] = varcontents
    return config
    
def initialize_netcdf(outfile,lat,lon,varname,units,compression,least_significant_digit):
    
    ncfile = Dataset(outfile, 'w', format='NETCDF4_CLASSIC')
    ncfile.history = 'Created on %s' % datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    ncfile.Conventions = 'CF-1.6'
    ncfile.Source_Software = 'Python netCDF4'
    ncfile.reference = 'A global daily high-resolution gridded meteorological data set for 1979-2019'  #####
    ncfile.title = 'Lisflood meteo maps 1981 for EUROPE setting Nov. 2021'
    ncfile.keywords = 'Lisflood, Global'
    ncfile.source = 'ERA5-land'
    ncfile.institution = 'European Commission - Economics of climate change Unit (JRC.C.6) : https://ec.europa.eu/jrc/en/research-topic/climate-change'
    ncfile.comment = 'The timestamp marks the end of the aggregation interval for a given map.'
    ncfile.createDimension('lon', len(lon))
    ncfile.createDimension('lat', len(lat))
    ncfile.createDimension('time', None)
    ncfile.createVariable('lon', 'f8', ('lon',),complevel=4, zlib=True)
    ncfile.variables['lon'][:] = lon
    ncfile.variables['lon'].units = 'degrees_east'
    ncfile.variables['lon'].standard_name = 'longitude'
    ncfile.variables['lon'].long_name = 'longitude'
    ncfile.createVariable('lat', 'f8', ('lat',),complevel=4, zlib=True)
    ncfile.variables['lat'][:] = lat
    ncfile.variables['lat'].units = 'degrees_north'
    ncfile.variables['lat'].standard_name = 'latitude'
    ncfile.variables['lat'].long_name = 'latitude'
    ncfile.createVariable('time', 'i4', 'time',complevel=4, zlib=True)
    ncfile.variables['time'].units = 'days since 1979-01-01 00:00:00' #initial date has an importance when it comes to LISFLOOD
    ncfile.variables['time'].long_name = 'time'
    ncfile.variables['time'].calendar = 'proleptic_gregorian'
    if compression=="1":
        ncfile.createVariable(varname, 'i2', ('time', 'lat', 'lon'),zlib=True,
             fill_value=-9999,complevel=4)
        ncfile.variables[varname].units = units
        scale_factor=meteo_vars_config[varname][KEY_SCALE_FACTOR]   
        add_offset=meteo_vars_config[varname][KEY_OFFSET]   
        ncfile.variables[varname].scale_factor=scale_factor      
        ncfile.variables[varname].add_offset=add_offset
    else:
        ncfile.createVariable(varname, 'f4', ('time', 'lat', 'lon'),zlib=True,
        fill_value=-9999,least_significant_digit=least_significant_digit,complevel=4)
        ncfile.variables[varname].units = units
        
    ncfile.variables[varname].grid_mapping='wgs_1984'
    ncfile.variables[varname].esri_pe_string='GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]'
    #ncfile.variables[varname].set_auto_maskandscale(True)
    ncfile.variables[varname].missing_value=-9999
    #add projection system 
    proj = ncfile.createVariable('wsg_1984', 'i4')
    proj.grid_mapping_name = 'latitude_longitude'
    proj.semi_major_axis= '6378137.0'
    proj.inverse_flattening='298.257223563'
    proj.proj4_params='+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'
    proj.EPSG_code='EPSG:4326'
    
    return ncfile

def potential_evaporation(data,albedo,factor,doy,lat,elev):
    """
    Calculate potential evaporation (mm/d) using an approach based on Penman-
    Monteith. More details provided in the LISVAP documentation (Van der 
    Knijff, 2006).
    
    Van der Knijff, J., 2006. LISVAP – Evaporation Pre-Processor for the 
        LISFLOOD Water Balance and Flood Simulation Model, User Manual. EUR 
        22639 EN, Office for Official Publications of the European 
        Communities, Luxembourg, 31 pp.
    
    INPUTS
    data:   Dict with grids of tmean, tmin, tmax (all in degrees Celsius), 
            relhum (%), wind (m/s), pres(mbar), swd (W/m2), and lwd (W/m2)
    albedo: Albedo (0 to 1)
    factor: Empirical factor related to land cover (>0)
    doy:    Day of year (1 to 366)
    lat:    Latitude grid (degrees)
    elev:   Elevation grid (m asl)
    
    OUTPUTS
    pet:    Potential evaporation (mm/d)
    """

    # Difference between daily maximum and minimum temperature (degrees C)
    DeltaT = data['tmax']-data['tmin']
    DeltaT[DeltaT<0] = 0
    
    # Empirical constant in windspeed formula (if DeltaT is less than 12 
    # degrees C, BU=0.54)
    BU = 0.54+0.35*((DeltaT-12)/4)
    BU[BU<0.54] = 0.54
    
    # Goudriaan equation (1977) to calculate saturated vapour pressure (mbar)
    ESat = 6.10588*np.exp((17.32491*data['tmean'])/(data['tmean']+238.102))
    
    # Actual vapor pressure calculated from relative humidity (mbar)
    EAct = data['relhum']*ESat/100
    
    # Vapour pressure deficit (mbar)
    VapPressDef = ESat-EAct
    VapPressDef[VapPressDef<0] = 0

    # Evaporative demand (mm/d)
    EA = {}
    for key in factor.keys():
        EA[key] = 0.26*VapPressDef*(factor[key]+BU*data['wind'])
        
    # Latent heat of vaporization (MJ/kg)
    LatHeatVap = 2.501-0.002361*data['tmean']
        
    # Allen et al. (1998) equation 8 (mbar/degrees C)
    Psychro = 10*(1.013*10**-3*data['pres']/10)/(0.622*LatHeatVap)
    
    # Slope of saturated vapour pressure curve (mbar/degrees C)
    Delta = (238.102*17.32491*ESat)/((data['tmean']+238.102)**2)
    
    
    #--------------------------------------------------------------------------
    #   Extra-terrestrial radiation
    #--------------------------------------------------------------------------

    # Solar declination (rad)
    Declin_rad = np.arcsin(0.39795*np.cos(0.2163108+2*np.arctan(0.9671396*np.tan(0.00860*(doy-186)))))
    
    # Convert latitude from degrees to radians
    lat_rad = lat*np.pi/180
    
    # Solar constant at top of the atmosphere (J/m2/s)
    SolarConstant = 1370*(1+0.033*np.cos(2*np.pi*doy/365))
    
    # Day length (h) equation from Forsythe et al. (1995; https://doi.org/10.1016/0304-3800(94)00034-F)
    sinLD = np.sin(Declin_rad)*np.sin(lat_rad)
    cosLD = np.cos(Declin_rad)*np.cos(lat_rad)
    DayLength = 24-(24/np.pi)*np.arccos((np.sin(0.8333*np.pi/180)+sinLD)/cosLD)
    DayLength = np.tile(fill(DayLength[:,:1]),(1,DayLength.shape[1])) # Nearest-neighbor gap filling
    
    # Integral of solar height over the day (s)
    IntSolarHeight = 3600*(DayLength*sinLD+(24/np.pi)*cosLD*np.sqrt(1-(sinLD/cosLD)**2))
    IntSolarHeight[IntSolarHeight<0] = 0
    IntSolarHeight = np.tile(fill(IntSolarHeight[:,:1]),(1,IntSolarHeight.shape[1])) # Nearest-neighbor gap filling
    
    # Daily extra-terrestrial radiation (J/m2/d)
    Ra = IntSolarHeight*SolarConstant
    
    
    #--------------------------------------------------------------------------
    #   Net absorbed radiation
    #--------------------------------------------------------------------------

    # Clear-sky radiation (J/m2/d) from Allen et al. (1998; equation 37)
    Rso = Ra*(0.75+(2*10**-5*elev))
    
    # Adjustment factor for cloud cover
    TransAtm_Allen = (data['swd']*86400+1)/(Rso+1)
    AdjCC = 1.8*TransAtm_Allen-0.35
    AdjCC[AdjCC<0.05] = 0.05
    AdjCC[AdjCC>1] = 1
    
    # Net emissivity
    EmNet = 0.56-0.079*np.sqrt(EAct)
    
    # Net longwave radiation (J/m2/d)
    StefBoltzConstant = 4.903*10**-3 # J/K4/m2/d
    RN = StefBoltzConstant*((data['tmean']+273.15)**4)*EmNet*AdjCC    

    # Net absorbed radiation of reference vegetation canopy (mm/d)
    RNA = {}
    for key in albedo.keys():
        RNA[key] = ((1-albedo[key])*data['swd']*86400-RN)/(10**6*LatHeatVap)
        RNA[key] = RNA[key].clip(0,None)
        
    # Potential reference evapotranspiration rate (mm/d)
    pet = {}
    for key in albedo.keys():
        pet[key] = ((Delta*RNA[key])+(Psychro*EA[key]))/(Delta+Psychro)
    
    return pet
    
def makefig(folder,title,data,vmin,vmax):
    if os.path.isdir(folder)==False:
        os.makedirs(folder)
    plt.figure()
    ax = plt.gca()
    im = ax.imshow(data,vmin=vmin,vmax=vmax)
    ax.set_axis_off()
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="5%", pad=0.05)   
    plt.colorbar(im, cax=cax)
    plt.title(title)
    plt.savefig(os.path.join(folder,title+'.png'),dpi=300,bbox_inches='tight')
    plt.close()