(() => {
let gsMarker;
let gsSelectedLatLon = null;
let gsPhenologyChart = null;
let gsCurrentPhenologyData = null;
let gsMapClickBound = false;
let gsActionsInitialized = false;
let gsModelsCache = {}; // Store complete model data for curve viewing
let gsCurveChart = null; // Chart instance for curve modal

function normalizeGsModel(model) {
    if (!model || typeof model !== 'object') return null;
    const normalizedId = model.id || model.model_id || '';
    if (!normalizedId) return null;
    return {
        ...model,
        id: normalizedId
    };
}

function getMainMap() {
    return window.mainMap || null;
}

// --- Map Initialization ---
function initMap() {
    const sharedMap = getMainMap();
    if (!sharedMap || gsMapClickBound) {
        console.log('[GS] Map already bound or map unavailable');
        return;
    }

    console.log('[GS] Binding map click event...');
    sharedMap.on('click', (e) => {
        const moduleEl = document.getElementById('golden-standard');
        if (!moduleEl || moduleEl.classList.contains('hidden')) {
            return;
        }
        const { lat, lng } = e.latlng;
        console.log('[GS] Map clicked at', lat, lng);
        setSelection(lat, lng);
    });
    gsMapClickBound = true;
    console.log('[GS] Map click event bound successfully');
}

function setSelection(lat, lng) {
    const sharedMap = getMainMap();
    if (!sharedMap) {
        console.warn('[GS] No shared map available');
        return;
    }
    gsSelectedLatLon = { lat, lon: lng };
    console.log('[GS] Selected location:', gsSelectedLatLon);
    
    // Remove existing marker
    if (gsMarker) sharedMap.removeLayer(gsMarker);
    
    // Add pulsing icon marker
    const pulseIcon = L.divIcon({
        className: 'custom-div-icon',
        html: `<div style="
            width: 20px;
            height: 20px;
            background-color: #f59e0b;
            border-radius: 50%;
            border: 2px solid white;
            box-shadow: 0 0 15px #f59e0b;
            animation: pulse-gold 2s infinite;
        "></div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });

    gsMarker = L.marker([lat, lng], { icon: pulseIcon }).addTo(sharedMap);
    
    // Update UI
    document.getElementById('gs-extract-btn').disabled = false;
    document.getElementById('gs-display-lat').textContent = `LAT: ${lat.toFixed(4)}`;
    document.getElementById('gs-display-lon').textContent = `LON: ${lng.toFixed(4)}`;
    
    // Fly to location
    sharedMap.flyTo([lat, lng], 13, { duration: 1.5 });
}

// --- Search Functionality ---
function initSearch() {
    const input = document.getElementById('gs-search-input');
    const btn = document.getElementById('gs-search-btn');

    const doSearch = async () => {
        const query = input.value;
        if (!query) return;

        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
        
        try {
            const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`);
            const data = await res.json();
            
            if (data && data.length > 0) {
                const { lat, lon } = data[0];
                setSelection(parseFloat(lat), parseFloat(lon));
            } else {
                alert('未找到该地点');
            }
        } catch (e) {
            console.error(e);
            alert('搜索失败');
        } finally {
            btn.innerHTML = 'LOCATE';
        }
    };

    btn.addEventListener('click', doSearch);
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') doSearch();
    });
}

