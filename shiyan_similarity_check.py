import ee
import geemap
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter, find_peaks
from scipy.interpolate import interp1d
import os

# 配置 Matplotlib 字体以支持中文
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False # 解决负号显示问题

# ==========================================
# 0. 初始化与配置
# ==========================================
project_id = os.getenv('GCP_PROJECT_ID', 'terrior-hunter')
try:
    ee.Initialize(project=project_id)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=project_id)

# 目标区域中心：十堰市郧阳区白桑关镇杨家河村
TARGET_LON = 110.998020
TARGET_LAT = 32.959540
SEARCH_RADIUS_KM = 10

# 金标准参考中心：陕西洛川
REF_LON = 109.4
REF_LAT = 35.8

print("\n" + "="*60)
print("🍎 富士苹果产区相似性分析系统")
print("="*60)
print(f"对比目标: 十堰市郧阳区杨家河村 ({TARGET_LON}, {TARGET_LAT})")
print(f"参考标准: 陕西洛川 ({REF_LON}, {REF_LAT})")
print("="*60 + "\n")

# ==========================================
# 1. 工具函数库 (AHP & Phenology)
# ==========================================

# --- AHP 重分类函数 ---
def reclassify_slope(img):
    return ee.Image(1).where(img.lt(5), 9).where(img.gte(5).And(img.lt(15)), 8).where(img.gte(15).And(img.lt(25)), 6).where(img.gte(25), 1)

def reclassify_aspect(img):
    return ee.Image(1).where(img.gte(135).And(img.lt(225)), 9).where(img.gte(90).And(img.lt(135)), 7).where(img.gte(225).And(img.lt(270)), 7).where(img.lt(90).Or(img.gte(270)), 3)

def reclassify_elevation(img):
    # 保持原有逻辑，针对高山苹果
    return ee.Image(1).where(img.lt(600), 3).where(img.gte(600).And(img.lt(800)), 6).where(img.gte(800).And(img.lt(1300)), 9).where(img.gte(1300), 5)

def calculate_ahp_score(roi):
    """计算区域内的 AHP 适宜性指数"""
    dem = ee.Image("USGS/SRTMGL1_003").clip(roi)
    climate = ee.Image("WORLDCLIM/V1/BIO").clip(roi)
    temp = climate.select('bio01').multiply(0.1)
    
    slope = ee.Terrain.slope(dem)
    aspect = ee.Terrain.aspect(dem)

    score_slope = reclassify_slope(slope)
    score_aspect = reclassify_aspect(aspect)
    score_dem = reclassify_elevation(dem)
    # 气温适宜度
    score_climate = temp.add(50).divide(100).multiply(8).add(1).clamp(1, 9)

    # 权重 (与 AHP.py 保持一致)
    lsi = score_slope.multiply(0.35) \
        .add(score_dem.multiply(0.25)) \
        .add(score_aspect.multiply(0.20)) \
        .add(score_climate.multiply(0.20))
    
    return lsi.multiply(10).rename('Suitability_Score') # 0-100

# --- 物候特征提取函数 ---
def get_ndvi_series(geometry, year=2020):
    """获取指定几何位置的年度 NDVI 时间序列"""
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    col = ee.ImageCollection('MODIS/006/MOD13Q1').filterDate(start, end).select('NDVI')
    
    def add_ndvi_property(img):
        ndvi_mean = img.reduceRegion(ee.Reducer.mean(), geometry, scale=250, bestEffort=True).get('NDVI')
        return img.set('ndvi_mean', ndvi_mean)
    
    col_with_ndvi = col.map(add_ndvi_property)
    dates = col_with_ndvi.aggregate_array('system:time_start').getInfo()
    values = col_with_ndvi.aggregate_array('ndvi_mean').getInfo()
    
    if not dates or not values: return None
    
    # 清洗和插值
    from datetime import datetime
    doys = []
    clean_values = []
    for d, v in zip(dates, values):
        if d and v:
            doy = datetime.utcfromtimestamp(d/1000).timetuple().tm_yday
            clean_values.append(float(v) * 0.0001)
            doys.append(doy)
            
    if len(clean_values) < 5: return None
    
    x = np.array(doys)
    y = np.array(clean_values)
    
    # 线性插值填充全365天
    f = interp1d(x, y, kind='linear', fill_value='extrapolate')
    return f(np.arange(1, 366))

