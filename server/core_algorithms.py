
import ee
import geemap
import os
import json
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from scipy.interpolate import interp1d

# Common Init
def init_gee():
    project_id = os.getenv('GCP_PROJECT_ID', 'terrior-hunter')
    try:
        ee.Initialize(project=project_id)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project_id)

def get_roi(search_radius=50, center_lat=35.8, center_lon=109.4):
    # search_radius 单位为km，转换为米
    return ee.Geometry.Point([center_lon, center_lat]).buffer(search_radius * 1000).bounds()

def calculate_lsi(roi, w_slope=0.35, w_elev=0.25, w_aspect=0.20, w_climate=0.20):
    dem = ee.Image("USGS/SRTMGL1_003").clip(roi)
    climate = ee.Image("WORLDCLIM/V1/BIO").clip(roi)
    temp = climate.select('bio01').multiply(0.1)
    
    slope = ee.Terrain.slope(dem)
    aspect = ee.Terrain.aspect(dem)

    # Reclassify
    def reclassify_slope_img(img):
        return ee.Image(1) \
            .where(img.lt(5), 9)    \
            .where(img.gte(5).And(img.lt(15)), 8) \
            .where(img.gte(15).And(img.lt(25)), 6) \
            .where(img.gte(25), 1)

    def reclassify_aspect_img(img):
        return ee.Image(1) \
            .where(img.gte(135).And(img.lt(225)), 9) \
            .where(img.gte(90).And(img.lt(135)), 7) \
            .where(img.gte(225).And(img.lt(270)), 7) \
            .where(img.lt(90).Or(img.gte(270)), 3)

    def reclassify_elevation_img(img):
        return ee.Image(1) \
            .where(img.lt(600), 3) \
            .where(img.gte(600).And(img.lt(800)), 6) \
            .where(img.gte(800).And(img.lt(1300)), 9) \
            .where(img.gte(1300), 5)

    score_slope = reclassify_slope_img(slope)
    score_aspect = reclassify_aspect_img(aspect)
    score_dem = reclassify_elevation_img(dem)
    score_climate = temp.add(50).divide(100).multiply(8).add(1).clamp(1, 9)

    lsi = score_slope.multiply(w_slope) \
        .add(score_dem.multiply(w_elev)) \
        .add(score_aspect.multiply(w_aspect)) \
        .add(score_climate.multiply(w_climate))

    return lsi.multiply(10).rename('Suitability_Score')

# ----------------- AHP ALGORITHM -----------------

def run_ahp_algorithm(w_slope=0.35, w_elev=0.25, w_aspect=0.20, w_climate=0.20,
                      search_radius=50, center_lat=35.8, center_lon=109.4):
    init_gee()
    roi = get_roi(search_radius, center_lat=center_lat, center_lon=center_lon)
    final_suitability = calculate_lsi(roi, w_slope, w_elev, w_aspect, w_climate)

    # Stats
    try:
        stats = final_suitability.sample(
            region=roi, scale=500, numPixels=100
        ).aggregate_stats('Suitability_Score')
        mean_score = stats.get('mean').getInfo()
    except:
        mean_score = 0

    try:
        # 计算各个分级的地块数量
        # S级: > 90
        result_s = final_suitability.gt(90).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=500,
            maxPixels=1e9
        ).getInfo()
        s_count = int(result_s.get('Suitability_Score', 0) if result_s else 0)
        
        # A级: 80-90
        result_a = final_suitability.gte(80).And(final_suitability.lte(90)).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=500,
            maxPixels=1e9
        ).getInfo()
        a_count = int(result_a.get('Suitability_Score', 0) if result_a else 0)
        
        # B级: 70-80
        result_b = final_suitability.gte(70).And(final_suitability.lt(80)).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=500,
            maxPixels=1e9
        ).getInfo()
        b_count = int(result_b.get('Suitability_Score', 0) if result_b else 0)
        
        # C级: 60-70
        result_c = final_suitability.gte(60).And(final_suitability.lt(70)).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=500,
            maxPixels=1e9
        ).getInfo()
        c_count = int(result_c.get('Suitability_Score', 0) if result_c else 0)
        
        # D级: < 60
        result_d = final_suitability.lt(60).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=500,
            maxPixels=1e9
        ).getInfo()
        d_count = int(result_d.get('Suitability_Score', 0) if result_d else 0)
        
        suitability_dist = [s_count, a_count, b_count, c_count, d_count]
        total_count = s_count + a_count + b_count + c_count + d_count
    except Exception as e:
        s_count = 0
        suitability_dist = [0,0,0,0,0]
        total_count = 0

    Map = geemap.Map(center=[center_lat, center_lon], zoom=11, basemap='SATELLITE')
    vis_params = {'min': 30, 'max': 90, 'palette': ['green', 'yellow', 'orange', 'red']}
    Map.addLayer(final_suitability, vis_params, 'Apple Orchard Suitability (AHP)')
    prime_locations = final_suitability.gt(85).selfMask()
    Map.addLayer(prime_locations, {'palette': ['purple']}, 'Prime Locations (S-Class)')
    
    return {
        "map_object": Map,
        "json_data": {
            "avg_score": round(mean_score, 1),
            "s_class_count": s_count,
            "a_class_count": a_count,
            "b_class_count": b_count,
            "c_class_count": c_count,
            "d_class_count": d_count,
            "total_count": total_count,
            "suitability_dist": suitability_dist
        },
        "ee_image": final_suitability,  # For internal use
        "meta": {
            "center_lat": center_lat,
            "center_lon": center_lon,
            "search_radius_km": search_radius,
        },
    }

