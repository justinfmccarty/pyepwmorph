
def read_epw(path_data):
    tmy_labels = [
        'year', 'month', 'day', 'hour', 'minute', 'datasource', 'drybulb_C',
        'dewpoint_C', 'relhum_percent', 'atmos_Pa', 'exthorrad_Whm2',
        'extdirrad_Whm2', 'horirsky_Whm2', 'glohorrad_Whm2', 'dirnorrad_Whm2',
        'difhorrad_Whm2', 'glohorillum_lux', 'dirnorillum_lux',
        'difhorillum_lux', 'zenlum_lux', 'winddir_deg', 'windspd_ms',
        'totskycvr_tenths', 'opaqskycvr_tenths', 'visibility_km',
        'ceiling_hgt_m', 'presweathobs', 'presweathcodes', 'precip_wtr_mm',
        'aerosol_opt_thousandths', 'snowdepth_cm', 'days_last_snow', 'Albedo',
        'liq_precip_depth_mm', 'liq_precip_rate_Hour'
    ]

    df = pd.read_csv(path_data,
                     skiprows=8,
                     header=None,
                     index_col=False,
                     usecols=list(range(0, 35)),
                     names=tmy_labels)#.drop('datasource', axis=1)

    df['hour'] = df['hour'].astype(int)
    if df['hour'][0] == 1:
        print('TMY file hours reduced from 1-24h to 0-23h')
        df['hour'] = df['hour'] - 1
    else:
        print('TMY file hours maintained at 0-23hr')
    df['minute'] = 0
    return df
