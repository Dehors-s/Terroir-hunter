import ee
import geemap

# 初始化 GEE
import os

# 获取项目 ID，如果没有则使用默认值
project_id = os.getenv('GCP_PROJECT_ID', 'terrior-hunter')  # Google Cloud 项目 ID

try:
    ee.Initialize(project=project_id)
except Exception as e:
    print(f"初始化失败: {e}")
    print("请完成以下步骤:")
    print("1. 访问 https://console.cloud.google.com 创建一个项目")
    print("2. 设置环境变量: set GCP_PROJECT_ID=your-project-id")
    print("3. 重新运行脚本")
    exit(1)

# 1. 定义感兴趣区域 (ROI) - 陕西洛川富士苹果典型产区
# 洛川县：世界最佳苹果优生区之一，位于陕西省延安市
# 地理位置：109.4°E, 35.8°N，海拔 800-1200m
# 搜索范围：以洛川为中心，半径约 50km 的周边地区
roi = ee.Geometry.Point([109.4, 35.8]).buffer(50000).bounds()  # 50km 半径

print("✓ ROI 已设置为陕西洛川富士苹果产区及周边")
print("  中心位置: 洛川县 (109.4°E, 35.8°N)")
print("  搜索半径: 50 km")
print("  典型特征: 黄土高原，海拔 800-1200m，昼夜温差大")
print("  金标准产区: 世界最佳苹果优生区")

# 2. 加载数据源 (Data Acquisition)
# 地形数据：NASA SRTM DEM (30m分辨率)
dem = ee.Image("USGS/SRTMGL1_003").clip(roi)

# 气候数据：WorldClim V1 Bioclim (历史气候数据)
# BIO1 = Annual Mean Temperature, BIO12 = Annual Precipitation
climate = ee.Image("WORLDCLIM/V1/BIO").clip(roi)
temp = climate.select('bio01').multiply(0.1) # 缩放因子
precip = climate.select('bio12')

# 土地覆盖：Sentinel-2 (用于剔除水体和建筑)
s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(roi).first()
# 计算地形因子
slope = ee.Terrain.slope(dem)
aspect = ee.Terrain.aspect(dem)

# --- 定义重分类函数 (Reclassify Helper) ---
# 将连续值映射为 1-9 的 AHP 得分
def reclassify_slope(img):
    return ee.Image(1) \
        .where(img.lt(5), 9)    \
        .where(img.gte(5).And(img.lt(15)), 8) \
        .where(img.gte(15).And(img.lt(25)), 6) \
        .where(img.gte(25), 1)  # 陡坡不适宜

def reclassify_aspect(img):
    # 阳坡 (135-225度) 得分高
    return ee.Image(1) \
        .where(img.gte(135).And(img.lt(225)), 9) \
        .where(img.gte(90).And(img.lt(135)), 7) \
        .where(img.gte(225).And(img.lt(270)), 7) \
        .where(img.lt(90).Or(img.gte(270)), 3) # 阴坡得分低

def reclassify_elevation(img):
    # 假设目标作物为高山苹果，适宜海拔 800-1300m
    return ee.Image(1) \
        .where(img.lt(600), 3) \
        .where(img.gte(600).And(img.lt(800)), 6) \
        .where(img.gte(800).And(img.lt(1300)), 9) \
        .where(img.gte(1300), 5)

# 应用重分类
score_slope = reclassify_slope(slope)
score_aspect = reclassify_aspect(aspect)
score_dem = reclassify_elevation(dem)

# --- AHP 加权叠加 ---
# 权重和必须为 1.0
w_slope = 0.35
w_elev = 0.25
w_aspect = 0.20
w_climate = 0.20

# 简单的气候得分 (温度越接近最佳值越好，假设最佳温度范围为 15-25°C)
# 温度已缩放，范围大约 -50 到 50 (单位0.1°C)
# 使用简单的线性映射到 1-9
score_climate = temp.add(50).divide(100).multiply(8).add(1).clamp(1, 9)

# 计算最终适宜性指数 LSI (Land Suitability Index)
lsi = score_slope.multiply(w_slope) \
    .add(score_dem.multiply(w_elev)) \
    .add(score_aspect.multiply(w_aspect)) \
    .add(score_climate.multiply(w_climate))

# 最终结果归一化到 0-100 分，便于展示
final_suitability = lsi.multiply(10).rename('Suitability_Score')

# --- 可视化 ---
Map = geemap.Map(center=[35.8, 109.4], zoom=11, basemap='SATELLITE')

# 设置可视化参数：红黄绿配色 (红=高适宜, 绿=不适宜)
vis_params = {
    'min': 30,
    'max': 90,
    'palette': ['green', 'yellow', 'orange', 'red']
}

Map.addLayer(final_suitability, vis_params, 'Apple Orchard Suitability (AHP)')

# 过滤出 "S级地块" (得分 > 85)
prime_locations = final_suitability.gt(85).selfMask()
Map.addLayer(prime_locations, {'palette': ['purple']}, 'Prime Locations (S-Class)')

# 保存地图到 HTML 文件
output_file = 'suitability_map.html'
Map.to_html(output_file)
print(f"✓ 地图已保存到: {output_file}")

# 计算并打印统计信息
print("\n=== 适宜性分析结果 ===")
print(f"分析区域中心: 陕西省洛川县 (109.4°E, 35.8°N)")
print(f"分析半径: 50 km")
print(f"\n权重分配:")
print(f"  - 坡度: {w_slope*100:.0f}%")
print(f"  - 海拔: {w_elev*100:.0f}%")
print(f"  - 坡向: {w_aspect*100:.0f}%")
print(f"  - 气候: {w_climate*100:.0f}%")

# 获取统计数据（采样点）
stats = final_suitability.sample(
    region=roi,
    scale=500,
    numPixels=100
).aggregate_stats('Suitability_Score')

try:
    mean_score = stats.get('mean').getInfo()
    print(f"\n平均适宜性得分: {mean_score:.1f}")
    print(f"适宜性等级划分:")
    print(f"  90-100: S级 (极优)")
    print(f"  80-90:  A级 (优秀)")
    print(f"  70-80:  B级 (良好)")
    print(f"  60-70:  C级 (中等)")
    print(f"  <60:    D级 (不推荐)")
except Exception as e:
    print(f"\n注意: 无法获取统计数据 ({e})")

print(f"\n请打开 {output_file} 查看详细地图！")
print("地图图层:")
print("  - Apple Orchard Suitability (AHP): 完整适宜性分析")
print("  - Prime Locations (S-Class): 高分地块 (>85分)")