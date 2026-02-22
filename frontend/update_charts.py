
import os

file_path = "d:/Work space/三创赛/frontend/index.html"

# 1. Update Suitability Chart
search_suit = """        function updateSuitabilityChart() {
            const ctx = document.getElementById('suitability-chart').getContext('2d');
            
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['S级 (90-100)', 'A级 (80-90)', 'B级 (70-80)', 'C级 (60-70)', 'D级 (<60)'],
                    datasets: [{
                        label: '地块数量',
                        data: [12, 35, 48, 25, 8],"""

replace_suit = """        let suitChartInstance = null;
        function updateSuitabilityChart(distData) {
            const ctx = document.getElementById('suitability-chart').getContext('2d');
            
            const dataValues = distData || [0, 0, 0, 0, 0]; // Default or API

            if (suitChartInstance) {
                suitChartInstance.destroy();
            }

            suitChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['S级 (90-100)', 'A级 (80-90)', 'B级 (70-80)', 'C级 (60-70)', 'D级 (<60)'],
                    datasets: [{
                        label: '地块数量',
                        data: dataValues,"""

# 2. Update Phenology Chart
search_pheno = """        function updatePhenologyChart() {
            const ctx = document.getElementById('phenology-chart').getContext('2d');
            
            // 生成模拟数据
            const days = Array.from({length: 365}, (_, i) => i + 1);
            const referenceData = days.map(day => {
                const t = (day - 180) / 180 * Math.PI;
                return 0.3 + 0.6 * Math.sin(t) * Math.exp(-0.005 * Math.abs(day - 180));
            });
            
            const targetData = days.map(day => {
                const t = (day - 190) / 180 * Math.PI;
                return 0.25 + 0.65 * Math.sin(t) * Math.exp(-0.004 * Math.abs(day - 190));
            });
            
            new Chart(ctx, {"""

replace_pheno = """        let phenoChartInstance = null;
        function updatePhenologyChart(apiData) {
            const ctx = document.getElementById('phenology-chart').getContext('2d');
            
            let labels, refData, tgtData;

            if (apiData && apiData.ref_curve) {
                // API 真实数据
                labels = Array.from({length: apiData.ref_curve.length}, (_, i) => i + 1);
                refData = apiData.ref_curve;
                tgtData = apiData.warped_curve || apiData.tgt_curve; // 用对齐后的曲线
            } else {
                // 模拟数据 (初始化时)
                const days = Array.from({length: 365}, (_, i) => i + 1);
                labels = days.filter((_, i) => i % 30 === 0); // 简化标签
                refData = days.map(day => 0); // Empty init
                tgtData = days.map(day => 0);
            }
            
            if (phenoChartInstance) {
                phenoChartInstance.destroy();
            }

            phenoChartInstance = new Chart(ctx, {"""

# Also need to fix labels in the chart options data property usage for mocked data vs real data
# In the search_pheno, mocked data logic was inside.
# I need to clean up the data assignment.

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

if search_suit in content:
    content = content.replace(search_suit, replace_suit)
    print("Updated Suitability Chart logic.")
else:
    print("Suitability Chart match failed.")

if search_pheno in content:
    content = content.replace(search_pheno, replace_pheno)
    
    # We also need to fix the data usage part down below in that function
    # Because I replaced the 'const referenceData = ...' block with 'let ...', 
    # but the chart config below uses 'data: referenceData.filter...'
    
    # Let's simple-replace the usage lines too if possible, or just be careful.
    # The new code defines refData, tgtData. The old code used referenceData, targetData.
    # And used .filter() on them.
    # I should check the Chart instantiation part.
    
    old_chart_data = """                    labels: days.filter((_, i) => i % 30 === 0),

                    datasets: [{

                        label: '参考产区 (洛川)',

                        data: referenceData.filter((_, i) => i % 30 === 0),"""
    
    new_chart_data = """                    labels: labels.filter((_, i) => i % 30 === 0), 

                    datasets: [{

                        label: '参考产区 (洛川)',

                        data: refData.filter((_, i) => i % 30 === 0),"""
    
    # And target
    old_tgt = """                        data: targetData.filter((_, i) => i % 30 === 0),"""
    new_tgt = """                        data: tgtData.filter((_, i) => i % 30 === 0),"""
    
    content = content.replace(old_chart_data, new_chart_data)
    content = content.replace(old_tgt, new_tgt)

    print("Updated Phenology Chart logic.")
else:
    print("Phenology Chart match failed.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