def extract_landmarks(ndvi_series):
    """提取关键物候点 (平滑 + 导数法)"""
    if ndvi_series is None: return None, None
    # 平滑
    smooth_ndvi = savgol_filter(ndvi_series, window_length=31, polyorder=3)
    
    # 计算导数
    d1 = np.gradient(smooth_ndvi)
    d2 = np.gradient(d1)
    d3 = np.gradient(d2)
    
    # 寻找极值点作为特征
    upward_peaks, _ = find_peaks(d3[:180], height=0.0001, distance=20) 
    downward_peaks, _ = find_peaks(-d3[180:], height=0.0001, distance=20)
    
    # 默认值兜底
    g_up = upward_peaks[0] if len(upward_peaks) > 0 else 100
    g_mat = upward_peaks[-1] if len(upward_peaks) > 0 else 150
    g_sen = downward_peaks[0] + 180 if len(downward_peaks) > 0 else 260
    g_dor = downward_peaks[-1] + 180 if len(downward_peaks) > 0 else 300
    
    landmarks = {
        'Greenup': g_up,
        'Maturity': g_mat,
        'Senescence': g_sen,
        'Dormancy': g_dor
    }
    return smooth_ndvi, landmarks

def calculate_similarity_score(ref_curve, tgt_curve):
    """计算形状相似度 (0-100)"""
    # 简单使用斜率距离
    s1 = np.gradient(ref_curve)
    s2 = np.gradient(tgt_curve)
    dist = np.mean(np.abs(s1 - s2))
    similarity = 100 * np.exp(-10 * dist)
    return similarity

# ==========================================
# 2. 提取参考特征 (Luochuan)
# ==========================================
print("🔄 正在提取金标准产区(洛川)特征...")
ref_point = ee.Geometry.Point([REF_LON, REF_LAT])
try:
    ref_ndvi = get_ndvi_series(ref_point, year=2020)
    ref_smooth, ref_marks = extract_landmarks(ref_ndvi)
    
    if ref_smooth is not None:
        print("   ✅ 参考曲线提取成功")
        print(f"   关键物候点: {ref_marks}")
    else:
        raise ValueError("无法提取参考点数据")
except Exception as e:
    print(f"❌ 提取参考特征失败: {e}")
    exit()

# ==========================================
# 3. 分析目标区域 (Shiyan)
# ==========================================
print(f"\n🔄 正在分析目标区域: 杨家河村 (半径 {SEARCH_RADIUS_KM}km)...")

# 定义目标 ROI
tgt_center = ee.Geometry.Point([TARGET_LON, TARGET_LAT])
tgt_roi = tgt_center.buffer(SEARCH_RADIUS_KM * 1000).bounds()

# 3.1 计算环境适宜性 (AHP)
print("   - 计算 AHP 环境适宜性...")
suitability = calculate_ahp_score(tgt_roi)

# 3.2 采样候选点 (为了速度，过滤得分>50的区域进行采样)
print("   - 正在采样潜在优质地块...")
# 只在适宜性 > 50 的地方采样，减少计算量
potential_areas = suitability.gt(50).selfMask()

# 在 ROI 内随机生成采样点 (限制数量以加快运行)
samples = potential_areas.sample(
    region=tgt_roi,
    scale=500,  # 采样分辨率
    numPixels=30, # 采样点数量
    geometries=True
).getInfo().get('features', [])

print(f"   - 找到 {len(samples)} 个潜在采样点，开始进行物候匹配...")

# 3.3 进行相似度匹配
results = []
for i, f in enumerate(samples):
    geom = ee.Geometry(f['geometry'])
    # 获取 AHP 得分
    props = f.get('properties', {})
    ahp_score = props.get('Suitability_Score', 0)
    
    # 获取 NDVI 曲线
    ndvi_ts = get_ndvi_series(geom, year=2020)
    smooth, marks = extract_landmarks(ndvi_ts)
    
    if smooth is None:
        continue
        
    # 计算相似度 (这里简化了 Hybrid Phenology Matching 中的 Warp 步骤，直接比对形态)
    sim_score = calculate_similarity_score(ref_smooth, smooth)
    
    # 综合得分 (50% 环境分 + 50% 相似分)
    final_score = 0.4 * ahp_score + 0.6 * sim_score
    
    coord = geom.centroid(1).coordinates().getInfo()
    
    results.append({
        'id': i,
        'lon': coord[0],
        'lat': coord[1],
        'ahp_score': ahp_score,
        'pheno_sim': sim_score,
        'final_score': final_score,
        'geometry': geom,
        'smooth': smooth,
        'marks': marks
    })
    if (i+1) % 5 == 0:
        print(f"     已处理 {i+1}/{len(samples)} 个点...")

# ==========================================
# 4. 汇总与输出
# ==========================================
if not results:
    print("\n⚠️ 警告: 未在目标区域找到有效数据点 (可能是云层遮挡或无植被)")