// --- Actions ---
function initActionButtons() {
    // Only initialize once to avoid duplicate event listeners
    if (gsActionsInitialized) return;
    gsActionsInitialized = true;
    
    // 1. Extract Button
    const extractBtn = document.getElementById('gs-extract-btn');
    if (!extractBtn) return;
    
    extractBtn.addEventListener('click', async () => {
        console.log('[GS] Extract button clicked');
        if (!gsSelectedLatLon) {
            console.warn('[GS] No location selected');
            alert('请先点击地图选择地点');
            return;
        }
        
        const btn = document.getElementById('gs-extract-btn');
        const originalText = btn.innerHTML;
        
        console.log('[GS] Sending request to API with:', gsSelectedLatLon);
        btn.innerHTML = '<i class="fa-solid fa-satellite fa-spin"></i><span>正在分析卫星数据...</span>';
        btn.disabled = true;

        try {
            // Call API
            console.log('[GS] Fetching /api/extract-phenology...');
            const response = await fetch('/api/extract-phenology', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(gsSelectedLatLon)
            });
            
            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`API Error ${response.status}: ${errText}`);
            }
            
            const data = await response.json();
            console.log('[GS] API response received:', data);
            gsCurrentPhenologyData = data;
            
            // Render Results
            console.log('[GS] Rendering results...');
            renderResults(data);
            
        } catch (error) {
            console.error('[GS] Error:', error);
            alert('数据提取失败: ' + error.message);
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    });

    // 2. Save Button
    const saveBtn = document.getElementById('gs-save-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveGoldenStandard);
    }
    
    // 3. View All Models Button
    const viewAllBtn = document.getElementById('gs-view-all-btn');
    if (viewAllBtn) {
        viewAllBtn.addEventListener('click', showAllGoldenStandards);
    }
    
    // 4. Modal Close Button
    const modalClose = document.getElementById('gs-modal-close');
    if (modalClose) {
        modalClose.addEventListener('click', closeGoldenStandardsModal);
    }
    
    const modalOverlay = document.getElementById('gs-modal-overlay');
    if (modalOverlay) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeGoldenStandardsModal();
        });
    }
    
    // 4b. Curve Modal Events
    const curveModalClose = document.getElementById('gs-curve-modal-close');
    if (curveModalClose) {
        curveModalClose.addEventListener('click', closeCurveModal);
    }
    
    const curveBtnClose = document.getElementById('gs-curve-close-btn');
    if (curveBtnClose) {
        curveBtnClose.addEventListener('click', closeCurveModal);
    }
    
    const curveDownloadBtn = document.getElementById('gs-curve-download-btn');
    if (curveDownloadBtn) {
        curveDownloadBtn.addEventListener('click', downloadCurveAsImage);
    }
    
    const curveModalOverlay = document.getElementById('gs-curve-modal');
    if (curveModalOverlay) {
        curveModalOverlay.addEventListener('click', (e) => {
            if (e.target === curveModalOverlay) closeCurveModal();
        });
    }
    
    // 5. Init Tags
    const tagsContainer = document.getElementById('gs-tags-container');
    if (!tagsContainer) return;
    const tags = ['高糖度', '耐寒', '长日照'];
    tags.forEach(tag => {
        const span = document.createElement('span');
        span.className = 'px-2 py-1 bg-white/10 rounded text-xs text-gray-300 cursor-pointer hover:bg-tech-gold/20 hover:text-tech-gold border border-transparent hover:border-tech-gold/30 transition select-none';
        span.textContent = tag;
        span.onclick = () => {
            span.classList.toggle('bg-tech-gold');
            span.classList.toggle('text-black');
            span.classList.toggle('font-bold');
        };
        tagsContainer.appendChild(span);
    });
}

// --- Rendering ---
function renderResults(data) {
    // Switch Views
    document.getElementById('gs-empty-state').classList.add('hidden');
    document.getElementById('gs-analysis-content').classList.remove('hidden');

    // Data panel stats
    const avgTemp = data.lst_curve.reduce((a,b)=>a+b, 0) / data.lst_curve.length;
    document.getElementById('gs-stat-temp').textContent = avgTemp.toFixed(1) + '°C';
    const mockRain = 600 + Math.abs((data.lat || 0) * 4.2);
    document.getElementById('gs-stat-rain').textContent = mockRain.toFixed(0) + ' mm';

    // Milestones
    document.getElementById('gs-milestone-germ').textContent = `Day ${data.milestones.valleys[0] || 'N/A'}`;
    document.getElementById('gs-milestone-mat').textContent = `Day ${data.milestones.peaks[0] || 'N/A'}`;

    // Chart
    renderChart(data.ndvi_curve, data.lst_curve);
}

