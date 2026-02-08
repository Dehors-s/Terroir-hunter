import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import time

# --- 页面配置 (必须在第一行) ---
st.set_page_config(
    page_title="天眼寻珍 - 农业资产发现引擎",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 自定义CSS (为了让界面看起来更科幻/高端) ---
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .big-font {
        font-size:30px !important;
        font-weight: bold;
        color: #4CAF50;
    }
    .metric-card {
        background-color: #262730;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #4CAF50;
    }
</style>
""", unsafe_allow_html=True)

# --- 侧边栏：控制台 ---
st.sidebar.image("https://img.icons8.com/color/96/000000/satellite-sending-signal.png", width=80)
st.sidebar.title("🛰️ 天眼控制台")
st.sidebar.markdown("---")

# 模拟选择扫描区域
target_province = st.sidebar.selectbox("目标省份", ["陕西省", "云南省", "四川省"])
target_city = st.sidebar.selectbox("目标市/区", ["商洛市·柞水县", "安康市·紫阳县", "汉中市·留坝县"])

# 核心功能按钮
st.sidebar.markdown("### 📡 扫描操作")
scan_mode = st.sidebar.radio("扫描模式", ["广域光谱初筛 (卫星)", "精准小气候分析 (IoT)", "资产价值评估 (AI)"])

st.sidebar.info("当前连接卫星：Sentinel-2L\n数据延迟：< 10ms")

# --- 主界面逻辑 ---

# 标题区
st.title(f"🌍 {target_city} - 农业风土价值发现报告")
st.markdown(f"天眼寻珍 (Terroir Hunter) 系统正在分析 {target_province} 秦巴山区腹地数据...")

# ------------------------------------------------------------------
# 模块一：天眼扫描 (卫星热力图)
# 对应BP中的“第一级漏斗：低成本广域初筛”
# ------------------------------------------------------------------
if scan_mode == "广域光谱初筛 (卫星)":
    st.header("1. 卫星光谱遥感扫描 (Sentinel-2 Data)")
    
    # 模拟一个进度条，增加演示时的紧张感
    if st.button("🚀 启动全域扫描"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        for i in range(100):
            # 模拟不同的计算阶段
            if i < 30: status_text.text("正在加载多光谱影像...")
            elif i < 60: status_text.text("正在计算 NDVI 植被指数...")
            elif i < 90: status_text.text("正在匹配‘波尔多’风土模型...")
            else: status_text.text("正在生成热力图...")
            time.sleep(0.02) # 演示速度
            progress_bar.progress(i + 1)
        st.success("扫描完成！发现 3 块高潜力未开发地块。")

    # 生成模拟数据 (在陕西附近的坐标)
    # 这里的 lat/lon 是模拟商洛山区的
    df_map = pd.DataFrame(
        np.random.randn(1000, 2) / [50, 50] + [33.6, 109.0],
        columns=['lat', 'lon'])
    
    # 增加一列“潜力值”，用于热力图权重
    df_map['potential'] = np.random.rand(1000)

    # 使用 Pydeck 绘制酷炫的 3D 热力图
    layer = pdk.Layer(
        "HeatmapLayer",
        data=df_map,
        get_position='[lon, lat]',
        get_weight="potential",
        radius_pixels=60,
        opacity=0.8,
    )

    view_state = pdk.ViewState(latitude=33.6, longitude=109.0, zoom=10, pitch=50)
    
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "风土匹配度: {potential}"}
    ))

    st.caption("🔴 红色高亮区域：风土模型匹配度 > 95% (建议重点开发)")

# ------------------------------------------------------------------
# 模块二：地面验身 (物联网数据)
# 对应BP中的“第二级漏斗：地面验身”
# ------------------------------------------------------------------
elif scan_mode == "精准小气候分析 (IoT)":
    st.header("2. 地面物联网实时监测 (Ground Truth)")
    
    col1, col2, col3, col4 = st.columns(4)
    
    # 使用 st.metric 展示核心指标
    # 这里的 delta (绿色箭头) 会给评委很好的视觉反馈
    col1.metric(label="当前气温", value="18.5 °C", delta="昼夜温差 12°C (优)")
    col2.metric(label="空气湿度", value="45 %", delta="-5% (适合糖分积累)")
    col3.metric(label="土壤 pH 值", value="6.5", delta="微酸性 (完美)")
    col4.metric(label="光合有效辐射", value="1200 μmol", delta="High")

    st.markdown("---")
    
    # 模拟实时数据图表
    st.subheader("📊 过去 24 小时微气候变化趋势")
    
    chart_data = pd.DataFrame(
        np.random.randn(24, 2) + [18, 45], # 模拟温度和湿度
        columns=['温度 (°C)', '湿度 (%)']
    )
    st.line_chart(chart_data)
    
    st.info("💡 结论：该地块昼夜温差大，非常有利于苹果/葡萄的糖分与花青素积累。")

# ------------------------------------------------------------------
# 模块三：资产评估 (商业变现)
# 对应BP中的“第三级漏斗：IP孵化”
# ------------------------------------------------------------------
elif scan_mode == "资产价值评估 (AI)":
    st.header("3. 土地资产价值重塑报告 (AI Valuation)")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.success("✅ 匹配成功：顶级高山脆苹果产区")
        st.markdown("""
        ### 📝 风土体检报告
        * 相似产区：🇫🇷 法国·波尔多 (92% 相似度)
        * 推荐品种：瑞雪苹果 / 阳光玫瑰葡萄
        * 预计糖度：18.5 Brix (普通苹果仅 13 Brix)
        * 核心优势：海拔 1200米，无工业污染，天然富硒土
        """)
    
    with col2:
        st.warning("💰 商业价值预估")
        # 用大字体展示钱，冲击力强
        st.markdown('<p class="big-font">预估亩产值：¥ 35,000 / 亩</p>', unsafe_allow_html=True)
        st.markdown("*(传统玉米种植仅 ¥ 800 / 亩，价值提升 40倍)*")
        
        # 进度条展示IP潜力
        st.write("品牌孵化潜力 (IP Score)")
        st.progress(0.95)
        st.caption("评级：S级 (建议立即签约独家包销)")

    st.markdown("---")
    st.markdown("### 📦 生成 IP 方案预览")
    st.image("https://images.unsplash.com/photo-1630563451961-ac2ff27676ab?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=80", caption="概念产品：云端之吻·高山野生苹果", width=400)