import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
from scipy.interpolate import interp1d
import ee
import os
import geemap

# ==========================================
# 输出设置
# ==========================================
TOP_N = 10
SIM_THRESHOLD = 60.0
EXPORT_CSV = True
EXPORT_MAP = True
OUTPUT_CSV = 'similar_regions.csv'
OUTPUT_MAP = 'similar_regions_map.html'

# ==========================================
# 1. 数据模拟 (Data Simulation)
# ==========================================
#：
# Reference: 标准的“波尔多”曲线
# Target: 待检测的贫困村曲线（假设它发芽晚了10天，但生长形态高度一致）
def double_logistic(t, params):
    # 双逻辑斯蒂函数模拟作物生长
    # params: [t_start, t_end, rate_growth, rate_decay, base, amp]
    p = params
    growth = 1 / (1 + np.exp(-p[2] * (t - p[0])))
    decay = 1 / (1 + np.exp(p[3] * (t - p[1])))
    return p[4] + p[5] * (growth - (1 - decay)) # 简化的双逻辑斯蒂形态

# 使用 GEE 数据代替模拟数据
# 初始化 Earth Engine（使用与 HAP 相同的项目）
project_id = os.getenv('GCP_PROJECT_ID', 'terrior-hunter')
try:
    ee.Initialize(project=project_id)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=project_id)

# 导入 HAP 模块，获取已计算的适宜性图层和 ROI
import AHP
final = AHP.final_suitability
roi = AHP.roi

print("\n" + "="*60)
print("富士苹果相似产区智能检索系统")
print("="*60)
print("金标准产区: 陕西洛川 (109.4°E, 35.8°N)")
print("搜索范围: 50km 半径周边地区")
print("目标: 找到与洛川生态条件接近的潜在优质地块")
print("="*60 + "\n")

# 找到得分>60 的高分区并向量化，选取面积最大的多边形作为参考区
prime = final.gt(60).selfMask()
# 增加 scale 和 eightConnected 参数，减少要素数量，加快处理
vec = prime.reduceToVectors(
    scale=1000,  # 提高分辨率，减少过度分割
    geometry=roi,
    geometryType='polygon',
    maxPixels=1e13,
    eightConnected=True  # 使用8邻接来简化要素
)
# 添加面积属性到 feature，进行服务器端计算
vec_with_area = vec.map(lambda f: f.set('area', f.geometry().area(maxError=50)))
# 排序并选取面积最大的要素
best_feat = vec_with_area.sort('area', False).first()
if best_feat is None:
    raise RuntimeError('未找到高分区域，请确认 HAP.py 中 final_suitability 是否包含得分>60 的区域。')
best_geom = best_feat.geometry()

# 函数：从 MODIS 获取年内 NDVI 时序（按 MOD13Q1 16-day）
def get_ndvi_series(geometry, year=2020):
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    col = ee.ImageCollection('MODIS/006/MOD13Q1').filterDate(start, end).select('NDVI')
    
    # 为每个影像添加 NDVI 均值作为属性
    def add_ndvi_property(img):
        ndvi_mean = img.reduceRegion(ee.Reducer.mean(), geometry, scale=250, bestEffort=True).get('NDVI')
        return img.set('ndvi_mean', ndvi_mean)
    
    col_with_ndvi = col.map(add_ndvi_property)
    
    # 用 aggregate_array 分别提取时间戳和 NDVI 值
    dates = col_with_ndvi.aggregate_array('system:time_start').getInfo()
    values = col_with_ndvi.aggregate_array('ndvi_mean').getInfo()
    
    if not dates or not values or len(dates) == 0:
        return np.full(365, np.nan)
    
    # 标准化为 DOY 索引长度
    from datetime import datetime
    doys = []
    clean_values = []
    
    for d, v in zip(dates, values):
        if isinstance(d, (int, float)) and d is not None:
            try:
                doy = datetime.utcfromtimestamp(d/1000).timetuple().tm_yday
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
    full = f(np.arange(1, 366))
    return full

# 参考样本：使用最佳高分区的 NDVI 序列
ref_ndvi = get_ndvi_series(best_geom, year=2020)