function renderChart(ndviData, lstData) {
    const ctx = document.getElementById('gs-phenology-chart').getContext('2d');
    
    if (gsPhenologyChart) gsPhenologyChart.destroy();

    // Normalize LST to match NDVI scale roughly for visualization or use dual axis
    // Ideally dual axis.
    
    gsPhenologyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array.from({length: 365}, (_, i) => i + 1),
            datasets: [
                {
                    label: 'NDVI (植被指数)',
                    data: ndviData,
                    borderColor: '#10b981', // tech-green
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    pointRadius: 0,
                    yAxisID: 'y'
                },
                {
                    label: 'LST (地表温度)',
                    data: lstData,
                    borderColor: '#f59e0b', // tech-gold
                    backgroundColor: 'rgba(245, 153, 11, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    pointRadius: 0,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#ccc',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#666' }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#10b981' }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#f59e0b' }
                }
            }
        }
    });
}


// --- Saving ---
async function saveGoldenStandard() {
    if (!gsCurrentPhenologyData) {
        alert("请先进行物候提取！");
        return;
    }

    const nameInput = document.getElementById('gs-model-name');
    const name = nameInput.value;
    if (!name) {
        alert('请输入模型名称');
        nameInput.focus();
        return;
    }

    const crop = document.getElementById('gs-crop-type').value;
    
    // Collect active tags
    const activeTags = [];
    document.querySelectorAll('#gs-tags-container span').forEach(span => {
        if (span.classList.contains('bg-tech-gold')) { // checking if it has the active class
            activeTags.push(span.textContent);
        }
    });

    const payload = {
        model_name: name,
        crop_type: crop,
        latitude: gsSelectedLatLon.lat,
        longitude: gsSelectedLatLon.lon,
        ndvi_curve: gsCurrentPhenologyData.ndvi_curve,
        lst_curve: gsCurrentPhenologyData.lst_curve,
        tags: activeTags
    };

    const btn = document.getElementById('gs-save-btn');
    const originalContent = '<span>💾 保存为金标准模型 (Save as Golden Standard)</span>';
    
    // Loading State
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin animate-spin"></i> Saving...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/golden-standards', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            // Success Animation
            btn.innerHTML = '<i class="fa-solid fa-check-circle text-lg"></i> Saved!';
            btn.classList.remove('bg-tech-gold', 'text-black');
            btn.classList.add('bg-green-600', 'text-white');
            
            // Reset after 2 seconds
            setTimeout(() => {
                btn.innerHTML = originalContent;
                btn.classList.add('bg-tech-gold', 'text-black');
                btn.classList.remove('bg-green-600', 'text-white');
                btn.disabled = false;
            }, 2000);
        } else {
            throw new Error('Server returned ' + response.status);
        }
    } catch (error) {
        console.error(error);
        alert('保存失败: ' + error.message);
        btn.innerHTML = originalContent;
        btn.disabled = false;
    }
}

// --- View All Golden Standards ---
async function showAllGoldenStandards() {
    const modal = document.getElementById('gs-modal-overlay');
    if (!modal) return;
    
    modal.classList.remove('hidden');
    await loadAndDisplayModels();
}

function closeGoldenStandardsModal() {
    const modal = document.getElementById('gs-modal-overlay');
    if (modal) {
        modal.classList.add('hidden');
    }
}

