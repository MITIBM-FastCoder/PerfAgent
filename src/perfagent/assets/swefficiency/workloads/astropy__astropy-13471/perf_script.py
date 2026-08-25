import timeit

timeit.template = """
def inner(_it, _timer{init}):
    {setup}
    _profile_duration = 10.0

    _t0 = _timer()
    for _i in _it:
        retval = {stmt}
    _t1 = _timer()

    _first_time = _t1 - _t0

    if _first_time >= _profile_duration:
        return _first_time

    _pad_start = _timer()
    while _timer() - _pad_start < _profile_duration:
        retval = {stmt}

    return _first_time
"""


import statistics
import astropy.io.fits
import astropy.units as u
from astropy.coordinates import (
    EarthLocation, AltAz, SkyCoord, CoordinateAttribute, BaseCoordinateFrame,
    UnitSphericalRepresentation, RepresentationMapping,
)
from astropy.time import Time

def setup():
    global ExampleFrame, coord_attr, coord
    class ExampleFrame(BaseCoordinateFrame):
        frame_specific_representation_info = {
            UnitSphericalRepresentation: [
                RepresentationMapping("lon", "fov_lon"),
                RepresentationMapping("lat", "fov_lat"),
            ]
        }
        default_representation = UnitSphericalRepresentation
        coord_attr = CoordinateAttribute(default=None, frame=AltAz)

    loc = EarthLocation.of_site("Roque de los Muchachos")
    t = Time.now()
    frame = AltAz(location=loc, obstime=t)
    coord = SkyCoord(0 * u.deg, 0 * u.deg, frame=frame)

def workload():
    global ExampleFrame, coord
    ExampleFrame(coord_attr=coord)

runtime = timeit.timeit(workload, number=1, setup=setup)

print("Mean:", runtime * 1000)