# ----------------- PHENOLOGY MATCHING -----------------

def get_ndvi_series(geometry, year=2020):
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    col = ee.ImageCollection('MODIS/006/MOD13Q1').filterDate(start, end).select('NDVI')
    
    def add_ndvi_property(img):
        ndvi_mean = img.reduceRegion(ee.Reducer.mean(), geometry, scale=250, bestEffort=True).get('NDVI')
        return img.set('ndvi_mean', ndvi_mean)
    
    col_with_ndvi = col.map(add_ndvi_property)
    dates = col_with_ndvi.aggregate_array('system:time_start').getInfo()
    values = col_with_ndvi.aggregate_array('ndvi_mean').getInfo()
    
    if not dates or not values or len(dates) == 0:
        return np.full(365, np.nan)
    
    from datetime import datetime
    doys = []
    clean_values = []
    
    for d, v in zip(dates, values):
        if isinstance(d, (int, float)) and d is not None:
            try:
                doy = datetime.fromtimestamp(d/1000).timetuple().tm_yday
                if v is not None:
                    clean_values.append(float(v) * 0.0001)
                    doys.append(doy)
                else:
                    clean_values.append(np.nan)
                    doys.append(doy)
            except:
                pass
    
    if len([v for v in clean_values if not np.isnan(v)]) < 3:
        return np.full(365, np.nan)
    
    x = np.array(doys)
    y = np.array(clean_values)
    valid_idx = ~np.isnan(y)
    
    if valid_idx.sum() < 3:
        return np.full(365, np.nan)
    
    f = interp1d(x[valid_idx], y[valid_idx], kind='linear', fill_value='extrapolate')
    return f(np.arange(1, 366))

def extract_landmarks(ndvi_series):
    series = np.array(ndvi_series, dtype=float)
    if np.all(np.isnan(series)): return None, None
    valid = ~np.isnan(series)
    if valid.sum() < 3: return None, None
    x = np.arange(series.size)
    series[~valid] = np.interp(x[~valid], x[valid], series[valid])
    
    smooth_ndvi = savgol_filter(series, window_length=31, polyorder=3)
    d1 = np.gradient(smooth_ndvi)
    d2 = np.gradient(d1)
    d3 = np.gradient(d2)
    
    from scipy.signal import find_peaks
    upward_peaks, _ = find_peaks(d3[:180], height=0.0001, distance=20) 
    downward_peaks, _ = find_peaks(-d3[180:], height=0.0001, distance=20)
    downward_peaks += 180 
    
    try:
        landmarks = {
            'Greenup': upward_peaks[0],
            'Maturity': upward_peaks[-1],
            'Senescence': downward_peaks[0],
            'Dormancy': downward_peaks[-1]
        }
    except:
        landmarks = {'Greenup': 100, 'Maturity': 150, 'Senescence': 260, 'Dormancy': 300}
        
    return smooth_ndvi, landmarks

def warp_and_match(ref_curve, tgt_curve, ref_lm, tgt_lm):
    key_points_ref = sorted(list(ref_lm.values()))
    key_points_tgt = sorted(list(tgt_lm.values()))
    x_ref = [0] + key_points_ref + [365]
    x_tgt = [0] + key_points_tgt + [365]
    
    warp_func = interp1d(x_tgt, x_ref, kind='linear', fill_value="extrapolate")
    inverse_warp = interp1d(x_ref, x_tgt, kind='linear', fill_value="extrapolate")
    original_time_indices = inverse_warp(np.arange(len(ref_curve)))
    original_time_indices = np.clip(original_time_indices, 0, 364)
    warped_tgt_curve = interp1d(np.arange(len(tgt_curve)), tgt_curve)(original_time_indices)
    return warped_tgt_curve