async function loadAndDisplayModels() {
    const listContainer = document.getElementById('gs-model-list');
    if (!listContainer) return;
    
    try {
        const response = await fetch('/api/golden-standards', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`API Error ${response.status}`);
        }
        
        const rawModels = await response.json();
        const models = (Array.isArray(rawModels) ? rawModels : [])
            .map(normalizeGsModel)
            .filter(Boolean);
        
        // Clear cache and rebuild it
        gsModelsCache = {};
        models.forEach(model => {
            gsModelsCache[model.id] = model;
        });
        
        // Update count
        const countEl = document.getElementById('gs-model-count');
        if (countEl) countEl.textContent = models.length;
        
        // Clear loading state
        listContainer.innerHTML = '';
        
        if (models.length === 0) {
            listContainer.innerHTML = `
                <div class="text-center py-8 text-gray-400">
                    <i class="fa-solid fa-inbox text-3xl mb-2 opacity-50"></i>
                    <p>暂无保存的金标准模型</p>
                </div>
            `;
            return;
        }
        
        // Render models
        models.forEach((model, index) => {
            const modelCard = document.createElement('div');
            modelCard.className = 'glass-panel p-4 rounded-lg border border-white/10 bg-black/30 hover:bg-black/50 transition cursor-pointer';
            
            // Format timestamp
            const createdDate = model.created_at
                ? new Date(model.created_at).toLocaleString('zh-CN')
                : '未知';
            const safeModelName = String(model.model_name || '未命名').replace(/'/g, "\\'");
            
            // Active tags display
            const tagsHtml = model.tags && model.tags.length > 0 
                ? `<div class="flex flex-wrap gap-1">${model.tags.map(tag => `<span class="text-xs px-2 py-1 bg-tech-gold/20 text-tech-gold rounded">${tag}</span>`).join('')}</div>`
                : '<p class="text-xs text-gray-500">无标签</p>';
            
            modelCard.innerHTML = `
                <div class="flex items-start justify-between mb-2">
                    <div>
                        <h3 class="font-bold text-white">${model.model_name}</h3>
                        <p class="text-xs text-gray-400">作物类型: ${model.crop_type}</p>
                    </div>
                    <span class="text-xs text-gray-500">#${index + 1}</span>
                </div>
                <div class="grid grid-cols-2 gap-2 text-xs mb-2">
                    <p class="text-gray-400">纬度: <span class="text-white">${model.latitude.toFixed(4)}°</span></p>
                    <p class="text-gray-400">经度: <span class="text-white">${model.longitude.toFixed(4)}°</span></p>
                </div>
                <p class="text-xs text-gray-500 mb-2">创建时间: ${createdDate}</p>
                <div class="mb-3">
                    <p class="text-xs text-gray-400 mb-1">标签:</p>
                    ${tagsHtml}
                </div>
                <div class="flex gap-2">
                    <button class="flex-1 text-sm bg-tech-gold/20 hover:bg-tech-gold/40 text-tech-gold rounded py-2 transition font-mono" onclick="gsLoadModelData('${model.id}')">
                        <i class="fa-solid fa-chart-line"></i> 查看曲线 
                    </button>
                    <button class="flex-1 text-sm bg-red-600/20 hover:bg-red-600/40 text-red-400 rounded py-2 transition font-mono" onclick="gsDeleteModel('${model.id}', '${safeModelName}')">
                        <i class="fa-solid fa-trash"></i> 删除
                    </button>
                </div>
            `;
            
            listContainer.appendChild(modelCard);
        });
    } catch (error) {
        console.error('[GS] Error loading models:', error);
        listContainer.innerHTML = `
            <div class="text-center py-8 text-red-400">
                <i class="fa-solid fa-circle-exclamation text-3xl mb-2 opacity-50"></i>
                <p>加载失败: ${error.message}</p>
            </div>
        `;
    }
}

// Function to delete a golden standard model
async function gsDeleteModel(modelId, modelName) {
    if (!modelId) {
        alert('模型ID无效，无法删除');
        return;
    }

    const displayName = modelName || '该模型';

    // Confirmation dialog
    if (!confirm(`确定要删除模型 "${displayName}" 吗？此操作无法撤销。`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/golden-standards/${modelId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`API Error ${response.status}: ${errorText}`);
        }
        
        // Success - reload the list
        await loadAndDisplayModels();
        
        // Show success message
        alert('模型已删除');
    } catch (error) {
        console.error('[GS] Error deleting model:', error);
        alert('删除失败: ' + error.message);
    }
}

