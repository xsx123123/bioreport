import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from bioreport.utils.print_theme import group_palette
from bioreport.utils.plotly_style import INK, export_config, style_figure
from sklearn.decomposition import PCA
import plotly.colors as pc


def _pca_label_positions(count, phase=0):
    """轮换标签锚点，降低重复样本坐标附近的文字重叠。"""
    slots = ['top center', 'bottom center', 'middle right', 'middle left']
    return [slots[(phase + i) % len(slots)] for i in range(count)]

def draw_pca_plotly(tpm_file, meta_file, height_num=600, width_num=900, scale_num=4,
                    top_n=None, group_col=None, color_map=None):
    """
    读取 TPM 和 Metadata，绘制交互式 PCA 双图 (PC1 vs PC2, PC2 vs PC3)。
    
    Args:
        tpm_file (str): TPM 文件路径
        meta_file (str): Metadata 文件路径
        top_n (int, optional): 仅使用变异最大的前 N 个基因进行 PCA (默认使用全部)
        group_col (str, optional): 指定 Metadata 中用于分组的列名 (默认自动查找)
        color_map (dict, optional): 分组颜色映射字典 {Group: ColorHex}
    
    Returns:
        fig, config: Plotly Figure 对象和下载配置
    """
    
    # --- 1. 数据读取与对齐 (鲁棒模式) ---
    try:
        # 读取数据
        df = pd.read_csv(tpm_file, sep=None, engine='python', index_col=0)
        meta_raw = pd.read_csv(meta_file, sep=None, engine='python')
        
        # 智能匹配 Metadata 的样本 ID 列
        matrix_samples = set(df.columns.astype(str))
        best_id_col, max_overlap = None, 0
        for col in meta_raw.columns:
            overlap = len(set(meta_raw[col].astype(str)) & matrix_samples)
            if overlap > max_overlap: max_overlap, best_id_col = overlap, col
        
        if not best_id_col or max_overlap == 0:
            raise ValueError("无法在 Metadata 中找到与矩阵匹配的样本 ID 列！")
            
        meta = meta_raw.set_index(best_id_col)
        
        # 对齐样本
        df.columns = df.columns.astype(str)
        meta.index = meta.index.astype(str)
        display_order = list(meta.index)
        common_samples = [s for s in df.columns if s in meta.index]
        
        if not common_samples:
            raise ValueError("没有找到公共样本！")
            
        df = df[common_samples]
        meta = meta.loc[common_samples]
        
        # 确定分组列
        if group_col is None:
            # 尝试寻找包含 "group" 的列，否则用第一列
            cols_lower = [c.lower() for c in meta.columns]
            if "group" in cols_lower:
                group_col = meta.columns[cols_lower.index("group")]
            else:
                group_col = meta.columns[0]
        
        # print(f"[INFO] 使用分组列: {group_col}")
        
    except Exception as e:
        print(f"[ERROR] 数据读取失败: {e}")
        return None, None

    # --- 2. 数据预处理 ---
    # 过滤低表达 (行均值 > 1)
    df = df[df.mean(axis=1) > 1]
    
    # Log2 转换
    log_df = np.log2(df + 1)
    
    # (可选) 筛选高变基因
    if top_n and top_n < len(log_df):
        vars = log_df.var(axis=1)
        top_genes = vars.sort_values(ascending=False).head(top_n).index
        log_df = log_df.loc[top_genes]
    
    # 转置矩阵 (PCA 需要行是样本，列是特征/基因)
    X = log_df.T 

    # --- 3. PCA 计算 ---
    pca = PCA(n_components=3)
    pca_result = pca.fit_transform(X)
    
    # 获取解释方差比例 (%)
    var_exp = pca.explained_variance_ratio_ * 100
    
    # 构建绘图数据
    plot_df = pd.DataFrame(pca_result, columns=['PC1', 'PC2', 'PC3'], index=X.index)
    plot_df['Group'] = meta[group_col]
    plot_df['Sample'] = plot_df.index
    # Display points in metadata order; do not reorder the PCA input or refit it.
    plot_df = plot_df.loc[[s for s in display_order if s in plot_df.index]]

    # --- 4. 绘图 (Plotly Graph Objects) ---
    # 创建 1行2列 的子图
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=(f"PCA Plot (PC1 vs PC2)", f"PCA Plot (PC2 vs PC3)"),
        horizontal_spacing=0.15
    )

    # 获取所有分组并分配颜色
    unique_groups = sorted(plot_df['Group'].unique(),key=str)
    
    # --- 颜色分配逻辑 ---
    if color_map:
        # 如果传入了 color_map，直接使用
        group_color_map = {g: color_map.get(g, '#333333') for g in unique_groups} # 找不到默认黑色
    else:
        # 使用 Plotly 默认色板
        group_color_map = group_palette(meta_raw[group_col])
        group_color_map = {g: group_color_map[str(g)] for g in unique_groups}

    # 循环添加每个分组的 Trace
    for group in unique_groups:
        subset = plot_df[plot_df['Group'] == group]
        color = group_color_map[group]
        
        # --- 左图: PC1 vs PC2 ---
        fig.add_trace(
            go.Scatter(
                x=subset['PC1'], y=subset['PC2'],
                mode='markers+text',
                textposition=_pca_label_positions(len(subset), unique_groups.index(group)),
                marker=dict(size=12, color=color, line=dict(width=1, color=INK)),
                name=str(group),
                hovertemplate=f"%{{text}} ({group})<br>X: %{{x:.3f}}<br>Y: %{{y:.3f}}<extra></extra>",
                text=subset['Sample'], # 鼠标悬停显示样本名
                legendgroup=str(group),     # 关键：让两张图的图例联动
                showlegend=True        # 左图显示图例
            ),
            row=1, col=1
        )
        
        # --- 右图: PC2 vs PC3 ---
        fig.add_trace(
            go.Scatter(
                x=subset['PC2'], y=subset['PC3'],
                mode='markers+text',
                textposition=_pca_label_positions(len(subset), unique_groups.index(group) + 1),
                marker=dict(size=12, color=color, line=dict(width=1, color=INK)),
                name=str(group),
                hovertemplate=f"%{{text}} ({group})<br>X: %{{x:.3f}}<br>Y: %{{y:.3f}}<extra></extra>",
                text=subset['Sample'],
                legendgroup=str(group),     # 联动
                showlegend=False       # 右图不重复显示图例
            ),
            row=1, col=2
        )

    # --- 5. 样式美化 ---
    style_figure(
        fig,
        meta={"bioreport_responsive_pca": True},
        height=height_num,
        # 图例提取为左右两子图的顶部公共图例，避免压在左图点位上。
        legend=dict(title_text="Group", orientation="h",
                    yanchor="bottom", y=1.16, xanchor="right", x=1),
        margin=dict(t=100, b=50, l=50, r=50)
    )

    # 更新坐标轴标签 (带方差百分比)
    fig.update_xaxes(title_text=f"PC1: {var_exp[0]:.1f}% variance", row=1, col=1)
    fig.update_yaxes(title_text=f"PC2: {var_exp[1]:.1f}% variance", row=1, col=1)
    
    fig.update_xaxes(title_text=f"PC2: {var_exp[1]:.1f}% variance", row=1, col=2)
    fig.update_yaxes(title_text=f"PC3: {var_exp[2]:.1f}% variance", row=1, col=2)

    # --- 6. 高清下载配置 ---
    my_config = export_config('PCA_Global_Analysis', height=height_num,
                              width=width_num, scale=scale_num)

    return fig, my_config
