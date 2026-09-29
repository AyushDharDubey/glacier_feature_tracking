# Glacier Tracking Module using Time Lapse Camera

Python implementation of the glacier-velocity methodology of

> Singh, P., Vijay, S., Azam, M.F. (2026). *High-Frequency observations of glacier ice
> velocities at Drang Drung Glacier, Western Himalaya, using a terrestrial time-lapse
> imaging system.* Science of Remote Sensing 13, 100431.
> https://doi.org/10.1016/j.srs.2026.100431

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# put the daily JPEGs (with EXIF capture time) in ./input, edit config.yaml if needed
python -m glacier_tlc all                # every stage in order
# Or run individual stages:
python -m glacier_tlc inventory
python -m glacier_tlc quality
python -m glacier_tlc extract
python -m glacier_tlc track
python -m glacier_tlc velocity
python -m glacier_tlc aggregate
python -m glacier_tlc plots
python -m glacier_tlc report
```