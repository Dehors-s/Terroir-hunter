from __future__ import annotations

import threading
import time
from pathlib import Path
import runpy
import json

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import sys
import math
import uuid
import datetime
import numpy as np
from typing import List, Optional, Dict, Any

try:
    from scipy.signal import savgol_filter, find_peaks
except ImportError:
    print("Warning: scipy not found. Phenology simulation will be limited.")
    savgol_filter = None
    find_peaks = None

try:
    from scipy.interpolate import interp1d
except ImportError:
    print("Warning: scipy.interpolate not found. Using simple interpolation.")
    interp1d = None

try:
    from scipy.interpolate import PchipInterpolator
except ImportError:
    PchipInterpolator = None

# Earth Engine 初始化（无交互环境下失败时自动降级，避免服务启动中断）
import os
EE_PROJECT_ID = os.getenv('GCP_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT')
try:
    import ee
    try:
        if EE_PROJECT_ID:
            ee.Initialize(project=EE_PROJECT_ID)
            print(f"✓ Earth Engine initialized with project: {EE_PROJECT_ID}")
        else:
            ee.Initialize()
            print("✓ Earth Engine initialized with default project from credentials")
        USE_REAL_GEE_DATA = True
    except Exception as ee_init_error:
        print(f"Warning: Earth Engine initialization failed ({ee_init_error}). Falling back to simulated data.")
        USE_REAL_GEE_DATA = False
except ImportError:
    print("Warning: Earth Engine package not available. Falling back to simulated data.")
    USE_REAL_GEE_DATA = False
    ee = None

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))
from server.core_algorithms import run_ahp_algorithm, run_phenology_algorithm
from pydantic import BaseModel, Field

FRONTEND_DIR = ROOT_DIR / "frontend"

OUTPUT_SUITABILITY_MAP = ROOT_DIR / "suitability_map.html"
OUTPUT_SIMILARITY_MAP = ROOT_DIR / "similar_regions_map.html"
OUTPUT_SIMILARITY_CSV = ROOT_DIR / "similar_regions.csv"
OUTPUT_PHENOLOGY_PNG = ROOT_DIR / "phenology_matching_analysis.png"
OUTPUT_AHP_JSON = ROOT_DIR / "ahp_results.json"
OUTPUT_PHENOLOGY_JSON = ROOT_DIR / "phenology_results.json"
GOLDEN_STANDARDS_FILE = ROOT_DIR / "golden_standards.json"

ALLOWED_OUTPUTS = {
    "suitability_map.html": OUTPUT_SUITABILITY_MAP,
    "similar_regions_map.html": OUTPUT_SIMILARITY_MAP,
    "similar_regions.csv": OUTPUT_SIMILARITY_CSV,
    "phenology_matching_analysis.png": OUTPUT_PHENOLOGY_PNG,
    "ahp_results.json": OUTPUT_AHP_JSON,
    "phenology_results.json": OUTPUT_PHENOLOGY_JSON,
}

LAST_AHP_IMAGE = None
LAST_AHP_META: Dict[str, Any] = {}

TASKS = {
    "ahp": {"status": "idle", "error": None, "started_at": None, "finished_at": None},
    "hybrid": {"status": "idle", "error": None, "started_at": None, "finished_at": None},
}
TASK_LOCK = threading.Lock()

app = FastAPI(title="Terroir Hunter API")

# Enable CORS for frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _set_task(task: str, **updates):
    with TASK_LOCK:
        TASKS[task].update(updates)


def _run_task_wrapper(task: str, func, *args, **kwargs):
    _set_task(task, status="running", error=None, started_at=time.time(), finished_at=None)
    try:
        # Run Algorithm
        result = func(*args, **kwargs)
        
        # Save Outputs
        if task == "ahp":
            result["map_object"].to_html(str(OUTPUT_SUITABILITY_MAP))
            with open(OUTPUT_AHP_JSON, 'w') as f:
                json.dump(result["json_data"], f)
            global LAST_AHP_IMAGE, LAST_AHP_META
            LAST_AHP_IMAGE = result.get("ee_image")
            LAST_AHP_META = result.get("meta", {})
        elif task == "hybrid":
            result["map_object"].to_html(str(OUTPUT_SIMILARITY_MAP))
            with open(OUTPUT_PHENOLOGY_JSON, 'w') as f:
                json.dump(result["json_data"], f)
                
        _set_task(task, status="completed", finished_at=time.time())
    except Exception as exc: 
        print(f"Task {task} failed: {exc}")
        _set_task(task, status="failed", error=str(exc), finished_at=time.time())


# --- Golden Standard Models & Logic ---

class GoldenStandardBase(BaseModel):
    model_name: str
    crop_type: str
    latitude: float
    longitude: float
    ndvi_curve: List[float]
    lst_curve: List[float]
    tags: List[str] = []

class GoldenStandardCreate(GoldenStandardBase):
    pass

class GoldenStandard(GoldenStandardBase):
    id: str
    created_at: str

class GoldenStandardSummary(BaseModel):
    """Simplified golden standard for UI dropdown/list display"""
    id: str
    model_name: str
    crop_type: str
    latitude: float
    longitude: float

class PhenologyRequest(BaseModel):
    lat: float
    lon: float

# --- Phenology Matching Request/Response Models ---
class PhenologyMatchRequest(BaseModel):
    """Request for matching local phenology against golden standards"""
    lat: float
    lon: float
    golden_standard_id: Optional[str] = None  # Specific standard, or None for all
    search_radius_km: float = 50.0
    sample_points: int = 20
    sample_resolution_m: int = 1000
    top_n: int = 5
    year: int = 2020  # 年份参数，用于获取指定年份的数据

class PhenologyMatchResult(BaseModel):
    """Result of phenology matching against one golden standard"""
    golden_standard_id: str
    golden_standard_name: str
    similarity_score: float  # 0-100
    ndvi_correlation: float  # Pearson correlation
    lst_correlation: float
    slope_similarity: float  # Hybrid-style slope distance similarity (0-100)
    milestones_match: Dict[str, Any]  # Key phenology milestone matches

class PhenologySamplePlot(BaseModel):
    """A sampled nearby plot ranked by similarity to golden standards"""
    lat: float
    lon: float
    similarity_score: float
    matched_standard_id: str
    matched_standard_name: str
    ndvi_correlation: float
    lst_correlation: float
    slope_similarity: float

class PhenologyMatchResponse(BaseModel):
    """Full response for phenology matching"""
    status: str
    data_source: str = "simulated"
    gee_available: bool = False
    gee_message: Optional[str] = None
    local_lat: float
    local_lon: float
    local_ndvi: List[float]
    local_lst: List[float]
    best_golden_ndvi: Optional[List[float]] = None
    best_golden_lst: Optional[List[float]] = None
    matches: List[PhenologyMatchResult]
    sampled_matches: List[PhenologySamplePlot] = []