# 在 ROI 内采样若干点作为候选目标（减少采样点数以加快处理）
sample_pts = final.sample(
    region=roi,
    scale=500,
    numPixels=20,  # 减少采样点数从 50 到 20
    geometries=True
).getInfo().get('features', [])

# 作为后续匹配用的时间轴
days = np.arange(1, 366)

# ==========================================
# 2. 特征提取：寻找“关节” (Landmark Extraction)
# ==========================================
def clean_ndvi_series(ndvi_series):
    series = np.array(ndvi_series, dtype=float)
    if np.all(np.isnan(series)):
        return None
    valid = ~np.isnan(series)
    if valid.sum() < 3:
        return None
    x = np.arange(series.size)
    series[~valid] = np.interp(x[~valid], x[valid], series[valid])
    return series

def extract_landmarks(ndvi_series):
    """
    根据论文方法，利用曲率变化率(Rate of Change of Curvature)提取关键点
    这里使用 Savitzky-Golay 滤波平滑并计算导数
    """
    cleaned = clean_ndvi_series(ndvi_series)
    if cleaned is None:
        return None, None

    # a. 平滑去噪 (Smoothing)
    smooth_ndvi = savgol_filter(cleaned, window_length=31, polyorder=3)
    
    # b. 计算导数 (Derivatives)
    d1 = np.gradient(smooth_ndvi) # 一阶导数 (生长速度)
    d2 = np.gradient(d1)          # 二阶导数 (加速度)
    d3 = np.gradient(d2)          # 三阶导数 (曲率变化率近似)
    
    # c. 寻找关键点 (Landmarks)
    # 论文中：Greenup/Maturity 是曲率变化率的局部最大值
    #        Senescence/Dormancy 是曲率变化率的局部最小值
    # 这里简化逻辑：寻找 d3 的极值点作为近似特征
    
    # 简单的峰值检测
    from scipy.signal import find_peaks
    # 生长期 (Upward): 找 d3 的正峰值
    upward_peaks, _ = find_peaks(d3[:180], height=0.0001, distance=20) 
    # 衰退期 (Downward): 找 d3 的负峰值 (即 -d3 的正峰值)
    downward_peaks, _ = find_peaks(-d3[180:], height=0.0001, distance=20)
    downward_peaks += 180 # 修正索引
    
    # 选取最重要的4个点 (假设)
    # Greenup (返青), Maturity (成熟), Senescence (衰老), Dormancy (休眠)
    try:
        landmarks = {
            'Greenup': upward_peaks[0],
            'Maturity': upward_peaks[-1], # 假设最后一个上升峰值是成熟前奏
            'Senescence': downward_peaks[0],
            'Dormancy': downward_peaks[-1]
        }
    except:
        # 兜底：如果没有检测到完美峰值，使用简单的阈值法或固定点
        landmarks = {'Greenup': 100, 'Maturity': 150, 'Senescence': 260, 'Dormancy': 300}
        
    return smooth_ndvi, landmarks

# ==========================================
# 3. 混合匹配：MICA 算法 (Phenophase Matching)
# ==========================================
def warp_and_match(ref_curve, tgt_curve, ref_lm, tgt_lm):
    """
    利用 MICA (Multi-Interval Curve Alignment) 对齐曲线
    """
    # a. 对齐关键点 (Align Landmarks)
    # 将 Target 的关键点映射到 Reference 的关键点位置
    # 构建简单的分段线性映射函数 A(x)
    
    key_points_ref = sorted(list(ref_lm.values()))
    key_points_tgt = sorted(list(tgt_lm.values()))
    
    # 添加起始和结束点 (0, 365) 保证全覆盖
    x_ref = [0] + key_points_ref + [365]
    x_tgt = [0] + key_points_tgt + [365]
    
    # 建立映射关系: Target time -> Reference time
    warp_func = interp1d(x_tgt, x_ref, kind='linear', fill_value="extrapolate")
    
    # b. 扭曲目标曲线 (Warp Target Curve)
    # 计算“校正后”的 Target 曲线在标准时间轴上的形态
    warped_time = warp_func(np.arange(len(tgt_curve)))
    # 注意：这里我们实际上是想看 Target 在 Ref 时间轴上的表现
    # 为简单起见，我们将 Target 的值“移”到 Ref 的时间点上
    
    # 反向插值：在 Ref 的时间网格上，找到对应的 Target 值
    # 真实的 MICA 更复杂，这里做演示级简化
    inverse_warp = interp1d(x_ref, x_tgt, kind='linear', fill_value="extrapolate")
    original_time_indices = inverse_warp(np.arange(len(ref_curve)))
    # 限制索引范围
    original_time_indices = np.clip(original_time_indices, 0, 364)
    
    warped_tgt_curve = interp1d(np.arange(len(tgt_curve)), tgt_curve)(original_time_indices)
    
    return warped_tgt_curve

