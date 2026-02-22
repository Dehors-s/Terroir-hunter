
import os

file_path = "d:/Work space/三创赛/frontend/index.html"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix the double replacement in Suitability Chart
bad_string = "window.suitChart = window.phenoChart = new Chart(ctx, {"
good_string = "window.suitChart = new Chart(ctx, {"
if bad_string in content:
    content = content.replace(bad_string, good_string)
    print("Fixed Suitability Chart double assignment.")
else:
    print("Warning: Double assignment not found. Check file state.")

# 2. Apply window.phenoChart to the Phenology Chart
# Strategy: Split content at 'function updatePhenologyChart'
split_marker = "function updatePhenologyChart(apiData) {"

if split_marker in content:
    parts = content.split(split_marker)
    if len(parts) == 2:
        part1 = parts[0]
        part2 = parts[1]
        
        # Replace 'new Chart' in part2
        # Note: part2 contains the Phenology chart instantiation
        # Search for pure "new Chart(ctx, {"
        target = "new Chart(ctx, {"
        replacement = "window.phenoChart = new Chart(ctx, {"
        
        if target in part2:
            part2 = part2.replace(target, replacement, 1) # Only first one in this part
            print("Updated Phenology Chart instantiation.")
        else:
            print("Warning: 'new Chart' not found in Phenology section.")
            
        content = part1 + split_marker + part2
    else:
        print("Error: Split marker not unique or not found.")
else:
    print("Error: Split marker 'function updatePhenologyChart(apiData) {' not found.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