def _generate_sample_candidates(center_lat: float, center_lon: float, radius_km: float,
                                sample_points: int, sample_resolution_m: int) -> List[Dict[str, float]]:
    """Generate deterministic sample points around center using concentric rings."""
    radius_km = max(0.0, min(radius_km, 200.0))
    sample_points = max(1, min(sample_points, 60))
    spacing_km = max(0.2, min(sample_resolution_m / 1000.0, radius_km))

    points: List[Dict[str, float]] = []
    seen = set()
    golden_angle = math.pi * (3 - math.sqrt(5))

    for i in range(sample_points):
        # Use a deterministic sunflower/spiral distribution so radius choice
        # directly controls spatial extent of sampled points.
        ratio = (i + 1) / sample_points
        angle = i * golden_angle
        r_km = radius_km * math.sqrt(ratio)
        r_km = max(min(r_km, radius_km), min(spacing_km * 0.5, radius_km))

        dlat = (r_km / 111.0) * math.sin(angle)
        cos_lat = max(0.2, math.cos(math.radians(center_lat)))
        dlon = (r_km / (111.0 * cos_lat)) * math.cos(angle)

        lat = center_lat + dlat
        lon = center_lon + dlon
        key = (round(lat, 6), round(lon, 6))
        if key in seen:
            continue
        seen.add(key)
        points.append({"lat": lat, "lon": lon})

    return points


def _get_gee_runtime_status() -> tuple[bool, str]:
    """Check whether server can access Earth Engine at runtime."""
    if not USE_REAL_GEE_DATA or ee is None:
        return False, "Earth Engine 不可用（未安装或初始化失败）"
    try:
        ee.data.getAssetRoots()
        return True, "Earth Engine 可用"
    except Exception as exc:
        err = str(exc)
        if 'Asset "projects/' in err and '/assets" not found' in err:
            project_tip = EE_PROJECT_ID or "未设置（来自默认凭据）"
            return False, f"Earth Engine 项目不存在或未开通资产空间（当前项目: {project_tip}）：{err[:180]}"
        if 'Permission denied' in err or 'not authorized' in err.lower() or 'insufficient' in err.lower():
            return False, f"Earth Engine 未授权或权限不足：{err[:180]}"
        return False, f"Earth Engine 网络不可达或运行异常：{err[:180]}"

# ==========================================
# Geographic Feature Estimation Functions
# ==========================================

def _estimate_elevation(lat: float, lon: float) -> float:
    """
    Estimate elevation based on lat/lon using simplified heuristics for China.
    Real implementation should query DEM (Digital Elevation Model) via GEE.
    
    Heuristics for China (simplified):
    - Tibetan Plateau (西藏/青海): lon < 100, lat 28-35 → 3000-4500m
    - Loess Plateau (黄土高原): lon 105-112, lat 34-40 → 800-1500m
    - Eastern plains (东部平原): lon > 115 → 0-200m
    - Sichuan Basin (四川盆地): lon 103-108, lat 28-32 → 300-600m
    
    For regions outside China, return a default low elevation.
    """
    # 处理中国境外地区（经度<70或>140，或纬度<18）
    if lon < 70 or lon > 140 or lat < 18 or lat > 55:
        return 100.0  # 默认低海拔
    
    # Tibetan Plateau
    if lon < 100 and 28 <= lat <= 35:
        return 3000 + (35 - lat) * 100  # Higher in north
    # Loess Plateau (洛川在这里)
    elif 105 <= lon <= 112 and 34 <= lat <= 40:
        return 800 + (lat - 34) * 50  # 洛川约海拔~1100m
    # Western mountains
    elif lon < 105:
        return 1500 + (105 - lon) * 100
    # Eastern plains
    elif lon > 115:
        return max(0, 200 - (lon - 115) * 20)
    # Central China
    else:
        return 500 + abs(lat - 32) * 30
        
def _estimate_continentality(lat: float, lon: float) -> float:
    """
    Estimate continentality (0-1 scale) - 大陆性气候程度
    0 = oceanic climate (海洋性), 1 = continental climate (大陆性)
    
    Based on distance from coast:
    - Eastern coast (lon > 120): 0.2-0.4 (oceanic)
    - Central China (105 < lon < 120): 0.5-0.7 (transitional)
    - Western interior (lon < 105): 0.7-1.0 (continental)
    
    For regions outside China, use generalized rules:
    - Western Europe (lon < 20, lat 40-55): 0.2-0.4 (oceanic, Atlantic influence)
    - Central Asia (lon 60-80): 0.8-0.9 (strong continental)
    - Eastern Siberia (lon 120-150, lat > 45): 0.7-0.9 (continental)
    """
    # 西欧（大西洋沿岸）：海洋性气候
    if lon < 20 and 40 <= lat <= 55:
        return 0.3  # 波尔多、巴黎等
    
    # 地中海沿岸
    elif 0 <= lon <= 20 and 35 <= lat <= 45:
        return 0.4  # 地中海气候
    
    # 北美东海岸
    elif -90 <= lon <= -70 and 35 <= lat <= 50:
        return 0.4  # 海洋性影响
    
    # 北美西海岸
    elif -130 <= lon <= -110 and 30 <= lat <= 50:
        return 0.3  # 太平洋海洋性
    
    # 中亚内陆（强大陆性）
    elif 60 <= lon <= 90 and 35 <= lat <= 50:
        return 0.9  # 中亚、哈萨克斯坦等
    
    # 中国境内（原有逻辑）
    if 70 <= lon <= 140 and 18 <= lat <= 55:
        if lon > 120:
            return 0.3  # 东部沿海，海洋性
        elif lon > 115:
            return 0.5  # 中东部，过渡带
        elif lon > 105:
            return 0.7  # 中西部，大陆性
        else:
            return 0.9  # 西部内陆，强大陆性
    
    # 默认：中等大陆性（通用地区）
    return 0.6

# ==========================================
# Real GEE Data Fetching Functions
# ==========================================

