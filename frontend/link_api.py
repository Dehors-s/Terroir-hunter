
import os

file_path = "d:/Work space/三创赛/frontend/index.html"

# Replacement 1: runAHP
ahp_replacement = """
        // --- 4. AHP 分析功能 (API Integrated) ---
        async function runAHP() {
            const btn = document.getElementById('ahp-btn');
            const radar = document.getElementById('radar-layer');
            
            // 添加故障效果
            btn.classList.add('glitch-effect');
            
            // UI 状态变更：分析中
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>ANALYZING...</span>';
            btn.classList.add('opacity-80', 'cursor-not-allowed');
            radar.style.display = 'block'; // 显示雷达

            try {
                // 1. 启动任务
                const res = await fetch('/api/run/ahp', { method: 'POST' });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Failed to start AHP');
                }

                // 2. 轮询状态
                const poll = setInterval(async () => {
                    try {
                        const statusRes = await fetch('/api/status');
                        const statusData = await statusRes.json();
                        const task = statusData.tasks.ahp;

                        if (task.status === 'completed') {
                            clearInterval(poll);
                            finishAHP();
                        } else if (task.status === 'failed') {
                            clearInterval(poll);
                            alert('AHP 分析失败: ' + task.error);
                            resetBtn(btn, radar, '运行 AHP 分析', 'fa-play');
                        }
                    } catch (e) {
                         console.error("Polling error", e);
                    }
                }, 2000);

            } catch (e) {
                alert('启动失败: ' + e.message);
                resetBtn(btn, radar, '运行 AHP 分析', 'fa-play');
            }
        }

        async function finishAHP() {
            const btn = document.getElementById('ahp-btn');
            const radar = document.getElementById('radar-layer');

            // UI 状态变更：分析完成
            btn.innerHTML = '<i class="fa-solid fa-check"></i> <span>分析完成</span>';
            btn.classList.remove('bg-tech-green');
            btn.classList.add('bg-gray-600'); // 按钮变灰
            radar.style.display = 'none'; // 隐藏雷达

            try {
                // 3. 获取结果
                const res = await fetch('/api/output/ahp_results.json');
                const data = await res.json();

                // 更新结果数据
                document.getElementById('avg-score').innerText = data.avg_score;
                document.getElementById('s-class-count').innerText = data.s_class_count;
                
                // 更新图表
                updateSuitabilityChart(data.suitability_dist);
                
                // 在地图上添加标记 (Reload map overlay if easier, or just parse s-class logic if included)
                // Assuming script generated HTML map. We could load it in an iframe or just acknowledge completion.
                // For now, keep mock markers or improve later.
                addAHPMarkers();
                
                playCompletionSound();
            } catch (e) {
                console.error("Failed to load results", e);
                alert("分析完成但无法加载结果文件。");
            }
        }

        function resetBtn(btn, radar, text, icon) {
            btn.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${text}</span>`;
            btn.classList.remove('opacity-80', 'cursor-not-allowed', 'bg-gray-600');
            btn.classList.add('bg-tech-green');
            radar.style.display = 'none';
        }
"""

# Replacement 2: runPhenology
phenology_replacement = """
        // --- 5. 物候期匹配功能 (API Integrated) ---
        async function runPhenology() {
            const btn = document.getElementById('phenology-btn');
            const radar = document.getElementById('radar-layer');
            
            // 添加故障效果
            btn.classList.add('glitch-effect');
            
            // UI 状态变更：分析中
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>MATCHING...</span>';
            btn.classList.add('opacity-80', 'cursor-not-allowed');
            radar.style.display = 'block'; // 显示雷达

            try {
                // 1. 启动任务
                const res = await fetch('/api/run/hybrid', { method: 'POST' });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Failed to start Phenology Matching');
                }

                // 2. 轮询状态
                const poll = setInterval(async () => {
                    try {
                        const statusRes = await fetch('/api/status');
                        const statusData = await statusRes.json();
                        const task = statusData.tasks.hybrid;

                        if (task.status === 'completed') {
                            clearInterval(poll);
                            finishPhenology();
                        } else if (task.status === 'failed') {
                            clearInterval(poll);
                            alert('物候匹配失败: ' + task.error);
                            resetBtn(btn, radar, '运行物候匹配', 'fa-play');
                        }
                    } catch (e) {
                        console.error("Polling error", e);
                    }
                }, 2000);

            } catch (e) {
                alert('启动失败: ' + e.message);
                resetBtn(btn, radar, '运行物候匹配', 'fa-play');
            }
        }

        async function finishPhenology() {
            const btn = document.getElementById('phenology-btn');
            const radar = document.getElementById('radar-layer');

            // UI 状态变更：分析完成
            btn.innerHTML = '<i class="fa-solid fa-check"></i> <span>匹配完成</span>';
            btn.classList.remove('bg-tech-green');
            btn.classList.add('bg-gray-600'); // 按钮变灰
            radar.style.display = 'none'; // 隐藏雷达

            try {
                // 3. 获取结果
                const res = await fetch('/api/output/phenology_results.json');
                const data = await res.json();

                // 更新结果数据
                document.getElementById('best-similarity').innerText = data.best_similarity + '%';
                
                // 更新图表
                updatePhenologyChart(data);
                
                addPhenologyMarkers();
                
                playCompletionSound();
            } catch (e) {
                console.error("Failed to load results", e);
                alert("匹配完成但无法加载结果文件。");
            }
        }
"""

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace runAHP block
run_ahp_start = "// --- 4. AHP 分析功能 ---"
run_ahp_end = "}" # This is risky. Let's find end of function.
# Or replace strictly the existing function text known from read_file