// Function to load and display a saved model's curve data
function gsLoadModelData(modelId) {
    const renderModel = (model) => {
        if (!model) {
            alert('未找到模型数据');
            return;
        }
        
        // Update modal title and info
        const titleEl = document.getElementById('gs-curve-modal-title');
        if (titleEl) titleEl.textContent = model.model_name + ' (作物: ' + model.crop_type + ')';
        
        const createdEl = document.getElementById('gs-curve-created-at');
        if (createdEl) {
            createdEl.textContent = model.created_at
                ? new Date(model.created_at).toLocaleString('zh-CN')
                : '未知';
        }
        
        const locationEl = document.getElementById('gs-curve-location');
        if (locationEl) locationEl.textContent = `${model.latitude.toFixed(4)}°N, ${model.longitude.toFixed(4)}°E`;
        
        // Render curve chart
        renderCurveChart(model.ndvi_curve, model.lst_curve);
        
        // Show modal
        const modal = document.getElementById('gs-curve-modal');
        if (modal) modal.classList.remove('hidden');
    };

    const model = gsModelsCache[modelId];
    if (model) {
        renderModel(model);
        return;
    }

    fetch('/api/golden-standards')
        .then(res => {
            if (!res.ok) throw new Error(`API Error ${res.status}`);
            return res.json();
        })
        .then(data => {
            const models = (Array.isArray(data) ? data : [])
                .map(normalizeGsModel)
                .filter(Boolean);

            models.forEach(item => {
                gsModelsCache[item.id] = item;
            });

            renderModel(gsModelsCache[modelId]);
        })
        .catch(error => {
            console.error('[GS] Load model data failed:', error);
            alert('加载模型数据失败: ' + error.message);
        });
}

function renderCurveChart(ndviData, lstData) {
    const ctx = document.getElementById('gs-curve-chart');
    if (!ctx) return;
    
    // Destroy existing chart if any
    if (gsCurveChart) gsCurveChart.destroy();
    
    gsCurveChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array.from({length: 365}, (_, i) => i + 1),
            datasets: [
                {
                    label: 'NDVI (植被指数)',
                    data: ndviData,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    pointRadius: 0,
                    yAxisID: 'y'
                },
                {
                    label: 'LST (地表温度)',
                    data: lstData,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    pointRadius: 0,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: true,
                    labels: { color: '#999', boxWidth: 12 }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#ccc',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#666' }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#10b981' }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#f59e0b' }
                }
            }
        }
    });
}

function closeCurveModal() {
    const modal = document.getElementById('gs-curve-modal');
    if (modal) modal.classList.add('hidden');
    if (gsCurveChart) gsCurveChart.destroy();
}

function downloadCurveAsImage() {
    const canvas = document.getElementById('gs-curve-chart');
    if (!canvas) return;
    
    const link = document.createElement('a');
    link.href = canvas.toDataURL('image/png');
    link.download = `wind-terroir-curve-${Date.now()}.png`;
    link.click();
}