def run_phenology_algorithm(year=2020, similarity_threshold=60.0, target_region=None, search_radius=50):
    init_gee()
    # 根据目标产区获取ROI
    if target_region:
        # 解析目标产区的经纬度信息
        if '陕西洛川' in target_region:
            # 使用洛川的经纬度
            roi = get_roi(search_radius)
        elif '山东烟台' in target_region:
            # 使用烟台的经纬度
            roi = ee.Geometry.Point([121.4, 37.5]).buffer(search_radius * 1000).bounds()
        elif '新疆阿克苏' in target_region:
            # 使用阿克苏的经纬度
            roi = ee.Geometry.Point([80.2, 41.2]).buffer(search_radius * 1000).bounds()
        elif '辽宁瓦房店' in target_region:
            # 使用瓦房店的经纬度
            roi = ee.Geometry.Point([122.0, 39.7]).buffer(search_radius * 1000).bounds()
        else:
            # 默认使用洛川
            roi = get_roi(search_radius)
    else:
        # 默认使用洛川
        roi = get_roi(search_radius)
    final_suitability = calculate_lsi(roi)
    
    prime = final_suitability.gt(60).selfMask()
    vec = prime.reduceToVectors(
        scale=1000, geometry=roi, geometryType='polygon', maxPixels=1e13, eightConnected=True
    )
    vec_with_area = vec.map(lambda f: f.set('area', f.geometry().area(maxError=50)))
    best_feat = vec_with_area.sort('area', False).first()
    
    if not best_feat:
        raise RuntimeError("No suitable area found > 60 score")
        
    best_geom = best_feat.geometry()
    
    ref_ndvi = get_ndvi_series(best_geom, year=year)
    ref_smooth, ref_marks = extract_landmarks(ref_ndvi)
    
    sample_pts = final_suitability.sample(
        region=roi, scale=500, numPixels=8, geometries=True
    ).getInfo().get('features', [])
    
    best_match = None
    results = []
    SIM_THRESHOLD = similarity_threshold

    for f in sample_pts:
        geom = ee.Geometry(f['geometry'])
        ndvi_ts = get_ndvi_series(geom, year=year)
        smooth, marks = extract_landmarks(ndvi_ts)
        if smooth is None: continue
        
        warped = warp_and_match(ref_smooth, smooth, ref_marks, marks)
        
        # Sim
        s1 = np.gradient(ref_smooth)
        s2 = np.gradient(warped)
        dist = np.mean(np.abs(s1 - s2))
        sim_score = 100 * np.exp(-10 * dist)
        
        if sim_score >= SIM_THRESHOLD:
            results.append({
                'similarity': sim_score,
                'smooth': smooth,
                'warped': warped,
                'landmarks': marks,
                'geometry': f['geometry']
            })
            
    results.sort(key=lambda x: x['similarity'], reverse=True)
    
    if not results:
        # Fallback to dummy if no match found just to show something on frontend
        # Or raise error. Let's return the Ref curve at least.
        return {
            "json_data": {
                "ref_curve": ref_smooth.tolist(),
                "tgt_curve": [],
                "warped_curve": [],
                "average_similarity": 0
            }
        }
        
    top = results[0]
    
    # Calculate average similarity
    average_similarity = sum(r['similarity'] for r in results) / len(results)
    
    # Map Generation
    Map = geemap.Map(center=[35.8, 109.4], zoom=10, basemap='SATELLITE')
    ref_fc = ee.FeatureCollection([ee.Feature(best_geom)])
    Map.addLayer(ref_fc.style(**{'color': '#0066ff', 'width': 3, 'fillColor': '#0066ff33'}), {}, 'Reference Area')

    top_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry(r['geometry']), {'similarity': r['similarity']})
        for r in results[:10]
    ])
    Map.addLayer(top_fc.style(**{'color': '#ff6600', 'pointSize': 8, 'width': 2}), {}, 'Similar Areas')
    
    return {
        "map_object": Map,
        "json_data": {
            "average_similarity": round(average_similarity, 1),
            "ref_curve": ref_smooth.tolist(),
            "tgt_curve": top['smooth'].tolist(),
            "warped_curve": top['warped'].tolist(),
            "landmarks": {k: int(v) for k, v in top['landmarks'].items()}
        }
    }