# ==========================================
# 4. 相似度计算：基于斜率距离 (Slope-based Distance)
# ==========================================
def calculate_similarity(curve1, curve2):
    """
    论文公式 (1): 基于斜率的距离函数
    d(Ct, Cr) = mean( |slope_t - slope_r| )
    """
    # 计算斜率 (Slope)
    s1 = np.gradient(curve1)
    s2 = np.gradient(curve2)
    
    # 计算距离 (Distance)
    # 距离越小，相似度越高
    dist = np.mean(np.abs(s1 - s2))
    
    # 转换为 0-100 的相似度分数 (heuristic)
    similarity = 100 * np.exp(-10 * dist) 
    return similarity, dist

# ==========================================
# 5. 相似区域检索 (Similarity Search)
# ==========================================
ref_smooth, ref_marks = extract_landmarks(ref_ndvi)
if ref_smooth is None:
    raise RuntimeError('参考区 NDVI 数据不足，无法进行相似度匹配。')

results = []
for f in sample_pts:
    geom = ee.Geometry(f['geometry'])
    ndvi_ts = get_ndvi_series(geom, year=2020)
    smooth, marks = extract_landmarks(ndvi_ts)
    if smooth is None:
        continue
    warped = warp_and_match(ref_smooth, smooth, ref_marks, marks)
    sim_score, raw_dist = calculate_similarity(ref_smooth, warped)
    if sim_score < SIM_THRESHOLD:
        continue
    centroid = geom.centroid(maxError=1).coordinates().getInfo()
    results.append({
        'geometry': f['geometry'],
        'similarity': sim_score,
        'distance': raw_dist,
        'centroid': centroid,
        'smooth': smooth,
        'warped': warped,
        'landmarks': marks
    })

results.sort(key=lambda x: x['similarity'], reverse=True)
top_results = results[:TOP_N]

if not top_results:
    raise RuntimeError('未找到满足阈值的相似区域，请降低阈值或增加采样点数。')

if EXPORT_CSV:
    rows = []
    for idx, r in enumerate(top_results, start=1):
        rows.append({
            'rank': idx,
            'similarity': round(r['similarity'], 3),
            'distance': round(r['distance'], 6),
            'lon': r['centroid'][0],
            'lat': r['centroid'][1]
        })
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)
    print(f"✓ 相似区域结果已保存到: {OUTPUT_CSV}")

if EXPORT_MAP:
    # 地图中心设为洛川产区
    Map = geemap.Map(center=[35.8, 109.4], zoom=10, basemap='SATELLITE')
    
    # 添加金标准产区（蓝色）
    ref_fc = ee.FeatureCollection([ee.Feature(best_geom)])
    ref_styled = ref_fc.style(**{
        'color': '#0066ff',
        'width': 3,
        'fillColor': '#0066ff33'
    })
    Map.addLayer(ref_styled, {}, '🏆 金标准产区 (洛川)')
    
    # 添加相似产区（橙色点）
    top_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry(r['geometry']), {'similarity': r['similarity']})
        for r in top_results
    ])
    styled = top_fc.style(**{
        'color': '#ff6600',
        'pointSize': 8,
        'width': 2,
        'fillColor': '#ffcc00'
    })
    Map.addLayer(styled, {}, f'📍 相似产区 (Top {len(top_results)})')
    
    Map.to_html(OUTPUT_MAP)
    print(f"✓ 相似区域地图已保存到: {OUTPUT_MAP}")
    print(f"  - 金标准产区: 蓝色区域")
    print(f"  - 相似产区: 橙色点标注 (共 {len(top_results)} 个)")
    print(f"  - 相似度范围: {top_results[-1]['similarity']:.1f}% - {top_results[0]['similarity']:.1f}%")

