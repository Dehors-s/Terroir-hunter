import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import pydeck as pdk
import time
import runpy
from pathlib import Path

# --- 页面配置 (必须在第一行) ---
st.set_page_config(
    page_title="天眼寻珍 - 农业资产发现引擎",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_SUITABILITY_MAP = ROOT_DIR / "suitability_map.html"
OUTPUT_SIMILARITY_MAP = ROOT_DIR / "similar_regions_map.html"
OUTPUT_SIMILARITY_CSV = ROOT_DIR / "similar_regions.csv"
OUTPUT_PHENOLOGY_PNG = ROOT_DIR / "phenology_matching_analysis.png"


def run_ahp_analysis():
    runpy.run_path(str(ROOT_DIR / "AHP.py"), run_name="__main__")


def run_hybrid_matching():
    runpy.run_path(str(ROOT_DIR / "Hybrid Phenology Matching.py"), run_name="__main__")


if "ahp_done" not in st.session_state:
    st.session_state.ahp_done = False
if "hybrid_done" not in st.session_state:
    st.session_state.hybrid_done = False

# --- 自定义CSS (整体视觉与模块组件) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=ZCOOL+XiaoWei&display=swap');

:root {
    --bg-0: #0b0f14;
    --bg-1: #0f1720;
    --bg-2: #121c28;
    --glow-1: #61d9ff;
    --glow-2: #7cffc4;
    --accent: #f7d774;
    --text-0: #e9f0f7;
    --text-1: #a4b3c6;
    --card: rgba(20, 30, 40, 0.62);
    --stroke: rgba(136, 176, 206, 0.25);
}

* { font-family: 'Space Grotesk', 'ZCOOL XiaoWei', sans-serif; }

.stApp {
    background: radial-gradient(1200px 600px at 10% 10%, rgba(97, 217, 255, 0.08), transparent 60%),
                radial-gradient(900px 500px at 90% 20%, rgba(124, 255, 196, 0.08), transparent 60%),
                linear-gradient(160deg, var(--bg-0), var(--bg-1) 55%, var(--bg-2));
    color: var(--text-0);
}

section.main > div { padding-top: 1.2rem; }

.hero {
    border: 1px solid var(--stroke);
    border-radius: 24px;
    padding: 28px 32px;
    background: linear-gradient(120deg, rgba(16, 25, 36, 0.85), rgba(12, 20, 28, 0.72));
    box-shadow: 0 24px 60px rgba(0,0,0,0.35);
}

.hero h1 {
    font-family: 'ZCOOL XiaoWei', serif;
    letter-spacing: 1px;
    font-size: 40px;
    margin-bottom: 0.3rem;
}

.hero p { color: var(--text-1); font-size: 16px; }

.badge {
    display: inline-flex;
    gap: 10px;
    align-items: center;
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid var(--stroke);
    background: rgba(15, 30, 40, 0.5);
    color: var(--text-1);
    font-size: 12px;
}

.stat-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin-top: 18px;
}

.stat {
    background: var(--card);
    border: 1px solid var(--stroke);
    border-radius: 18px;
    padding: 14px 16px;
}

.stat h3 { font-size: 20px; margin: 0 0 6px; }
.stat span { color: var(--text-1); font-size: 12px; }

.panel {
    background: var(--card);
    border: 1px solid var(--stroke);
    border-radius: 20px;
    padding: 18px 20px;
}

.section-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    font-size: 18px;
    margin-bottom: 10px;
}

.glow {
    color: var(--glow-2);
    text-shadow: 0 0 12px rgba(124, 255, 196, 0.35);
}

.big-font {
    font-size: 30px !important;
    font-weight: 700;
    color: var(--accent);
}

.stSidebar {
    background: linear-gradient(180deg, rgba(10, 18, 26, 0.98), rgba(9, 14, 20, 0.92));
    border-right: 1px solid rgba(136, 176, 206, 0.18);
}

.stSidebar .stRadio > label, .stSidebar .stSelectbox > label {
    color: var(--text-1);
}

.stTabs [data-baseweb="tab"] {
    background: rgba(16, 26, 36, 0.55);
    border: 1px solid var(--stroke);
    border-radius: 999px;
    color: var(--text-1);
    padding: 8px 16px;
}

