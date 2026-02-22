
import os

file_path = "d:/Work space/三创赛/frontend/index.html"

# Suitability Chart Replacement
# Target: Whole function body
suitability_func_old = """        function updateSuitabilityChart() {

            const ctx = document.getElementById('suitability-chart').getContext('2d');

            

            new Chart(ctx, {

                type: 'bar',

                data: {

                    labels: ['S级 (90-100)', 'A级 (80-90)', 'B级 (70-80)', 'C级 (60-70)', 'D级 (<60)'],

                    datasets: [{

                        label: '地块数量',

                        data: [12, 35, 48, 25, 8],"""

# Note: matching precisely is hard with variable whitespace.
# I'll use a regex-like approach: read file, find start and end of function, replace.
# But python's string replace is easiest if I can get the string right.
# Let's use the unique start and finding the distinct block.

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
in_suit = False
in_pheno = False

# New function definitions
new_suit_func = """        let suitChartInstance = null;
        function updateSuitabilityChart(distData) {
            const ctx = document.getElementById('suitability-chart').getContext('2d');
            const dataValues = distData || [0, 0, 0, 0, 0]; 

            if (suitChartInstance) suitChartInstance.destroy();

            suitChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['S级 (90-100)', 'A级 (80-90)', 'B级 (70-80)', 'C级 (60-70)', 'D级 (<60)'],
                    datasets: [{
                        label: '地块数量',
                        data: dataValues,
"""

new_pheno_func = """        let phenoChartInstance = null;
        function updatePhenologyChart(apiData) {
            const ctx = document.getElementById('phenology-chart').getContext('2d');
            
            let labels, refData, tgtData;
            if (apiData && apiData.ref_curve) {
                // API Data
                labels = Array.from({length: apiData.ref_curve.length}, (_, i) => i + 1);
                refData = apiData.ref_curve;
                tgtData = apiData.warped_curve || apiData.tgt_curve;
            } else {
                // Init Data
                const days = Array.from({length: 365}, (_, i) => i + 1);
                labels = days;
                refData = days.map(d => 0); 
                tgtData = days.map(d => 0);
            }

            if (phenoChartInstance) phenoChartInstance.destroy();
            
            // Downsample for chart clarity if needed, or use all points
            const filterStep = 10; 

            phenoChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels.filter((_, i) => i % filterStep === 0),
                    datasets: [{
                        label: '参考产区 (洛川)',
                        data: refData.filter((_, i) => i % filterStep === 0),
"""

# Logic: Iterate lines. Detect start of function. 
# Replace the preamble (setup variables, ctx, data gen).
# Stop replacing when we hit "backgroundColor:" (common chart config).
# This is tricky because I need to preserve the chart styling options below.

# Better: Replace the entire function. I have the chart options; I can just rewrite them in the new function string.
# The options are quite long though (font settings).
# Let's try to locate the specific data generation block.

content = "".join(lines)

# 1. Update Suitability Data
# Find: data: [12, 35, 48, 25, 8],
# Replace with: data: (typeof distData !== 'undefined') ? distData : [0,0,0,0,0],
# And add "let suitChartInstance..." at the top of script? Or just manage destroy() inside.
# If I don't destroy, old chart stays underneath.
# So I must add destroy logic.

# Simplest: Replace "new Chart(ctx, {" with 
# "if(window.suitChart) window.suitChart.destroy(); window.suitChart = new Chart(ctx, {"
repl_chart_init = """            if (window.suitChart) window.suitChart.destroy();
            window.suitChart = new Chart(ctx, {"""
old_chart_init = """            new Chart(ctx, {"""

if old_chart_init in content:
    # We need to be careful not to replace it everywhere (there are 2 charts).
    # But actually, doing it for both is fine if valid.
    # But better to target specific functions.
    pass

# Let's try the python replace of specific blocks again, but use normalize to avoid whitespace hell.
# Or just finding the data line.
# "data: [12, 35, 48, 25, 8]," is very specific.

