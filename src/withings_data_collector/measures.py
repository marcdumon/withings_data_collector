'''Withings measurement types mapping and UI formatting helpers.'''

from datetime import datetime
from typing import Any

# Canonical mapping of Withings measurement types to SI units and display metadata.
# Keys are Withings meastype integers.
MEASURE_TYPES = {
    1: {'key': 'weight', 'name': 'Weight', 'unit': 'kg', 'precision': 2},
    4: {'key': 'height', 'name': 'Height', 'unit': 'm', 'precision': 2},
    5: {'key': 'fat_free_mass', 'name': 'Fat Free Mass', 'unit': 'kg', 'precision': 2},
    6: {'key': 'fat_ratio', 'name': 'Fat Ratio', 'unit': '%', 'precision': 1},
    8: {'key': 'fat_mass', 'name': 'Fat Mass', 'unit': 'kg', 'precision': 2},
    9: {'key': 'diastolic_bp', 'name': 'Diastolic Blood Pressure', 'unit': 'mmHg', 'precision': 0},
    10: {'key': 'systolic_bp', 'name': 'Systolic Blood Pressure', 'unit': 'mmHg', 'precision': 0},
    11: {'key': 'heart_pulse', 'name': 'Heart Pulse', 'unit': 'bpm', 'precision': 0},
    12: {'key': 'temperature', 'name': 'Temperature', 'unit': 'C', 'precision': 1},
    54: {'key': 'sp02', 'name': 'SP02', 'unit': '%', 'precision': 1},
    71: {'key': 'body_temperature', 'name': 'Body Temperature', 'unit': 'C', 'precision': 1},
    73: {'key': 'skin_temperature', 'name': 'Skin Temperature', 'unit': 'C', 'precision': 1},
    76: {'key': 'muscle_mass', 'name': 'Muscle Mass', 'unit': 'kg', 'precision': 2},
    77: {'key': 'hydration', 'name': 'Hydration', 'unit': 'kg', 'precision': 2},
    88: {'key': 'bone_mass', 'name': 'Bone Mass', 'unit': 'kg', 'precision': 2},
    123: {'key': 'vo2max', 'name': 'VO2 max', 'unit': 'ml/min/kg', 'precision': 1},
    130: {'key': 'atrial_fibrillation', 'name': 'Atrial Fibrillation', 'unit': '', 'precision': 0},
    155: {'key': 'vascular_age', 'name': 'Vascular Age', 'unit': 'years', 'precision': 0},
    167: {'key': 'nerve_health_feet', 'name': 'Nerve Health Score (Feet)', 'unit': '', 'precision': 0},
    168: {'key': 'ecw', 'name': 'Extracellular Water', 'unit': 'kg', 'precision': 2},
    169: {'key': 'icw', 'name': 'Intracellular Water', 'unit': 'kg', 'precision': 2},
    170: {'key': 'visceral_fat', 'name': 'Visceral Fat', 'unit': '', 'precision': 1},
    173: {'key': 'ffm_segments', 'name': 'Fat Free Mass Segments', 'unit': 'kg', 'precision': 2},
    174: {'key': 'fm_segments', 'name': 'Fat Mass Segments', 'unit': 'kg', 'precision': 2},
    175: {'key': 'muscle_segments', 'name': 'Muscle Mass Segments', 'unit': 'kg', 'precision': 2},
    196: {'key': 'eda_feet', 'name': 'Electrodermal Activity (Feet)', 'unit': '', 'precision': 2},
    226: {'key': 'bmr', 'name': 'Basal Metabolic Rate', 'unit': 'kcal/day', 'precision': 0},
    227: {'key': 'metabolic_age', 'name': 'Metabolic Age', 'unit': 'years', 'precision': 0},
    229: {'key': 'esc', 'name': 'Electrochemical Skin Conductance', 'unit': '', 'precision': 2},
}


def _compute_actual_value(raw_measure: dict[str, Any]) -> float:
    '''Compute the actual numeric value from Withings measure entry.

    Withings returns a 'value' and a 'unit' exponent such that:
        actual = value * (10 ** unit)
    '''
    value = raw_measure.get('value')
    unit_exp = raw_measure.get('unit', 0)
    try:
        return float(value) * (10 ** int(unit_exp))
    except Exception:
        # Fallback: return 0.0 on unexpected payloads
        return 0.0


def format_measure_for_display(raw_measure: dict[str, Any]) -> str:
    '''Return a human-readable SI string for a single raw Withings measure.

    Accepts the raw measure dict from the API (has keys 'value', 'unit', 'type').
    Uses `MEASURE_TYPES` for unit and precision. Unknown types fall back to a
    sensible numeric display without a unit.
    '''
    mtype = int(raw_measure.get('type', -1))
    meta = MEASURE_TYPES.get(mtype, {'name': f'Type {mtype}', 'unit': '', 'precision': 2})
    actual = _compute_actual_value(raw_measure)
    precision = meta.get('precision', 2)
    unit = meta.get('unit', '')
    if unit:
        return f'{actual:.{precision}f} {unit}'
    return f'{actual:.{precision}f}'


def get_measure_name(mtype: int) -> str:
    '''Return a human-friendly name for a meastype integer.'''
    return MEASURE_TYPES.get(mtype, {}).get('name', f'Type {mtype}')

__all__ = ['MEASURE_TYPES', 'format_measure_for_display', 'get_measure_name']