.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: var(--text-0);
    border-color: rgba(124, 255, 196, 0.5);
    box-shadow: 0 0 16px rgba(97, 217, 255, 0.2);
}

@media (max-width: 980px) {
    .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 640px) {
    .stat-grid { grid-template-columns: 1fr; }
    .hero { padding: 22px; }
    .hero h1 { font-size: 30px; }
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

# 头部视觉区
st.markdown("""
<div class="hero">
    <div class="badge">Terroir Hunter • 卫星遥感 + IoT + AI</div>
    <h1>天眼寻珍：农业资产发现引擎</h1>
    <p>把“风土价值”看得见、算得清、说得出。当前分析区域已锁定秦巴山脉核心带。</p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="stat-grid">
    <div class="stat"><h3>92%</h3><span>风土匹配度峰值</span></div>
    <div class="stat"><h3>1.2k</h3><span>卫星样本像元</span></div>
    <div class="stat"><h3>24h</h3><span>微气候监测窗口</span></div>
    <div class="stat"><h3>40x</h3><span>亩产值提升潜力</span></div>
</div>
""", unsafe_allow_html=True)

st.markdown(f"<div class='section-title'>🌍 {target_city} · <span class='glow'>农业风土价值发现报告</span></div>", unsafe_allow_html=True)
st.markdown(f"系统正在分析 {target_province} 秦巴山区腹地数据，输出从遥感到商业价值的全链路评估。")

# ------------------------------------------------------------------
# 模块一：天眼扫描 (卫星热力图)
# 对应BP中的“第一级漏斗：低成本广域初筛”
# ------------------------------------------------------------------
if scan_mode == "广域光谱初筛 (卫星)":
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>1. 卫星光谱遥感扫描</div>", unsafe_allow_html=True)
    
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
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>1.1 AHP 适宜性分析 (真实计算)</div>", unsafe_allow_html=True)
    st.write("运行后会生成适宜性地图并在此处展示。")
    if st.button("🧭 运行 AHP 适宜性分析"):
        with st.spinner("正在计算适宜性指数，请稍候..."):
            try:
                run_ahp_analysis()
                st.session_state.ahp_done = True
                st.success("AHP 适宜性分析完成。")
            except Exception as exc:
                st.error(f"AHP 计算失败: {exc}")

    if st.session_state.ahp_done and OUTPUT_SUITABILITY_MAP.exists():
        components.html(OUTPUT_SUITABILITY_MAP.read_text(encoding="utf-8"), height=560, scrolling=True)
        st.caption("🗺️ 适宜性地图已生成：高分区建议重点开发。")
    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 模块二：地面验身 (物联网数据)
# 对应BP中的“第二级漏斗：地面验身”
# ------------------------------------------------------------------
elif scan_mode == "精准小气候分析 (IoT)":
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>2. 地面物联网实时监测</div>", unsafe_allow_html=True)
    
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
    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 模块三：资产评估 (商业变现)
# 对应BP中的“第三级漏斗：IP孵化”
# ------------------------------------------------------------------
elif scan_mode == "资产价值评估 (AI)":
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>3. 土地资产价值重塑报告</div>", unsafe_allow_html=True)

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
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>3.1 物候匹配与相似产区检索 (真实计算)</div>", unsafe_allow_html=True)
    st.write("运行后会生成相似产区地图、CSV 排名和对比图。")
    if st.button("🧪 运行物候匹配"):
        with st.spinner("正在进行物候匹配与相似区域检索..."):
            try:
                run_hybrid_matching()
                st.session_state.hybrid_done = True
                st.success("物候匹配完成。")
            except Exception as exc:
                st.error(f"物候匹配失败: {exc}")

    if st.session_state.hybrid_done:
        if OUTPUT_SIMILARITY_MAP.exists():
            components.html(OUTPUT_SIMILARITY_MAP.read_text(encoding="utf-8"), height=560, scrolling=True)
        if OUTPUT_SIMILARITY_CSV.exists():
            st.subheader("📋 相似产区排名")
            st.dataframe(pd.read_csv(OUTPUT_SIMILARITY_CSV))
        if OUTPUT_PHENOLOGY_PNG.exists():
            st.subheader("📈 物候曲线对比")
            st.image(str(OUTPUT_PHENOLOGY_PNG), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)