existing_ahp = """        // --- 4. AHP 分析功能 ---

        function runAHP() {

            const btn = document.getElementById('ahp-btn');

            const radar = document.getElementById('radar-layer');

            

            // 添加故障效果

            btn.classList.add('glitch-effect');

            

            // UI 状态变更：分析中

            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>ANALYZING...</span>';

            btn.classList.add('opacity-80', 'cursor-not-allowed');

            radar.style.display = 'block'; // 显示雷达



            // 模拟分析过程 (5秒后)

            setTimeout(() => {

                // UI 状态变更：分析完成

                btn.innerHTML = '<i class="fa-solid fa-check"></i> <span>分析完成</span>';

                btn.classList.remove('bg-tech-green');

                btn.classList.add('bg-gray-600'); // 按钮变灰

                radar.style.display = 'none'; // 隐藏雷达



                // 更新结果数据

                document.getElementById('avg-score').innerText = '78.5';

                document.getElementById('s-class-count').innerText = '12';

                

                // 更新图表

                updateSuitabilityChart();

                

                // 在地图上添加标记

                addAHPMarkers();

                

                // 添加分析完成的音效反馈（如果浏览器支持）

                playCompletionSound();

            }, 5000);

        }"""

existing_phenology = """        // --- 5. 物候期匹配功能 ---

        function runPhenology() {

            const btn = document.getElementById('phenology-btn');

            const radar = document.getElementById('radar-layer');

            

            // 添加故障效果

            btn.classList.add('glitch-effect');

            

            // UI 状态变更：分析中

            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>MATCHING...</span>';

            btn.classList.add('opacity-80', 'cursor-not-allowed');

            radar.style.display = 'block'; // 显示雷达



            // 模拟分析过程 (6秒后)

            setTimeout(() => {

                // UI 状态变更：分析完成

                btn.innerHTML = '<i class="fa-solid fa-check"></i> <span>匹配完成</span>';

                btn.classList.remove('bg-tech-green');

                btn.classList.add('bg-gray-600'); // 按钮变灰

                radar.style.display = 'none'; // 隐藏雷达



                // 更新结果数据

                document.getElementById('best-similarity').innerText = '92%';

                

                // 更新图表

                updatePhenologyChart();

                

                // 在地图上添加标记

                addPhenologyMarkers();

                

                // 添加分析完成的音效反馈（如果浏览器支持）

                playCompletionSound();

            }, 6000);

        }"""

# Normalize strings (remove excessive newlines/whitespace for matching?)
# Or try simple replace if python reads it exactly as is.
# The read_file output shows double newlines.
# I'll try to replace simply.

if existing_ahp in content:
    content = content.replace(existing_ahp, ahp_replacement)
    print("Replaced runAHP.")
else:
    # Try normalizing newlines to simple \n
    norm_content = content.replace('\r\n', '\n')
    norm_ahp = existing_ahp.replace('\r\n', '\n')
    
    # Remove all empty lines for robust matching? No that's risky for structure.
    # Let's try matching a unique substring if full match fails.
    if norm_ahp in norm_content:
        content = norm_content.replace(norm_ahp, ahp_replacement)
        print("Replaced runAHP (normalized).")
    else:
        print("Could not find runAHP function block.")
        # Debug: print snippet
        # print(content[content.find("runAHP"):content.find("runAHP")+200])

if existing_phenology in content:
    content = content.replace(existing_phenology, phenology_replacement)
    print("Replaced runPhenology.")
else:
     # Normalize check
    norm_content = content.replace('\r\n', '\n')
    norm_ph = existing_phenology.replace('\r\n', '\n')
    if norm_ph in norm_content:
        content = norm_content.replace(norm_ph, phenology_replacement)
        print("Replaced runPhenology (normalized).")
    else:
        print("Could not find runPhenology function block.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

