# 🛰️ 天眼寻珍 - 农业资产发现引擎

> Terroir Hunter System - 基于卫星遥感与物联网的农业风土价值发现平台

## 📖 项目简介

天眼寻珍是一个创新的农业科技应用，通过整合卫星遥感数据、地面物联网监测和AI价值评估，帮助发现和挖掘中国秦巴山区等欠发达地区的优质农业资产，实现土地价值的重塑与提升。

**核心理念：** 像发现波尔多一样发现中国的优质农业产区

## ✨ 功能特点

### 1. 广域光谱初筛 (卫星遥感)
- 🌍 基于 Sentinel-2 卫星多光谱影像分析
- 📊 NDVI 植被指数计算
- 🗺️ 3D 热力图可视化高潜力地块
- 🎯 风土模型智能匹配（波尔多标准）

### 2. 精准小气候分析 (IoT)
- 🌡️ 实时气温与昼夜温差监测
- 💧 空气湿度追踪
- 🧪 土壤 pH 值检测
- ☀️ 光合有效辐射测量
- 📈 24小时微气候变化趋势分析

### 3. 资产价值评估 (AI)
- 💰 土地资产价值重塑报告
- 🏆 与国际顶级产区对比分析（相似度评分）
- 🌾 推荐种植品种与预期糖度
- 📦 品牌IP孵化潜力评估
- 💡 亩产值商业预估（40倍增值潜力）

## 🛠️ 技术栈

- **框架**: Streamlit - 快速构建交互式Web应用
- **数据处理**: Pandas, NumPy - 数据分析与科学计算
- **可视化**: Pydeck - 高性能3D地图渲染
- **数据源**: Sentinel-2卫星数据 (模拟)

## 📦 安装说明

### 环境要求
- Python 3.8+

### 安装步骤

1. 克隆项目
```bash
git clone <项目地址>
cd 三创赛
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

## 🚀 使用方法

### 方式一：Streamlit 演示（历史入口）
```bash
streamlit run app.py
```

应用将自动在浏览器中打开（默认地址：http://localhost:8501）

### 方式二：Web 主版本（推荐，FastAPI + 前端）

> 推荐使用根目录脚本 `start_local.ps1` 启动。脚本会自动：
> 1) 注入代理变量；2) 注入 GCP 项目；3) 预检 GEE；4) 通过后启动后端。

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_local.ps1 -ProjectId "terrior-hunter"
```

可选参数：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_local.ps1 -ProjectId "terrior-hunter" -ProxyUrl "http://127.0.0.1:7890"
```

浏览器访问：

- http://127.0.0.1:8000

## 🌐 Web 版本说明 (FastAPI + 前端)

本版本提供独立网页界面与后端 API，可部署到阿里云 ECS 或本地运行。

### 直接启动后端（手动方式）

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

或：

```bash
python server/main.py
```

### 访问前端

浏览器打开：http://localhost:8000

### 功能说明

- **AHP 适宜性分析**：触发 AHP.py 生成 suitability_map.html
- **Hybrid 物候匹配**：触发 Hybrid Phenology Matching.py 生成地图、CSV、曲线图

## ☁️ 阿里云 ECS 部署简要

1. 安装依赖并启动服务
   ```bash
   pip install -r requirements.txt
   uvicorn server.main:app --host 0.0.0.0 --port 8000
   ```
2. Nginx 反向代理 (示例)
   ```nginx
   server {
       listen 80;
       server_name your-domain-or-ip;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }
   }
   ```

### 操作流程

1. **选择目标区域**
   - 在左侧边栏选择目标省份和市/区
   - 当前支持：陕西省商洛市、云南省、四川省等秦巴山区

2. **选择扫描模式**
   - 📡 广域光谱初筛：查看卫星热力图，发现高潜力地块
   - 🌡️ 精准小气候分析：查看实时物联网监测数据
   - 💰 资产价值评估：生成完整的商业价值报告

3. **查看分析结果**
   - 启动扫描按钮开始数据处理
   - 实时查看进度条与状态信息
   - 查看可视化图表与评估报告

## 📁 项目结构

```
三创赛/
├── app.py                  # Streamlit 演示入口
├── start_local.ps1         # 本地一键启动（代理 + GEE预检 + 后端启动）
├── frontend/               # 前端页面与脚本
├── server/                 # FastAPI 后端
├── requirements.txt        # Python依赖列表
└── README.md               # 项目说明文档
```

## 🎯 应用场景

### 目标用户
- 🏛️ 地方政府农业部门
- 🌾 农业企业与合作社
- 💼 农业投资机构
- 🎓 农业科研机构

### 核心价值
- **发现价值**：识别被低估的优质农业土地
- **数据驱动**：用科技手段替代传统的"靠天吃饭"
- **价值重塑**：通过品种升级实现亩产值40倍增长
- **精准扶贫**：帮助欠发达地区找到致富路径

## 💡 三级漏斗模型

```
第一级：低成本广域初筛 (卫星)
    ↓ 100万亩 → 10万亩
第二级：地面验身 (IoT)
    ↓ 10万亩 → 1万亩
第三级：IP孵化 (品牌)
    ↓ 签约包销，价值兑现
```

## 🔮 未来规划

- [ ] 接入真实 Sentinel-2 卫星API
- [ ] 集成物联网传感器实时数据流
- [ ] 增加更多风土模型（托斯卡纳、纳帕谷等）
- [ ] 开发移动端APP
- [ ] 增加农产品溯源功能
- [ ] 建立全国农业风土数据库

## 📊 演示数据说明

当前 Web 主版本已支持真实 GEE 数据。

- 物候提取与匹配默认采用严格真实数据模式：真实数据不可用时直接报错，不回退模拟。
- 若出现 `Earth Engine ... no project found` 或 `assets not found`，请检查：
    1) `GCP_PROJECT_ID` 是否设置为可用项目；
    2) 该项目是否已开通 Earth Engine API 与资产空间；
    3) 启动后端的同一终端会话是否设置了代理（如 `HTTP_PROXY/HTTPS_PROXY`）。

## 📄 许可证

本项目为三创赛参赛作品

## 👥 团队

三创赛项目团队

---

**注意**: 本系统仍处于迭代阶段。若使用 Web 主版本进行分析，建议始终通过 `start_local.ps1` 启动，以保证项目与代理配置一致。
