"""Gemeinsames Analyse-Raster fuer alle Ebenen.

Das Raster ist regelmaessig in Web-Mercator (EPSG:3857), damit die erzeugten PNGs
in Leaflet ohne Verzerrung als imageOverlay ueber den OSM-Kacheln liegen.
300 m Mercator entsprechen bei 52,5 Grad N ca. 183 m am Boden.
"""
import math, os
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
STATIC = os.path.join(ROOT, 'data', 'static')
WEB_DATA = os.path.join(ROOT, 'web', 'data')

R = 6378137.0
RES = 300.0                               # Zellgroesse in Mercator-Metern
WEST, EAST, SOUTH, NORTH = 11.20, 14.80, 51.30, 53.60


def merc_x(lon):
    return np.radians(lon) * R


def merc_y(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * R


def lon_of(x):
    return np.degrees(x / R)


def lat_of(y):
    return np.degrees(2 * np.arctan(np.exp(y / R)) - np.pi / 2)


X0 = math.floor(merc_x(WEST) / RES) * RES
X1 = math.ceil(merc_x(EAST) / RES) * RES
Y0 = math.floor(merc_y(SOUTH) / RES) * RES
Y1 = math.ceil(merc_y(NORTH) / RES) * RES
NX = int(round((X1 - X0) / RES))
NY = int(round((Y1 - Y0) / RES))
SHAPE = (NY, NX)                          # Zeile 0 = Norden


def cell_centers():
    """(x, y) Mercator-Mittelpunkte als 2D-Arrays."""
    xs = X0 + (np.arange(NX) + 0.5) * RES
    ys = Y1 - (np.arange(NY) + 0.5) * RES
    return np.meshgrid(xs, ys)


def cell_lonlat():
    x, y = cell_centers()
    return lon_of(x), lat_of(y)


def to_index(x, y):
    """Mercator-Koordinaten -> (zeile, spalte), -1 ausserhalb."""
    i = np.floor((x - X0) / RES).astype(np.int64)
    j = np.floor((Y1 - y) / RES).astype(np.int64)
    ok = (i >= 0) & (i < NX) & (j >= 0) & (j < NY)
    return np.where(ok, j, -1), np.where(ok, i, -1)


def lonlat_to_pixel(lon, lat):
    """Gleitkomma-Pixelkoordinaten (Spalte, Zeile) fuer Polygon-Rasterung."""
    return (merc_x(np.asarray(lon)) - X0) / RES, (Y1 - merc_y(np.asarray(lat))) / RES


def leaflet_bounds():
    """[[sued, west], [nord, ost]] fuer L.imageOverlay."""
    return [[float(lat_of(Y0)), float(lon_of(X0))], [float(lat_of(Y1)), float(lon_of(X1))]]