def _fetch_gee_ndvi_series(lat: float, lon: float, year: int = 2020, buffer_m: float = 500) -> List[float]:
    """
    Fetch real MODIS NDVI time series from Google Earth Engine.
    
    Args:
        lat: Latitude
        lon: Longitude
        year: Year for data (default: 2020)
        buffer_m: Buffer radius in meters around the point (default: 500m)
    
    Returns:
        List of 365 NDVI values (one per day), interpolated from 16-day MODIS data
    """
    if not USE_REAL_GEE_DATA or ee is None:
        raise RuntimeError("Earth Engine not available")
    
    try:
        from datetime import datetime
        
        # Create point geometry with buffer
        point = ee.Geometry.Point([lon, lat])
        geometry = point.buffer(buffer_m)
        
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        
        # Fetch MODIS NDVI (MOD13Q1 - 16-day, 250m resolution)
        col = ee.ImageCollection('MODIS/006/MOD13Q1') \
            .filterDate(start, end) \
            .select('NDVI') \
            .filterBounds(geometry)
        
        # Extract mean NDVI for each image
        def add_ndvi_property(img):
            ndvi_mean = img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=250,
                bestEffort=True
            ).get('NDVI')
            return img.set('ndvi_mean', ndvi_mean)
        
        col_with_ndvi = col.map(add_ndvi_property)
        
        # Get dates and values
        dates = col_with_ndvi.aggregate_array('system:time_start').getInfo()
        values = col_with_ndvi.aggregate_array('ndvi_mean').getInfo()
        
        if not dates or not values or len(dates) == 0:
            print(f"Warning: No MODIS data for {lat}, {lon} in {year}, using simulation")
            return None
        
        # Convert to Day of Year and clean data
        doys = []
        clean_values = []
        
        for d, v in zip(dates, values):
            if isinstance(d, (int, float)) and d is not None:
                try:
                    doy = datetime.utcfromtimestamp(d/1000).timetuple().tm_yday
                    if v is not None:
                        clean_values.append(float(v) * 0.0001)  # MODIS NDVI scale factor
                        doys.append(doy)
                except:
                    pass
        
        if len([v for v in clean_values if not np.isnan(v)]) < 3:
            print(f"Warning: Insufficient valid MODIS data points, using simulation")
            return None
        
        # Interpolate to 365 days
        x = np.array(doys)
        y = np.array(clean_values)
        valid_idx = ~np.isnan(y)
        
        if valid_idx.sum() < 3:
            return None
        
        # Use interpolation to fill 365 days
        if interp1d is not None:
            f = interp1d(x[valid_idx], y[valid_idx], kind='linear', 
                        fill_value='extrapolate', bounds_error=False)
            full_curve = f(np.arange(1, 366))
        else:
            # Simple fallback interpolation
            full_curve = np.interp(np.arange(1, 366), x[valid_idx], y[valid_idx])
        
        # Apply Savitzky-Golay smoothing
        if savgol_filter is not None:
            try:
                full_curve = savgol_filter(full_curve, window_length=31, polyorder=3)
            except:
                pass
        
        return full_curve.tolist()
        
    except Exception as e:
        print(f"Error fetching GEE NDVI data: {e}")
        return None

def _fetch_gee_lst_series(lat: float, lon: float, year: int = 2020, buffer_m: float = 500) -> List[float]:
    """
    Fetch real MODIS Land Surface Temperature time series from Google Earth Engine.
    
    Args:
        lat: Latitude
        lon: Longitude
        year: Year for data (default: 2020)
        buffer_m: Buffer radius in meters around the point
    
    Returns:
        List of 365 LST values (one per day), interpolated from 8-day MODIS data
    """
    if not USE_REAL_GEE_DATA or ee is None:
        raise RuntimeError("Earth Engine not available")
    
    try:
        from datetime import datetime
        
        # Create point geometry with buffer
        point = ee.Geometry.Point([lon, lat])
        geometry = point.buffer(buffer_m)
        
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        
        # Fetch MODIS LST (MOD11A2 - 8-day, 1km resolution)
        col = ee.ImageCollection('MODIS/006/MOD11A2') \
            .filterDate(start, end) \
            .select('LST_Day_1km') \
            .filterBounds(geometry)
        
        # Extract mean LST for each image
        def add_lst_property(img):
            lst_mean = img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=1000,
                bestEffort=True
            ).get('LST_Day_1km')
            return img.set('lst_mean', lst_mean)
        
        col_with_lst = col.map(add_lst_property)
        
        # Get dates and values
        dates = col_with_lst.aggregate_array('system:time_start').getInfo()
        values = col_with_lst.aggregate_array('lst_mean').getInfo()
        
        if not dates or not values or len(dates) == 0:
            print(f"Warning: No MODIS LST data for {lat}, {lon} in {year}, using simulation")
            return None
        
        # Convert to Day of Year and clean data
        doys = []
        clean_values = []
        
        for d, v in zip(dates, values):
            if isinstance(d, (int, float)) and d is not None:
                try:
                    doy = datetime.utcfromtimestamp(d/1000).timetuple().tm_yday
                    if v is not None:
                        # MODIS LST scale factor: 0.02, offset: convert Kelvin to Celsius
                        celsius = float(v) * 0.02 - 273.15
                        clean_values.append(celsius)
                        doys.append(doy)
                except:
                    pass
        
        if len([v for v in clean_values if not np.isnan(v)]) < 3:
            print(f"Warning: Insufficient valid MODIS LST data points, using simulation")
            return None
        
        # Interpolate to 365 days
        x = np.array(doys)
        y = np.array(clean_values)
        valid_idx = ~np.isnan(y)
        
        if valid_idx.sum() < 3:
            return None
        
        # Use interpolation to fill 365 days
        if interp1d is not None:
            f = interp1d(x[valid_idx], y[valid_idx], kind='linear', 
                        fill_value='extrapolate', bounds_error=False)
            full_curve = f(np.arange(1, 366))
        else:
            # Simple fallback interpolation
            full_curve = np.interp(np.arange(1, 366), x[valid_idx], y[valid_idx])
        
        # Apply Savitzky-Golay smoothing
        if savgol_filter is not None:
            try:
                full_curve = savgol_filter(full_curve, window_length=31, polyorder=3)
            except:
                pass
        
        return full_curve.tolist()
        
    except Exception as e:
        print(f"Error fetching GEE LST data: {e}")
        return None

# ==========================================
# Unified Data Fetching Function (Real or Simulated)
# ==========================================

def _get_curve(lat: float, lon: float, curve_type: str = "ndvi", 
               year: int = 2020, use_real_data: bool = True,
               strict_real: bool = False) -> List[float]:
    """
    Get phenology curve from GEE.
    When strict_real=True, real data is mandatory and any failure raises RuntimeError.
    When strict_real=False, fallback to simulation is allowed.
    
    Args:
        lat: Latitude
        lon: Longitude
        curve_type: "ndvi" or "lst"
        year: Year for real data (default: 2020)
        use_real_data: Whether to attempt fetching real data (default: True)
        strict_real: Whether to forbid simulation fallback (default: False)
    
    Returns:
        List of 365 daily values
    """
    if strict_real and (not use_real_data or not USE_REAL_GEE_DATA):
        raise RuntimeError("Earth Engine 不可用，无法获取真实物候数据")

    # Try real GEE data first
    if use_real_data and USE_REAL_GEE_DATA:
        try:
            if curve_type == "ndvi":
                real_data = _fetch_gee_ndvi_series(lat, lon, year)
            elif curve_type == "lst":
                real_data = _fetch_gee_lst_series(lat, lon, year)
            else:
                real_data = None
            
            if real_data is not None:
                print(f"✓ Using real GEE {curve_type.upper()} data for ({lat}, {lon})")
                return real_data
            if strict_real:
                raise RuntimeError(f"GEE 未返回有效 {curve_type.upper()} 数据")
        except Exception as e:
            if strict_real:
                raise RuntimeError(f"GEE {curve_type.upper()} 数据获取失败: {e}")
            print(f"GEE data fetch failed: {e}, falling back to simulation")

    if strict_real:
        raise RuntimeError("Earth Engine 不可用，无法获取真实物候数据")
    
    # Fallback to simulation
    print(f"→ Using simulated {curve_type.upper()} data for ({lat}, {lon})")
    return _simulate_curve(lat, curve_type, lon)

# ==========================================
# Simulation Function (Fallback)
# ==========================================

