"""Conversiones conservadoras para limpiadores pandas y pruebas locales."""
from datetime import date
import re

import pandas as pd


MONTHS = dict(zip(('ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'), range(1, 13)))
FULL_MONTHS = dict(zip(('ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO',
                       'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'), range(1, 13)))
FULL_MONTHS['SETIEMBRE'] = 9


def normalize_period(values):
    def parse(value):
        if pd.isna(value):
            return pd.NA
        value = str(value).strip().upper()
        if re.fullmatch(r'\d{6}(?:\.0+)?', value):
            year, month = int(value[:4]), int(value[4:6])
        elif re.fullmatch(r'(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)-\d{2}', value):
            year, month = 2000 + int(value[-2:]), MONTHS[value[:3]]
        else:
            return pd.NA
        return f'{year:04d}{month:02d}' if 1900 <= year <= 2099 and 1 <= month <= 12 else pd.NA
    return values.map(parse).astype('string')


def _integer(value):
    if pd.isna(value):
        return None
    v = str(value).strip()
    return int(v.split('.')[0]) if re.fullmatch(r'\d+(?:\.0+)?', v) else None


def parse_source_dates(values, year=None, month=None, day=None):
    """ISO explícito; fechas ambiguas solo con componentes corroborantes."""
    def direct(value):
        if pd.isna(value):
            return None
        v = str(value).strip()
        parts = None
        if re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T][\d:.]+)?', v):
            parts = re.split(r'[-/]', v.replace('T', ' ').split(' ')[0])
        elif re.fullmatch(r'\d{8}', v):
            parts = [v[:4], v[4:6], v[6:]]
        if parts:
            try:
                return date(*(int(part) for part in parts))
            except ValueError:
                pass
        return None

    parsed = values.map(direct)
    if year is not None and month is not None and day is not None:
        for index in parsed[parsed.isna()].index:
            value = values.loc[index]
            if pd.isna(value) or not re.fullmatch(r'\d{1,2}[-/]\d{1,2}[-/]\d{4}', str(value).strip()):
                continue
            yy, mm, dd = _integer(year.loc[index]), _integer(month.loc[index]), _integer(day.loc[index])
            if mm is None and pd.notna(month.loc[index]):
                mm = FULL_MONTHS.get(str(month.loc[index]).strip().upper())
            if None in (yy, mm, dd):
                continue
            a, b, y = (int(part) for part in re.split(r'[-/]', str(value).strip()))
            if y != yy or (a, b) not in ((dd, mm), (mm, dd)):
                continue
            try:
                parsed.loc[index] = date(yy, mm, dd)
            except ValueError:
                continue
    return pd.to_datetime(parsed, errors='coerce')
