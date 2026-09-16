"""Terrestrial time-lapse glacier velocity pipeline.

Python implementation of the methodology of

    Singh, P., Vijay, S., Azam, M.F. (2026). High-Frequency observations of
    glacier ice velocities at Drang Drung Glacier, Western Himalaya, using a
    terrestrial time-lapse imaging system. Science of Remote Sensing 13, 100431.
    https://doi.org/10.1016/j.srs.2026.100431

Stages (see ``python -m glacier_tlc --help``):

    inventory  -> read EXIF dates, keep one image per day near the target hour,
                  assign each image to a camera-position group
    quality    -> image quality metrics + scene-visibility check, apply
                  manual include/exclude lists, write the filtered image list
    extract    -> crop + enhance (CLAHE == MATLAB adapthisteq) every ROI of
                  every usable image once, cache to disk
    track      -> for every image pair (nC2 within a group, limited baseline)
                  and every ROI: SIFT keypoints -> KLT (bidirectional) ->
                  RANSAC affine -> direction filter -> per-pair statistics
    velocity   -> stable-region correction, NMAD uncertainty, photogrammetric
                  scaling to metres, horizontal / vertical components
    aggregate  -> weekly-to-monthly windows, annual / seasonal / interannual
                  summaries, short-term daily series with local maxima
    plots      -> paper-style figures + QA figures
    report     -> markdown summary of all deliverables
"""

__version__ = "1.0.0"