def _simulate_curve(lat: float, curve_type: str = "ndvi", lon: float = 109.4, elevation: float = None) -> List[float]:
    """
    Simulate a 365-day phenology curve based on latitude, longitude, and elevation.
    This mimics fetching Sentinel-2/MODIS time series and smoothing it.
    
    Improvements:
    - Latitude: Controls base phenology timing (北半球夏季vs南半球夏季)
    - Longitude: Affects continentality (大陆性气候延迟峰值)
    - Elevation: Higher elevation delays peak day (海拔每升高100m，峰值延迟~2天)
    
    Args:
        lat: Latitude (-90 to 90)
        curve_type: "ndvi" or "lst"
        lon: Longitude (default: 109.4, 洛川经度)
        elevation: Elevation in meters (if None, will be estimated from lat/lon)
    """
    days = np.arange(365)
    is_north = lat >= 0
    
    # Auto-estimate elevation if not provided
    if elevation is None:
        elevation = _estimate_elevation(lat, lon)
    
    # Get continentality factor (大陆性因子)
    continentality = _estimate_continentality(lat, lon)
    
    # 1️⃣ Base peak day from latitude (纬度影响)
    # 北半球夏季在7月（Day 200），但随纬度调整：
    # - 低纬度（20°N）: 峰值早（5月，Day 140）
    # - 中纬度（35°N）: 峰值标准（7月，Day 200）
    # - 高纬度（50°N）: 峰值晚（8月，Day 220）
    if is_north:
        base_peak_day = 200 + (abs(lat) - 35) * 0.8  # 纬度每偏离35°，峰值移动0.8天
    else:
        base_peak_day = 20
    
    # 2️⃣ Elevation effect: +1.5 days per 100m elevation
    # 洛川海拔~1100m → +16天，其他地区按比例
    elevation_delay = elevation / 66.7  # 海拔每升高67m，峰值延迟1天
    
    # 3️⃣ Continentality effect: 大陆性气候使生长季延迟和压缩
    # continentality = 0.3-0.9 (从 _estimate_continentality 获取)
    continentality_delay = continentality * 15  # 强大陆性气候最多延迟13.5天
    
    # 4️⃣ Latitude-based season length variation
    # 高纬度地区生长季短（窄峰），低纬度地区长（宽峰）
    lat_factor = min(abs(lat) / 50.0, 1.0)  # 纬度因子 (0-1)
    width_base = 60 if curve_type == "ndvi" else 90
    # 大陆性气候也会使生长季变短（春秋短暂）
    width = width_base * (1.4 - lat_factor * 0.3 - continentality * 0.2)
    
    # 最终峰值日 = 基准 + 海拔延迟 + 大陆性延迟
    peak_day = base_peak_day + elevation_delay + continentality_delay
    peak_day = peak_day % 365  # 确保在0-365范围内
    
    # 5️⃣ Base curve shape (Gaussian-like)
    curve = np.exp(-((days - peak_day) ** 2) / (2 * width ** 2))
    
    if not is_north and base_peak_day < 50:
        # Handle wrapping for Southern hemisphere summer
        curve += np.exp(-((days - (peak_day + 365)) ** 2) / (2 * width ** 2))
    
    # 6️⃣ Scale and Offset with geographic variation
    if curve_type == "ndvi":
        # NDVI: 基础值随海拔变化（高海拔植被稀疏、生长受限）
        base_val = 0.25 - (elevation / 4000.0) * 0.15  # 海拔3000m → 基础值降至0.14
        # 振幅随纬度变化（中纬度（35-40°）最高，极地和赤道较低）
        optimal_lat = 40.0  # 温带最优纬度
        lat_amplitude_factor = 1.0 - abs(abs(lat) - optimal_lat) / 50.0
        amplitude = 0.6 * max(0.5, lat_amplitude_factor)
        noise_level = 0.02 + continentality * 0.01  # 大陆性气候波动更大
    else:
        # LST: 温度范围随纬度变化
        base_val = 5.0 + max(0, 40 - abs(lat)) * 0.3  # 低纬度基础温度更高
        amplitude = 30.0 - abs(lat) * 0.2  # 高纬度温差更大
        noise_level = 1.5 + continentality * 0.5
        
    s_curve = base_val + curve * amplitude
    
    # Add random noise
    noise = np.random.normal(0, noise_level, 365)
    raw_curve = s_curve + noise
    
    # Apply Savitzky-Golay Filter (Smoothing)
    if savgol_filter:
        try:
            # window_length must be odd, polyorder must be less than window_length
            smoothed_curve = savgol_filter(raw_curve, window_length=31, polyorder=3)
            return smoothed_curve.tolist()
        except Exception as e:
            print(f"Savgol filter failed: {e}")
            return raw_curve.tolist()
    else:
        # Simple moving average fallback
        kernel_size = 15
        return np.convolve(raw_curve, np.ones(kernel_size)/kernel_size, mode='same').tolist()

def _get_phenology_milestones(ndvi_curve: List[float]):
    """Extract key phenological dates (Greenup, Maturity, Senescence)"""
    arr = np.array(ndvi_curve)
    
    if find_peaks:
        peaks, _ = find_peaks(arr, distance=150) # Assuming one major crop season
        valleys, _ = find_peaks(-arr, distance=150)
    else:
        peaks = [np.argmax(arr)]
        valleys = [np.argmin(arr)]
        
    return {
        "peaks": [int(p) for p in peaks],
        "valleys": [int(v) for v in valleys],
        "max_value": float(np.max(arr)),
        "min_value": float(np.min(arr))
    }

# --- API Endpoints for Golden Standards ---