if "data: [12, 35, 48, 25, 8]," in content:
    content = content.replace("data: [12, 35, 48, 25, 8],", "data: (typeof arguments[0] !== 'undefined') ? arguments[0] : [0,0,0,0,0],")
    # Also inject the destroy logic for suitability chart
    # It's inside updateSuitabilityChart
    content = content.replace(
        "const ctx = document.getElementById('suitability-chart').getContext('2d');",
        "const ctx = document.getElementById('suitability-chart').getContext('2d');\n            if(window.suitChart) window.suitChart.destroy();"
    )
    content = content.replace(
        "new Chart(ctx, {", 
        "window.suitChart = new Chart(ctx, {", 
        1 # Replace only the first occurrence (suitability chart matches first in file) 
    )
    print("Suitability chart updated.")

# 2. Update Phenology Data
# This is harder because of the data generation lines. 
# I'll just change the function signature and the data generation block.

start_marker = "function updatePhenologyChart() {"
end_marker = "new Chart(ctx, {"

if start_marker in content:
    # Inject argument
    content = content.replace(start_marker, "function updatePhenologyChart(apiData) {")
    
    # Inject data logic before new Chart
    # I'll inserting the parsing logic right after ctx definition.
    ctx_line = "const ctx = document.getElementById('phenology-chart').getContext('2d');"
    
    data_logic = """
            let labels, refData, tgtData;
            if (apiData && apiData.ref_curve) {
                labels = Array.from({length: apiData.ref_curve.length}, (_, i) => i + 1);
                refData = apiData.ref_curve;
                tgtData = apiData.warped_curve || apiData.tgt_curve;
            } else {
                const days = Array.from({length: 365}, (_, i) => i + 1);
                labels = days;
                refData = days.map(d=>0); tgtData = days.map(d=>0);
            }
            if(window.phenoChart) window.phenoChart.destroy();
    """
    
    content = content.replace(ctx_line, ctx_line + data_logic)
    
    # Now replace the 'new Chart' line for the second chart
    # Find the second occurrence of "new Chart"
    # Or just replace "new Chart(ctx, {" inside this function context if possible.
    # Since I'm editing the whole string, I need to find the location.
    
    # Also I need to remove the old const days = ... block? 
    # It might shadow or just be unused logic if I overwrite the data properties in Chart config.
    # The Chart config uses 'referenceData' and 'targetData'.
    # I should replace those variable names in the Chart config.
    
    content = content.replace("data: referenceData.filter", "data: refData.filter")
    content = content.replace("data: targetData.filter", "data: tgtData.filter")
    content = content.replace("labels: days.filter", "labels: labels.filter")

    # Capture the window global
    # This replace is risky if it hits the suitability chart.
    # I'll use a unique context string for phenology chart.
    
    pheno_new_chart = "window.phenoChart = new Chart(ctx, {"
    
    # Find the part around phenology chart
    # It comes after "const targetData = ..." usually.
    # But I haven't removed targetData definition.
    # So "const targetData" is uniquely in phenology function.
    
    content = content.replace("const targetData", "const targetData_unused") # rename to avoid confusion? 
    # Actually I just need to find the new chart call that follows it.
    
    # Instead of complex finding, lets just assume the order.
    # suitability is first, phenology is second.
    # I already replaced the first "new Chart" with "window.suitChart = ..."
    # So the next "new Chart" is the one.
    
    content = content.replace("new Chart(ctx, {", "window.phenoChart = new Chart(ctx, {", 1) 
    # Note: replace(..., 1) replaces the *first* match. 
    # Since I already replaced the first one in the previous block (suitability), 
    # the "new Chart" string remaining in `content` starts from Phenology (mostly).
    # Wait, `content` is a string. `replace` returns a new string.
    # So `content` currently has `window.suitChart = ...` for the first one.
    # So `new Chart` matches the phenology one now (as the first match of that string).
    
    print("Phenology chart updated.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