print("\n" + "="*60)
print("✅ 分析完成！")
print("="*60)

# 选择相似度最高的区域进行可视化对比
best_match = top_results[0]
tgt_smooth = best_match['smooth']
tgt_marks = best_match['landmarks']
warped_tgt = best_match['warped']
sim_score = best_match['similarity']

# ==========================================
# 6. 结果可视化 (Visualization)
# ==========================================
print("\n📊 生成曲线对比图...\n")

fig = plt.figure(figsize=(15, 10))

# 子图1: 金标准产区 NDVI 时序
ax1 = plt.subplot(2, 2, 1)
ax1.plot(days, ref_smooth, 'b-', linewidth=2.5)
ax1.fill_between(days, ref_smooth, alpha=0.2, color='blue')
ax1.scatter(ref_marks.values(), [ref_smooth[int(i)] for i in ref_marks.values()], 
           c='darkblue', s=80, zorder=5, marker='o')
for name, idx in ref_marks.items():
    ax1.annotate(name, (idx, ref_smooth[int(idx)]), 
                xytext=(5, 5), textcoords='offset points', fontsize=9)
ax1.set_title('🏆 金标准产区 (洛川) NDVI 时序', fontsize=12, fontweight='bold')
ax1.set_xlabel('Day of Year (DOY)')
ax1.set_ylabel('NDVI')
ax1.grid(True, alpha=0.3)

# 子图2: 最相似产区 NDVI 时序
ax2 = plt.subplot(2, 2, 2)
ax2.plot(days, tgt_smooth, 'r-', linewidth=2.5)
ax2.fill_between(days, tgt_smooth, alpha=0.2, color='red')
ax2.scatter(tgt_marks.values(), [tgt_smooth[int(i)] for i in tgt_marks.values()], 
           c='darkred', s=80, zorder=5, marker='s')
for name, idx in tgt_marks.items():
    ax2.annotate(name, (idx, tgt_smooth[int(idx)]), 
                xytext=(5, 5), textcoords='offset points', fontsize=9)
ax2.set_title(f'📍 最相似产区 (相似度: {sim_score:.1f}%) NDVI 时序', fontsize=12, fontweight='bold')
ax2.set_xlabel('Day of Year (DOY)')
ax2.set_ylabel('NDVI')
ax2.grid(True, alpha=0.3)

# 子图3: 时间对齐前的曲线对比
ax3 = plt.subplot(2, 2, 3)
ax3.plot(days, ref_smooth, 'b-', label='金标准产区 (洛川)', linewidth=2.5)
ax3.plot(days, tgt_smooth, 'r--', label='候选产区', linewidth=2.5)
ax3.scatter(ref_marks.values(), [ref_smooth[int(i)] for i in ref_marks.values()], 
           c='blue', s=60, zorder=5, marker='o', alpha=0.7)
ax3.scatter(tgt_marks.values(), [tgt_smooth[int(i)] for i in tgt_marks.values()], 
           c='red', s=60, zorder=5, marker='s', alpha=0.7)
ax3.set_title('对齐前: 时间偏移明显', fontsize=12, fontweight='bold')
ax3.set_xlabel('Day of Year (DOY)')
ax3.set_ylabel('NDVI')
ax3.legend(loc='best', fontsize=10)
ax3.grid(True, alpha=0.3)

# 子图4: 时间对齐后的曲线对比
ax4 = plt.subplot(2, 2, 4)
ax4.plot(days, ref_smooth, 'b-', label='金标准产区 (洛川)', linewidth=2.5)
ax4.plot(days, warped_tgt, 'g-', label='候选产区 (对齐后)', linewidth=2.5)
ax4.fill_between(days, ref_smooth, warped_tgt, alpha=0.1, color='gray')
ax4.set_title(f'✅ 对齐后: 物候一致 (相似度: {sim_score:.1f}%)', fontsize=12, fontweight='bold')
ax4.set_xlabel('Day of Year (标准化)')
ax4.set_ylabel('NDVI')
ax4.legend(loc='best', fontsize=10)
ax4.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('phenology_matching_analysis.png', dpi=150, bbox_inches='tight')
print("✓ 曲线对比图已保存到: phenology_matching_analysis.png\n")
plt.show()