@app.post("/api/extract-phenology", response_model=Dict[str, Any])
def extract_phenology(req: PhenologyRequest):
    """
    Interface 1: Extract Historical Phenology Curve
    仅使用真实 GEE 数据进行提取；若不可用则直接报错。
    """
    try:
        gee_available, gee_message = _get_gee_runtime_status()
        if not gee_available:
            raise HTTPException(status_code=503, detail=f"真实数据不可用：{gee_message}")

        # Fetch real data from GEE only
        ndvi = _get_curve(req.lat, req.lon, "ndvi", year=2020, use_real_data=True, strict_real=True)
        lst = _get_curve(req.lat, req.lon, "lst", year=2020, use_real_data=True, strict_real=True)
        
        milestones = _get_phenology_milestones(ndvi)
        
        data_source = "real_gee"
        
        return {
            "status": "success",
            "lat": req.lat,
            "lon": req.lon,
            "ndvi_curve": ndvi,
            "lst_curve": lst,
            "milestones": milestones,
            "data_source": data_source,
            "gee_available": gee_available,
            "gee_message": gee_message,
            "message": "Phenology extracted using real GEE data & Savitzky-Golay filter"
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/golden-standards", response_model=List[GoldenStandard])
def get_golden_standards():
    """Interface 3: Get all saved Golden Standards"""
    if not GOLDEN_STANDARDS_FILE.exists():
        return []
        
    try:
        with open(GOLDEN_STANDARDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

            if not isinstance(data, list):
                return []

            normalized_models = []
            for item in data:
                if not isinstance(item, dict):
                    continue

                normalized = dict(item)
                normalized["id"] = item.get("id") or item.get("model_id")
                normalized["created_at"] = item.get("created_at") or datetime.datetime.now().isoformat()

                if normalized.get("id") is None:
                    continue

                try:
                    normalized_models.append(GoldenStandard(**normalized))
                except Exception:
                    continue

            return normalized_models
    except json.JSONDecodeError:
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load standards: {str(e)}")


@app.post("/api/golden-standards", response_model=Dict[str, Any])
def save_golden_standard(standard: GoldenStandardCreate):
    """Interface 2: Save Golden Standard Model"""
    try:
        # Load existing
        current_standards = []
        if GOLDEN_STANDARDS_FILE.exists():
            with open(GOLDEN_STANDARDS_FILE, "r", encoding="utf-8") as f:
                try:
                    current_standards = json.load(f)
                except json.JSONDecodeError:
                    current_standards = []

        # Create new entry
        new_entry = standard.dict()
        new_id = str(uuid.uuid4())
        new_entry["id"] = new_id
        new_entry["created_at"] = datetime.datetime.now().isoformat()
        
        current_standards.append(new_entry)
        
        # Save back
        with open(GOLDEN_STANDARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(current_standards, f, indent=2, ensure_ascii=False)
            
        return {"status": "success", "id": new_id, "message": "Golden standard saved successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save standard: {str(e)}")


class GoldenStandardRename(BaseModel):
    new_name: str

@app.post("/api/golden-standards/{model_id}/rename", response_model=Dict[str, Any])
def rename_golden_standard(model_id: str, rename_request: GoldenStandardRename = Body(...)):
    """Interface: Rename Golden Standard Model"""
    try:
        normalized_name = (rename_request.new_name or "").strip()
        if not normalized_name:
            raise HTTPException(status_code=400, detail="new_name cannot be empty")

        if not GOLDEN_STANDARDS_FILE.exists():
            raise HTTPException(status_code=404, detail="No saved standards found")
        
        # Load existing
        with open(GOLDEN_STANDARDS_FILE, "r", encoding="utf-8") as f:
            try:
                current_standards = json.load(f)
            except json.JSONDecodeError:
                raise HTTPException(status_code=500, detail="Failed to read standards file")
        
        # Find and update
        model_found = False
        for model in current_standards:
            current_id = model.get("id") or model.get("model_id")
            if current_id == model_id:
                model["model_name"] = normalized_name
                model_found = True
                break
        
        if not model_found:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
        
        # Save back
        with open(GOLDEN_STANDARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(current_standards, f, indent=2, ensure_ascii=False)
            
        return {"status": "success", "message": "Golden standard renamed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename standard: {str(e)}")


@app.delete("/api/golden-standards/{model_id}", response_model=Dict[str, Any])
def delete_golden_standard(model_id: str):
    """Delete a saved Golden Standard Model"""
    try:
        if not GOLDEN_STANDARDS_FILE.exists():
            raise HTTPException(status_code=404, detail="No saved standards found")
        
        # Load existing
        with open(GOLDEN_STANDARDS_FILE, "r", encoding="utf-8") as f:
            try:
                current_standards = json.load(f)
            except json.JSONDecodeError:
                raise HTTPException(status_code=500, detail="Failed to read standards file")
        
        # Find and remove the model
        original_count = len(current_standards)
        current_standards = [
            m for m in current_standards
            if (m.get("id") or m.get("model_id")) != model_id
        ]
        
        if len(current_standards) == original_count:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
        
        # Save back
        with open(GOLDEN_STANDARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(current_standards, f, indent=2, ensure_ascii=False)
            
        return {"status": "success", "message": "Golden standard deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete standard: {str(e)}")


# --- Matching & Comparison ---

@app.get("/api/golden-standards-list", response_model=List[GoldenStandardSummary])
def get_golden_standards_list():
    """
    Interface 4A: Get simplified list of all golden standards for frontend dropdown.
    Returns only essential fields (id, name, crop_type, location).
    """
    if not GOLDEN_STANDARDS_FILE.exists():
        return []
    
    try:
        with open(GOLDEN_STANDARDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []

            summaries = []
            for item in data:
                if not isinstance(item, dict):
                    continue

                model_id = item.get("id") or item.get("model_id")
                if model_id is None:
                    continue

                try:
                    summaries.append(GoldenStandardSummary(**{
                        "id": model_id,
                        "model_name": item["model_name"],
                        "crop_type": item["crop_type"],
                        "latitude": item["latitude"],
                        "longitude": item["longitude"]
                    }))
                except Exception:
                    continue

            return summaries
    except json.JSONDecodeError:
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load standards list: {str(e)}")


def _clean_curve_for_mica(curve: np.ndarray) -> np.ndarray:
    arr = np.array(curve, dtype=float)
    valid = ~np.isnan(arr)
    if valid.sum() < 3:
        return arr
    x = np.arange(arr.size)
    arr[~valid] = np.interp(x[~valid], x[valid], arr[valid])
    return arr


def _extract_mica_landmarks(curve: np.ndarray) -> Dict[str, int]:
    arr = _clean_curve_for_mica(curve)
    smoothed = savgol_filter(arr, window_length=31, polyorder=3) if savgol_filter is not None else arr

    d1 = np.gradient(smoothed)
    d2 = np.gradient(d1)
    d3 = np.gradient(d2)

    if find_peaks is not None:
        up, _ = find_peaks(d3[:180], height=0.0001, distance=20)
        down, _ = find_peaks(-d3[180:], height=0.0001, distance=20)
        down = down + 180
    else:
        up, down = np.array([]), np.array([])

    if len(up) > 0 and len(down) > 0:
        marks = {
            "Greenup": int(up[0]),
            "Maturity": int(up[-1]),
            "Senescence": int(down[0]),
            "Dormancy": int(down[-1])
        }
    else:
        marks = {"Greenup": 100, "Maturity": 150, "Senescence": 260, "Dormancy": 300}

    marks["Greenup"] = max(1, min(364, marks["Greenup"]))
    marks["Maturity"] = max(marks["Greenup"] + 1, min(364, marks["Maturity"]))
    marks["Senescence"] = max(marks["Maturity"] + 1, min(364, marks["Senescence"]))
    marks["Dormancy"] = max(marks["Senescence"] + 1, min(364, marks["Dormancy"]))
    return marks


def _build_mica_inverse_warp(ref_marks: Dict[str, int], tgt_marks: Dict[str, int], n_days: int = 365):
    x_ref = np.array([0, ref_marks["Greenup"], ref_marks["Maturity"], ref_marks["Senescence"], ref_marks["Dormancy"], n_days - 1], dtype=float)
    x_tgt = np.array([0, tgt_marks["Greenup"], tgt_marks["Maturity"], tgt_marks["Senescence"], tgt_marks["Dormancy"], n_days - 1], dtype=float)

    x_ref = np.maximum.accumulate(x_ref)
    x_tgt = np.maximum.accumulate(x_tgt)
    for idx in range(1, len(x_ref)):
        if x_ref[idx] <= x_ref[idx - 1]:
            x_ref[idx] = x_ref[idx - 1] + 1
        if x_tgt[idx] <= x_tgt[idx - 1]:
            x_tgt[idx] = x_tgt[idx - 1] + 1

    x_ref = np.clip(x_ref, 0, n_days - 1)
    x_tgt = np.clip(x_tgt, 0, n_days - 1)

    if PchipInterpolator is not None:
        inverse_warp = PchipInterpolator(x_ref, x_tgt, extrapolate=True)
    elif interp1d is not None:
        inverse_warp = interp1d(x_ref, x_tgt, kind='linear', fill_value='extrapolate')
    else:
        inverse_warp = None

    return inverse_warp, x_ref.tolist(), x_tgt.tolist()


def _apply_mica_alignment(reference_curve: np.ndarray, target_curve: np.ndarray):
    ref = _clean_curve_for_mica(reference_curve)
    tgt = _clean_curve_for_mica(target_curve)

    if ref.size != tgt.size or ref.size < 10:
        return tgt, ref, False, {}, {}

    ref_marks = _extract_mica_landmarks(ref)
    tgt_marks = _extract_mica_landmarks(tgt)

    inverse_warp, ref_anchors, tgt_anchors = _build_mica_inverse_warp(ref_marks, tgt_marks, ref.size)
    if inverse_warp is None:
        return tgt, ref, False, ref_marks, tgt_marks

    ref_time = np.arange(ref.size)
    mapped_tgt_time = np.array(inverse_warp(ref_time), dtype=float)
    mapped_tgt_time = np.clip(mapped_tgt_time, 0, tgt.size - 1)

    if interp1d is not None:
        tgt_interp = interp1d(np.arange(tgt.size), tgt, kind='linear', fill_value='extrapolate')
        aligned_tgt = np.array(tgt_interp(mapped_tgt_time), dtype=float)
    else:
        aligned_tgt = np.interp(mapped_tgt_time, np.arange(tgt.size), tgt)

    meta_ref = {"landmarks": ref_marks, "anchors": ref_anchors}
    meta_tgt = {"landmarks": tgt_marks, "anchors": tgt_anchors}
    return aligned_tgt, ref, True, meta_ref, meta_tgt


def _calculate_similarity(local_ndvi: List[float], local_lst: List[float],
                         golden_ndvi: List[float], golden_lst: List[float]) -> Dict[str, Any]:
    """
    Calculate phenological similarity between local and golden curves.
    Returns: similarity_score (0-100), ndvi_correlation, lst_correlation, milestones_match
    """
    local_ndvi = np.array(local_ndvi)
    local_lst = np.array(local_lst)
    golden_ndvi = np.array(golden_ndvi)
    golden_lst = np.array(golden_lst)

    # Keep raw NDVI for milestone matching (timing difference still meaningful)
    raw_local_ndvi = local_ndvi.copy()
    raw_golden_ndvi = golden_ndvi.copy()

    # 0. MICA (enhanced): landmarks + monotonic warp + aligned-curve comparison
    mica_applied = False
    mica_meta_ref = {}
    mica_meta_tgt = {}
    try:
        aligned_local_ndvi, aligned_golden_ndvi, mica_applied, mica_meta_ref, mica_meta_tgt = _apply_mica_alignment(
            reference_curve=golden_ndvi,
            target_curve=local_ndvi
        )
        if mica_applied:
            local_ndvi = np.array(aligned_local_ndvi)
            golden_ndvi = np.array(aligned_golden_ndvi)
    except Exception as e:
        print(f"MICA alignment skipped: {e}")
    
    # 1. Pearson Correlation for NDVI
    try:
        ndvi_corr = float(np.corrcoef(local_ndvi, golden_ndvi)[0, 1])
        if np.isnan(ndvi_corr):
            ndvi_corr = 0.0
    except:
        ndvi_corr = 0.0
    
    # 2. Pearson Correlation for LST
    try:
        lst_corr = float(np.corrcoef(local_lst, golden_lst)[0, 1])
        if np.isnan(lst_corr):
            lst_corr = 0.0
    except:
        lst_corr = 0.0
    
    # 3. Milestone matching (peak day, valley day)
    try:
        # 更可靠的峰值检测：优先用 find_peaks，失败则使用全局最大/最小值
        if find_peaks:
            # 尝试用较小的 distance 参数检测多个峰值
            local_peaks, _ = find_peaks(raw_local_ndvi, height=np.max(raw_local_ndvi) * 0.5, distance=50)
            golden_peaks, _ = find_peaks(raw_golden_ndvi, height=np.max(raw_golden_ndvi) * 0.5, distance=50)
            local_valleys, _ = find_peaks(-raw_local_ndvi, height=None, distance=50)
            golden_valleys, _ = find_peaks(-raw_golden_ndvi, height=None, distance=50)
            
            # 转换为列表，并检查长度
            local_peaks = list(local_peaks) if len(local_peaks) > 0 else []
            golden_peaks = list(golden_peaks) if len(golden_peaks) > 0 else []
            local_valleys = list(local_valleys) if len(local_valleys) > 0 else []
            golden_valleys = list(golden_valleys) if len(golden_valleys) > 0 else []
        else:
            local_peaks = []
            golden_peaks = []
            local_valleys = []
            golden_valleys = []
        
        # 如果 find_peaks 没找到，使用全局最大/最小值
        if len(local_peaks) == 0:
            local_peaks = [int(np.argmax(raw_local_ndvi))]
        if len(golden_peaks) == 0:
            golden_peaks = [int(np.argmax(raw_golden_ndvi))]
        if len(local_valleys) == 0:
            local_valleys = [int(np.argmin(raw_local_ndvi))]
        if len(golden_valleys) == 0:
            golden_valleys = [int(np.argmin(raw_golden_ndvi))]
        
        # 使用第一个（最高）的峰值和第一个（最低）的谷值
        local_peak_day = int(local_peaks[0])
        golden_peak_day = int(golden_peaks[0])
        local_valley_day = int(local_valleys[0])
        golden_valley_day = int(golden_valleys[0])
        
        # 计算里程碑的时间差
        peak_diff = abs(local_peak_day - golden_peak_day)
        valley_diff = abs(local_valley_day - golden_valley_day)
        
        # 转换为相似度评分（差异小 -> 高分）
        peak_match = max(0, 100 - peak_diff * 0.5)
        valley_match = max(0, 100 - valley_diff * 0.5)
        
        milestones_match = {
            "local_peak_day": local_peak_day,
            "golden_peak_day": golden_peak_day,
            "peak_match_score": peak_match,
            "local_valley_day": local_valley_day,
            "golden_valley_day": golden_valley_day,
            "valley_match_score": valley_match,
            "mica_alignment_applied": mica_applied,
            "mica_reference": mica_meta_ref,
            "mica_target": mica_meta_tgt
        }
    except Exception as e:
        print(f"Error calculating milestones: {e}")
        milestones_match = {
            "local_peak_day": None,
            "golden_peak_day": None,
            "peak_match_score": 0,
            "local_valley_day": None,
            "golden_valley_day": None,
            "valley_match_score": 0,
            "mica_alignment_applied": mica_applied,
            "mica_reference": mica_meta_ref,
            "mica_target": mica_meta_tgt
        }
    
    # 4. Hybrid-style slope distance similarity (NDVI shape consistency)
    # Formula aligned with Hybrid script: similarity = 100 * exp(-k * dist)
    # dist = mean(|slope_local - slope_golden|)
    # Use a stronger decay (k=100) to avoid overly optimistic scores on visibly different curves.
    try:
        slope_dist = float(np.mean(np.abs(np.gradient(local_ndvi) - np.gradient(golden_ndvi))))
        slope_similarity = float(100 * np.exp(-100 * slope_dist))
        slope_similarity = min(100.0, max(0.0, slope_similarity))
    except Exception:
        slope_similarity = 0.0

    # 5. Overall similarity score (weighted combination)
    # Weights (sum=1.0):
    # - NDVI correlation: 30%
    # - LST correlation: 20%
    # - Milestones: 20%
    # - Slope similarity (Hybrid): 30%
    ndvi_weight = 0.30
    lst_weight = 0.20
    milestone_weight = 0.20
    slope_weight = 0.30
    
    avg_milestone = (milestones_match.get("peak_match_score", 0) + milestones_match.get("valley_match_score", 0)) / 2
    
    # Convert correlations to [0, 100] with stricter interpretation:
    # corr <= 0 -> 0 score, corr = 1 -> 100 score
    # This avoids inflating moderate correlation (e.g. corr=0.65) to 82.5.
    ndvi_score = max(0.0, ndvi_corr) * 100
    lst_score = max(0.0, lst_corr) * 100
    milestone_score = avg_milestone
    
    overall_score = (
        ndvi_weight * ndvi_score
        + lst_weight * lst_score
        + milestone_weight * milestone_score
        + slope_weight * slope_similarity
    )
    overall_score = min(100, max(0, overall_score))
    
    return {
        "similarity_score": round(overall_score, 2),
        "ndvi_correlation": round(ndvi_corr, 3),
        "lst_correlation": round(lst_corr, 3),
        "slope_similarity": round(slope_similarity, 2),
        "milestones_match": milestones_match
    }


@app.post("/api/phenology-matching", response_model=PhenologyMatchResponse)
def phenology_matching(req: PhenologyMatchRequest):
    """
    Interface 4B: Match local phenology against golden standards.
    Performs one-to-many comparison: local location vs all/specific golden standards.
    使用指定年份的数据进行对比
    """
    try:
        gee_available, gee_message = _get_gee_runtime_status()
        if not gee_available:
            raise HTTPException(status_code=503, detail=f"真实数据不可用：{gee_message}")

        # 1. Extract local phenology - real GEE data only
        local_ndvi = _get_curve(req.lat, req.lon, "ndvi", year=req.year, use_real_data=True, strict_real=True)
        local_lst = _get_curve(req.lat, req.lon, "lst", year=req.year, use_real_data=True, strict_real=True)
        
        # 2. Load golden standards
        if not GOLDEN_STANDARDS_FILE.exists():
            raise HTTPException(status_code=404, detail="No golden standards available")
        
        with open(GOLDEN_STANDARDS_FILE, "r", encoding="utf-8") as f:
            try:
                all_standards = json.load(f)
            except json.JSONDecodeError:
                raise HTTPException(status_code=500, detail="Failed to read standards")
        
        # 3. Filter by specific standard if requested
        if req.golden_standard_id:
            all_standards = [s for s in all_standards if (s.get("id") or s.get("model_id")) == req.golden_standard_id]
            if not all_standards:
                raise HTTPException(status_code=404, detail=f"Golden standard {req.golden_standard_id} not found")
        
        # 4. Compare against each standard
        matches = []
        for standard in all_standards:
            standard_id = standard.get("id") or standard.get("model_id")
            if not standard_id:
                continue
            sim_result = _calculate_similarity(
                local_ndvi, local_lst,
                standard["ndvi_curve"], standard["lst_curve"]
            )
            
            match = PhenologyMatchResult(
                golden_standard_id=standard_id,
                golden_standard_name=standard.get("model_name", "未命名模型"),
                similarity_score=sim_result["similarity_score"],
                ndvi_correlation=sim_result["ndvi_correlation"],
                lst_correlation=sim_result["lst_correlation"],
                slope_similarity=sim_result["slope_similarity"],
                milestones_match=sim_result["milestones_match"]
            )
            matches.append(match)
        
        # 5. Sort by similarity score (highest first)
        matches.sort(key=lambda x: x.similarity_score, reverse=True)

        best_golden_ndvi = None
        best_golden_lst = None
        if matches:
            best_id = matches[0].golden_standard_id
            best_standard = next((s for s in all_standards if (s.get("id") or s.get("model_id")) == best_id), None)
            if best_standard:
                best_golden_ndvi = best_standard.get("ndvi_curve")
                best_golden_lst = best_standard.get("lst_curve")

        # 6. Sample nearby plots and rank by similarity
        sample_candidates = _generate_sample_candidates(
            center_lat=req.lat,
            center_lon=req.lon,
            radius_km=req.search_radius_km,
            sample_points=req.sample_points,
            sample_resolution_m=req.sample_resolution_m,
        )

        sampled_matches: List[PhenologySamplePlot] = []
        for pt in sample_candidates:
            # 采样点用指定年份的数据（真实数据强制模式）
            try:
                candidate_ndvi = _get_curve(pt["lat"], pt["lon"], "ndvi", year=req.year, use_real_data=True, strict_real=True)
                candidate_lst = _get_curve(pt["lat"], pt["lon"], "lst", year=req.year, use_real_data=True, strict_real=True)
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"采样点真实数据获取失败（{pt['lat']:.4f}, {pt['lon']:.4f}）：{exc}")

            best_candidate = None
            for standard in all_standards:
                standard_id = standard.get("id") or standard.get("model_id")
                if not standard_id:
                    continue
                try:
                    sim_result = _calculate_similarity(
                        candidate_ndvi,
                        candidate_lst,
                        standard["ndvi_curve"],
                        standard["lst_curve"]
                    )
                except Exception:
                    continue

                if (best_candidate is None) or (sim_result["similarity_score"] > best_candidate["similarity_score"]):
                    best_candidate = {
                        "standard_id": standard_id,
                        "standard_name": standard.get("model_name", "未命名模型"),
                        "similarity_score": sim_result["similarity_score"],
                        "ndvi_correlation": sim_result["ndvi_correlation"],
                        "lst_correlation": sim_result["lst_correlation"],
                        "slope_similarity": sim_result["slope_similarity"],
                    }

            if best_candidate is None:
                continue

            sampled_matches.append(
                PhenologySamplePlot(
                    lat=pt["lat"],
                    lon=pt["lon"],
                    similarity_score=best_candidate["similarity_score"],
                    matched_standard_id=best_candidate["standard_id"],
                    matched_standard_name=best_candidate["standard_name"],
                    ndvi_correlation=best_candidate["ndvi_correlation"],
                    lst_correlation=best_candidate["lst_correlation"],
                    slope_similarity=best_candidate["slope_similarity"],
                )
            )

        sampled_matches.sort(key=lambda x: x.similarity_score, reverse=True)
        sampled_matches = sampled_matches[:max(1, min(req.top_n, 20))]
        
        return PhenologyMatchResponse(
            status="success",
            data_source="real_gee",
            gee_available=gee_available,
            gee_message=gee_message,
            local_lat=req.lat,
            local_lon=req.lon,
            local_ndvi=local_ndvi,
            local_lst=local_lst,
            best_golden_ndvi=best_golden_ndvi,
            best_golden_lst=best_golden_lst,
            matches=matches,
            sampled_matches=sampled_matches
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Matching failed: {str(e)}")


@app.post("/api/run/ahp")
def run_ahp(params: dict = Body(default={})):
    # Params: w_slope, w_elev, w_aspect, w_climate, search_radius
    with TASK_LOCK:
        if TASKS["ahp"]["status"] == "running":
            raise HTTPException(status_code=409, detail="AHP is already running")
    
    # Extract weights if provided, ensuring they are floats
    kwargs = {}
    if "w_slope" in params: kwargs["w_slope"] = float(params["w_slope"])
    if "w_elev" in params: kwargs["w_elev"] = float(params["w_elev"])
    if "w_aspect" in params: kwargs["w_aspect"] = float(params["w_aspect"])
    if "w_climate" in params: kwargs["w_climate"] = float(params["w_climate"])
    if "search_radius" in params: kwargs["search_radius"] = int(params["search_radius"])
    if "center_lat" in params: kwargs["center_lat"] = float(params["center_lat"])
    if "center_lon" in params: kwargs["center_lon"] = float(params["center_lon"])

    thread = threading.Thread(target=_run_task_wrapper, args=("ahp", run_ahp_algorithm), kwargs=kwargs, daemon=True)
    thread.start()
    return {"status": "running"}


@app.post("/api/run/hybrid")
def run_hybrid(params: dict = Body(default={})):
    with TASK_LOCK:
        if TASKS["hybrid"]["status"] == "running":
            raise HTTPException(status_code=409, detail="Hybrid matching is already running")
    
    kwargs = {}
    if "year" in params: kwargs["year"] = int(params["year"])
    if "similarity_threshold" in params: kwargs["similarity_threshold"] = float(params["similarity_threshold"])
    if "target_region" in params: kwargs["target_region"] = params["target_region"]
    if "search_radius" in params: kwargs["search_radius"] = int(params["search_radius"])
            
    thread = threading.Thread(target=_run_task_wrapper, args=("hybrid", run_phenology_algorithm), kwargs=kwargs, daemon=True)
    thread.start()
    return {"status": "running"}


@app.get("/api/status")
def status():
    with TASK_LOCK:
        tasks = {k: dict(v) for k, v in TASKS.items()}
    outputs = {
        "suitability_map": OUTPUT_SUITABILITY_MAP.exists(),
        "similarity_map": OUTPUT_SIMILARITY_MAP.exists(),
        "similarity_csv": OUTPUT_SIMILARITY_CSV.exists(),
        "phenology_png": OUTPUT_PHENOLOGY_PNG.exists(),
    }
    return {"tasks": tasks, "outputs": outputs}


@app.get("/api/output/{name}")
def output(name: str):
    path = ALLOWED_OUTPUTS.get(name)
    if not path:
        raise HTTPException(status_code=404, detail="Output not found")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File is not ready")
    return FileResponse(path)


@app.get("/api/ahp/tiles")
def get_ahp_tiles():
    if LAST_AHP_IMAGE is None:
        raise HTTPException(status_code=404, detail="AHP heatmap not ready")

    vis_params = {
        "min": 30,
        "max": 90,
        "palette": ["green", "yellow", "orange", "red"],
    }
    tile_info = LAST_AHP_IMAGE.visualize(**vis_params).getMapId()
    tile_url = tile_info["tile_fetcher"].url_format

    center_lat = float(LAST_AHP_META.get("center_lat", 35.8))
    center_lon = float(LAST_AHP_META.get("center_lon", 109.4))
    radius_km = float(LAST_AHP_META.get("search_radius_km", 50))

    dlat = radius_km / 111.0
    cos_lat = max(0.2, math.cos(math.radians(center_lat)))
    dlon = radius_km / (111.0 * cos_lat)
    bounds = [[center_lat - dlat, center_lon - dlon], [center_lat + dlat, center_lon + dlon]]

    return {
        "tile_url": tile_url,
        "bounds": bounds,
        "center": {"lat": center_lat, "lon": center_lon},
        "radius_km": radius_km,
    }


@app.get("/api/ahp/class-plots")
def get_ahp_class_plots(
    grade: str = Query(..., pattern="^[SABCD]$"),
    limit: int = Query(120, ge=20, le=600),
):
    if LAST_AHP_IMAGE is None or ee is None:
        raise HTTPException(status_code=404, detail="AHP heatmap not ready")

    center_lat = float(LAST_AHP_META.get("center_lat", 35.8))
    center_lon = float(LAST_AHP_META.get("center_lon", 109.4))
    radius_km = float(LAST_AHP_META.get("search_radius_km", 50))
    roi = ee.Geometry.Point([center_lon, center_lat]).buffer(radius_km * 1000).bounds()

    score_img = LAST_AHP_IMAGE
    if grade == "S":
        class_img = score_img.updateMask(score_img.gt(90))
    elif grade == "A":
        class_img = score_img.updateMask(score_img.gte(80).And(score_img.lte(90)))
    elif grade == "B":
        class_img = score_img.updateMask(score_img.gte(70).And(score_img.lt(80)))
    elif grade == "C":
        class_img = score_img.updateMask(score_img.gte(60).And(score_img.lt(70)))
    else:
        class_img = score_img.updateMask(score_img.lt(60))

    try:
        fc = class_img.sample(
            region=roi,
            scale=500,
            numPixels=limit,
            geometries=True,
            seed=42,
        )
        features = fc.getInfo().get("features", [])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to sample class plots: {exc}")

    points = []
    for item in features:
        geom = item.get("geometry", {})
        coords = geom.get("coordinates", []) if geom else []
        props = item.get("properties", {})
        if not coords or len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        score = props.get("Suitability_Score")
        points.append({
            "lat": lat,
            "lon": lon,
            "score": round(float(score), 2) if score is not None else None,
            "grade": grade,
        })

    return {
        "grade": grade,
        "count": len(points),
        "center": {"lat": center_lat, "lon": center_lon},
        "radius_km": radius_km,
        "points": points,
    }


@app.get("/api/gee-status")
def get_gee_status():
    gee_available, message = _get_gee_runtime_status()
    return {
        "gee_available": gee_available,
        "message": message,
        "project_id": EE_PROJECT_ID,
    }


# Mount static files AFTER API routes to avoid route conflicts
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import os
    import uvicorn
    enable_reload = os.getenv("UVICORN_RELOAD", "0") == "1" and os.name != "nt"
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=enable_reload, app_dir=str(ROOT_DIR / "server"))
