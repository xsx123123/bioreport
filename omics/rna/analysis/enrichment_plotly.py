import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import textwrap
from pathlib import Path
import unicodedata
import numpy as np

from bioreport.utils.plotly_style import AXIS_LINE, GRID, export_config, style_figure


def parse_gene_ratios(values):
    def parse(value):
        if pd.isna(value): return np.nan
        try:
            text = str(value)
            if '/' in text:
                numerator, denominator = text.split('/')
                result = float(numerator)/float(denominator)
            else: result = float(text)
            return result if np.isfinite(result) else np.nan
        except (ValueError, ZeroDivisionError):
            return np.nan
    return values.map(parse)


def wrap_label(text, width=28):
    """Wrap English words and count wide CJK characters as two columns."""
    text = str(text)
    if not any(unicodedata.east_asian_width(c) in ['W','F'] for c in text):
        return '<br>'.join(textwrap.wrap(text, width=width, break_long_words=True))
    lines, current, length = [], '', 0
    for char in text:
        size = 2 if unicodedata.east_asian_width(char) in ['W','F'] else 1
        if current and length + size > width:
            lines.append(current); current, length = '', 0
        current += char; length += size
    if current: lines.append(current)
    return '<br>'.join(lines)

def draw_fancy_dotplot(enrich_file, 
                       top_n=20, 
                       p_cutoff=0.05, 
                       sort_by="p.adjust", 
                       ascending=True, 
                       x_col="GeneRatio", 
                       y_col="Description", 
                       size_col="Count", 
                       color_col="p.adjust",
                       height_num=800, 
                       width_num=900, 
                       scale_num=4,
                       wrap_width=30):
    """
    绘制科研级审美的富集分析气泡图 (支持长文本折行)
    """
    
    # --- 1. 数据读取与预处理 ---
    try:
        if isinstance(enrich_file, (str, Path)):
            df = pd.read_csv(enrich_file, sep=None, engine='python')
        elif isinstance(enrich_file, pd.DataFrame):
            df = enrich_file.copy()
        else:
            return None, None

        # 阈值过滤
        if p_cutoff is not None and color_col in df.columns:
            df = df[df[color_col] < p_cutoff]
            if len(df) == 0:
                print("⚠️ [WARN] 过滤后无剩余通路。")
                return None, None

        # GeneRatio 计算
        plot_x_col = x_col
        if df.empty: return None, None
        if x_col == 'GeneRatio' and x_col in df.columns:
            df['parsed_ratio'] = parse_gene_ratios(df[x_col])
            plot_x_col = 'parsed_ratio'
        elif x_col not in df.columns:
             candidates = ['FoldEnrichment', size_col]
             for c in candidates:
                 if c in df.columns:
                     plot_x_col = c
                     break

        # 排序
        if sort_by in df.columns:
            df = df.sort_values(sort_by, ascending=ascending)
        else:
            df = df.sort_values(color_col, ascending=True)
        
        # 截取 Top N 并反转
        if top_n and top_n < len(df):
            df = df.head(top_n)
        df = df.iloc[::-1]
        df[size_col] = pd.to_numeric(df[size_col],errors='coerce')
        df = df.dropna(subset=[plot_x_col,size_col,color_col])
        if df.empty: return None, None

    except Exception as e:
        print(f"❌ [ERROR] {e}")
        return None, None

    # --- 🛠️ 核心修改：文本折行处理 ---
    # 定义折行函数
    # 创建一个新的列用于绘图（带<br>的），保留原列 y_col 用于悬停显示
    df['wrapped_y'] = df[y_col].apply(lambda x: wrap_label(x, wrap_width))
    # 按每一行的实际折行数累计高度预算，避免单行条目被最高条目撑出大量空白
    row_budget = sum(t.count('<br>') + 1 for t in df['wrapped_y']) * 15 + len(df) * 10
    computed_height = 140 + row_budget

    # --- 2. 🎨 绘图 ---

    # Chart text stays English in both report languages.
    colorbar_title = 'Adjusted P value'
    color_scale = "RdYlBu"
    
    fig = px.scatter(
        df,
        x=plot_x_col,
        y='wrapped_y', # ✨ 这里使用折行后的列作为 Y 轴
        size=size_col,
        color=color_col,
        color_continuous_scale=color_scale, 
        size_max=25,
        title=f"<b>Top {len(df)} Enriched Pathways</b>",
        # hover_data 中显示原始的长名称 (y_col)
        hover_data={y_col:True, 'wrapped_y':False, size_col:True, color_col:":.2e", plot_x_col:":.3f"}
    )

    # --- 3. 精细化修饰 ---
    style_figure(
        fig,
        colorscale_menu='RdYlBu',
        height=max(height_num, computed_height),

        title=dict(text=f"<b>Top {len(df)} Enriched Pathways</b>", pad=dict(t=8)),

        xaxis=dict(
            title="<b>Gene ratio</b>" if plot_x_col in ["parsed_ratio", "GeneRatio"] else f"<b>{plot_x_col}</b>",
            gridcolor=GRID,
            griddash='dash',
        ),

        yaxis=dict(
            title="",
            gridcolor=GRID, griddash='dash',
            automargin=True, # 自动调整边距
            # ✨ 增加刻度文字间距，防止折行后太密
            tickfont=dict(size=12)
        ),

        # 边距：左边留白交给 automargin，右边留给 colorbar 与 Count 图例
        margin=dict(t=70, b=65, l=290, r=120),
        meta={"enrichment": True, "print_height": computed_height / 100},

        # colorbar 下移，给标题留出顶部空间
        coloraxis_colorbar=dict(
            title=f"<b>{colorbar_title}</b>",
            tickformat=".1e",
            len=0.45,
            thickness=15,
            yanchor="top", y=0.92,
            xanchor="left", x=1.02
        ),

        # Count 图例固定到 colorbar 下方，避免与标题重叠
        legend=dict(
            x=1.02, xanchor="left",
            y=0.38, yanchor="top",
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0
        )
    )
    
    fig.update_traces(
        marker=dict(
            line=dict(width=1.2, color='#4B5563'),
            opacity=0.9
        ),
        # 修改悬停显示的格式，把原本的 wrapped_y 替换为 Description
        hovertemplate = 
            f"<b>%{{customdata[0]}}</b><br>" + # 显示完整的 Description
            f"{plot_x_col}: %{{x:.3f}}<br>" +
            f"{size_col}: %{{marker.size}}<br>" +
            f"{color_col}: %{{marker.color:.2e}}<extra></extra>"
    )
    
    # 这一步是为了让 customdata 对齐 hovertemplate
    # 必须把原始 Description 放到 customdata 里
    fig.update_traces(customdata=df[[y_col]])

    # Explicit Count legend in both interactive and print output.
    for count in sorted(set(int(v) for v in df[size_col].quantile([0, .5, 1]))):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
            marker=dict(size=max(5, 25*(count/df[size_col].max())**.5), color='#8795a5'),
            name=f'Count: {count}', showlegend=True))
    # --- 4. 导出 ---
    config = export_config('Fancy_Enrichment', height=fig.layout.height,
                           width=width_num, scale=scale_num)

    return fig, config