// 加载模型到侧边栏
function gsLoadSidebarModels() {
    const container = document.getElementById('gs-sidebar-models-container');
    if (!container) return;
    
    container.innerHTML = '<div class="text-gray-400 text-sm">加载中...</div>';
    
    fetch('/api/golden-standards')
        .then(res => res.json())
        .then(data => {
            if (!Array.isArray(data)) data = [];

            const normalizedModels = data
                .map(normalizeGsModel)
                .filter(Boolean);

            gsModelsCache = {};
            normalizedModels.forEach(model => {
                gsModelsCache[model.id] = model;
            });
            
            if (normalizedModels.length === 0) {
                container.innerHTML = '<div class="text-gray-400 text-sm p-4">暂无模型</div>';
                return;
            }
            
            let html = '';
            normalizedModels.forEach(model => {
                const modelId = model.id;
                const modelName = model.model_name || '未命名';
                const cropType = model.crop_type || '未知';
                const location = model.location || '未知位置';
                const safeModelName = String(modelName).replace(/'/g, "\\'");
                
                html += `
                    <div class="bg-black/40 border border-white/10 rounded-lg p-3 hover:border-white/20 transition">
                        <div class="flex justify-between items-start gap-2 mb-2">
                            <div class="flex-1 min-w-0">
                                <p class="font-semibold text-white truncate text-sm">${modelName}</p>
                                <p class="text-xs text-gray-400">${cropType} • ${location}</p>
                            </div>
                            <button onclick="gsOpenRenameModal('${modelId}', '${safeModelName}')" class="text-xs px-2 py-1 bg-white/10 hover:bg-white/20 text-gray-300 rounded transition whitespace-nowrap">
                                重命名
                            </button>
                        </div>
                        <div class="flex gap-2">
                            <button onclick="gsLoadModelData('${modelId}')" class="flex-1 text-xs py-1 bg-tech-gold/20 hover:bg-tech-gold/30 text-tech-gold rounded transition">
                                查看数据
                            </button>
                            <button onclick="gsDeleteModel('${modelId}', '${safeModelName}')" class="flex-1 text-xs py-1 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded transition">
                                删除
                            </button>
                        </div>
                    </div>
                `;
            });
            
            container.innerHTML = html;
            
            // 更新模型数量
            const countBadge = document.getElementById('gs-sidebar-model-count');
            if (countBadge) {
                countBadge.textContent = normalizedModels.length;
            }
        })
        .catch(error => {
            console.error('加载模型失败:', error);
            container.innerHTML = '<div class="text-red-400 text-sm p-4">加载失败</div>';
        });
}

// 打开重命名模态框
function gsOpenRenameModal(modelId, currentName) {
    const modal = document.getElementById('gs-rename-modal');
    const input = document.getElementById('gs-rename-input');
    
    if (!modelId) {
        alert('模型ID无效，无法重命名');
        return;
    }

    if (modal && input) {
        // 存储当前模型ID供确认时使用
        modal.dataset.modelId = modelId;
        input.value = currentName;
        input.focus();
        input.select();
        modal.classList.remove('hidden');
    }
}

// 确认重命名
function gsConfirmRename() {
    const modal = document.getElementById('gs-rename-modal');
    const input = document.getElementById('gs-rename-input');
    const modelId = modal?.dataset.modelId;
    const newName = input?.value.trim();
    
    if (!modelId || !newName) {
        alert('请输入新名称');
        return;
    }
    
    // 调用 API 重命名
    fetch(`/api/golden-standards/${encodeURIComponent(modelId)}/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: newName })
    })
    .then(async res => {
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(payload.detail || payload.message || `重命名失败 (${res.status})`);
        }
        return payload;
    })
    .then(() => {
        gsCloseRenameModal();
        // 刷新侧边栏模型列表
        gsLoadSidebarModels();
    })
    .catch(error => {
        console.error('重命名错误:', error);
        alert('重命名失败: ' + error.message);
    });
}

// 关闭重命名模态框
function gsCloseRenameModal() {
    const modal = document.getElementById('gs-rename-modal');
    if (modal) {
        modal.classList.add('hidden');
        modal.dataset.modelId = '';
    }
}

// Expose functions to global scope for HTML onclick handlers
window.gsLoadModelData = gsLoadModelData;
window.gsDeleteModel = gsDeleteModel;
window.closeCurveModal = closeCurveModal;
window.downloadCurveAsImage = downloadCurveAsImage;
window.gsLoadSidebarModels = gsLoadSidebarModels;
window.gsOpenRenameModal = gsOpenRenameModal;
window.gsConfirmRename = gsConfirmRename;
window.gsCloseRenameModal = gsCloseRenameModal;

window.initGoldenStandardModule = function initGoldenStandardModule() {
    if (!document.getElementById('golden-standard')) {
        return;
    }
    const sharedMap = getMainMap();
    if (!sharedMap) {
        return;
    }
    initMap();
    initSearch();
    initActionButtons();
    gsLoadSidebarModels();  // 加载模型到侧边栏
    sharedMap.invalidateSize();
};


// Add animation keyframes for pulse
const styleStyle = document.createElement('style');
styleStyle.innerHTML = `
@keyframes pulse-gold {
    0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.7); }
    70% { box-shadow: 0 0 0 15px rgba(245, 158, 11, 0); }
    100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
}`;
document.head.appendChild(styleStyle);

})();