else:
    # 排序
    results.sort(key=lambda x: x['final_score'], reverse=True)
    best_match = results[0]
    
    print("\n" + "="*60)
    print("🏆 分析结果总结")
    print("="*60)
    print(f"目标区域最佳匹配点: 经度 {best_match['lon']:.6f}, 纬度 {best_match['lat']:.6f}")
    print(f"综合匹配得分: {best_match['final_score']:.1f} / 100")
    print(f"  - 环境适宜性 (AHP): {best_match['ahp_score']:.1f} (基于地形/气候)")
    print(f"  - 物候相似度 (NDVI): {best_match['pheno_sim']:.1f} (基于生长曲线)")
    
    # 保存 CSV (排除非标量列)
    df = pd.DataFrame(results).drop(columns=['geometry', 'smooth', 'marks'])
    csv_path = 'shiyan_similarity_results.csv'
    df.to_csv(csv_path, index=False)
    print(f"\n✓ 详细数据已保存至: {csv_path}")

    # ==========================================
    # 5. 结果可视化 (曲线对比)
    # ==========================================
    print("📊 生成曲线对比图...")
    days = np.arange(1, 366)
    tgt_smooth = best_match['smooth']
    tgt_marks = best_match['marks']
    
    plt.figure(figsize=(12, 6))
    
    # 绘制参考曲线 (洛川)
    plt.plot(days, ref_smooth, 'b-', label='金标准产区 (陕西洛川)', linewidth=2)
    plt.fill_between(days, ref_smooth, alpha=0.1, color='blue')
    
    # 绘制目标曲线 (十堰最佳匹配)
    plt.plot(days, tgt_smooth, 'r--', label=f"最佳匹配点 (十堰杨家河) - 相似度: {best_match['pheno_sim']:.1f}%", linewidth=2)
    plt.fill_between(days, tgt_smooth, alpha=0.1, color='red')

    # 绘制关键物候点
    if ref_marks:
        plt.scatter(ref_marks.values(), [ref_smooth[int(i)] for i in ref_marks.values()], 
                   c='blue', marker='o', s=50, label='洛川物候点', zorder=5)
    
    if tgt_marks:
        plt.scatter(tgt_marks.values(), [tgt_smooth[int(i)] for i in tgt_marks.values()], 
                   c='red', marker='x', s=50, label='十堰物候点', zorder=5)

    plt.title(f"富士苹果产区物候曲线对比\n(杨家河村 vs 洛川县)", fontsize=14)
    plt.xlabel("Day of Year (DOY)", fontsize=12)
    plt.ylabel("NDVI (植被指数)", fontsize=12)
    plt.legend(loc='best')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    img_path = 'shiyan_curve_comparison.png'
    plt.savefig(img_path, dpi=150, bbox_inches='tight')
    print(f"✓ 曲线对比图已保存至: {img_path}")

    # 生成地图
    print("🔄 正在生成可视化地图...")
    Map = geemap.Map(center=[TARGET_LAT, TARGET_LON], zoom=12)
    
    # 1. 适宜性底图
    vis_params = {'min': 40, 'max': 90, 'palette': ['green', 'yellow', 'orange', 'red']}
    Map.addLayer(suitability.clip(tgt_roi), vis_params, '环境适宜性 (AHP)')
    
    # 2. 目标中心点
    center_point = ee.Geometry.Point([TARGET_LON, TARGET_LAT])
    Map.addLayer(center_point, {'color': 'blue'}, '查询中心: 杨家河村')
    
    # 3. 最佳匹配点
    best_geom = best_match['geometry']
    Map.addLayer(best_geom, {'color': 'red', 'pointSize': 10}, f"最佳匹配点 (得分:{best_match['final_score']:.1f})")
    
    # 4. Top 5 匹配点
    top_fc = ee.FeatureCollection([ee.Feature(r['geometry'], {'score': r['final_score']}) for r in results[:5]])
    Map.addLayer(top_fc, {'color': 'purple'}, 'Top 5 相似地块')
    
    html_path = 'shiyan_similarity_map.html'
    Map.to_html(html_path)
    print(f"✓ 交互式地图已保存至: {html_path}")

    print("\n建议:")
    if best_match['final_score'] > 80:
        print("✅ 该区域与洛川产区高度相似，极具引种潜力！")
    elif best_match['final_score'] > 60:
        print("⚠️ 该区域具备一定相似性，但存在局部环境差异，建议实地考察。")
    else:
        print("❌ 该区域与洛川产区差异较大 (可能是海拔或气候模式不同)。")
