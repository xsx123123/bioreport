"""GWAS figure helpers for BioReport modules (GWASFlow upstream contract).

All figures follow the shared BioReport plotly style (``style_figure``);
the caller displays them through ``show_figure`` so HTML editions stay
interactive while PDF editions are exported as vector panels.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from bioreport.utils.plotly_style import GUIDE, INK, MUTED, style_figure

CHROM_COLORS = ("#477EB2", "#D89A5B")
SIG_COLOR = "#C0392B"


def load_gwas(path: str) -> pd.DataFrame:
    """Load a GWASFlow harmonized gwas.tsv (08.results/{trait}/gwas.tsv)."""
    df = pd.read_csv(path, sep="\t", dtype={"chrom": str})
    df["p_num"] = pd.to_numeric(df["p_value"], errors="coerce")
    df["neglog"] = -df["p_num"].apply(
        lambda value: math.log10(value) if value and value > 0 else float("nan"))
    return df


def load_chrom_lengths(path: str) -> tuple[list[str], dict[str, float]]:
    """Load a chromosome table (name, length_bp) keeping file order."""
    table = pd.read_csv(path, sep="\t")
    order = [str(value) for value in table.iloc[:, 0]]
    lengths = {str(row.iloc[0]): float(row.iloc[1]) for _, row in table.iterrows()}
    return order, lengths


def genome_offsets(chrom_order: list[str], lengths: dict[str, float]):
    offsets = [0.0]
    for chrom in chrom_order:
        offsets.append(offsets[-1] + lengths.get(chrom, 0.0))
    midpoints = [(offsets[i] + offsets[i + 1]) / 2 for i in range(len(chrom_order))]
    return offsets[:-1], midpoints


def plot_manhattan(
    df: pd.DataFrame,
    chrom_order: list[str],
    lengths: dict[str, float],
    *,
    threshold: float | None = None,
    threshold_label: str = "",
    title: str = "",
    point_budget: int = 200000,
    height: int = 460,
) -> go.Figure:
    """Interactive Manhattan plot with genome-offset x axis per chromosome."""
    starts, _ = genome_offsets(chrom_order, lengths)
    offset_by_chrom = dict(zip(chrom_order, starts))

    data = df[df["chrom"].isin(chrom_order)].copy()
    significant = data["significant"].astype(str).str.lower() == "true"
    if threshold:
        significant = significant | (
            (data["p_num"] > 0) & (data["p_num"] <= threshold))
    if len(data) > point_budget:
        keep_sig = data[significant]
        rest = data[~significant].sample(n=max(0, point_budget - len(keep_sig)),
                                         random_state=20261023)
        data = pd.concat([keep_sig, rest])

    fig = go.Figure()
    for index, chrom in enumerate(chrom_order):
        block = data[data["chrom"] == chrom]
        if block.empty:
            continue
        is_sig = significant.loc[block.index]
        for flag, color, name_suffix in (
            (False, CHROM_COLORS[index % 2], ""),
            (True, SIG_COLOR, " (significant)"),
        ):
            subset = block[is_sig == flag]
            if subset.empty:
                continue
            hover = ("<b>%{customdata[0]}</b><br>chr%{customdata[1]}:%{customdata[2]:,d}"
                     "<br>P = %{customdata[3]}<br>beta = %{customdata[4]}"
                     "<extra></extra>")
            fig.add_trace(go.Scattergl(
                x=(subset["pos"].astype(float) + offset_by_chrom[chrom]).tolist(),
                y=subset["neglog"].tolist(),
                customdata=list(zip(
                    subset["variant_id"], subset["chrom"],
                    subset["pos"].astype(int),
                    subset.get("p_value_text", subset["p_num"]),
                    subset["beta"].round(4) if "beta" in subset else "",
                )),
                mode="markers",
                marker=dict(size=4 if not flag else 5, color=color,
                            line=dict(width=0)),
                name=f"chr{chrom}{name_suffix}",
                hovertemplate=hover,
            ))

    _, midpoints = genome_offsets(chrom_order, lengths)
    fig.update_layout(
        title=title or "Manhattan plot",
        xaxis=dict(title="Chromosome", tickvals=midpoints,
                   ticktext=[f"chr{chrom}" for chrom in chrom_order],
                   showgrid=False),
        yaxis=dict(title="-log10(P)"),
        showlegend=False,
        dragmode="zoom",
        height=height,
        margin=dict(l=60, r=30, t=50, b=45),
    )
    if threshold and threshold > 0:
        fig.add_hline(y=-math.log10(threshold), line_dash="dash", line_color="#C0392B",
                      line_width=1,
                      annotation_text=threshold_label or f"Bonferroni {threshold:.3g}",
                      annotation_position="top left")
    return style_figure(fig)


def plot_qq(df: pd.DataFrame, *, title: str = "", max_points: int = 50000,
            height: int = 460) -> go.Figure:
    """QQ plot: expected -log10(rank/(n+1)) vs observed -log10(P)."""
    data = df[df["neglog"].notna()].sort_values("neglog")
    if len(data) > max_points:
        step = max(1, len(data) // max_points)
        data = pd.concat([
            data.iloc[::step],
            data.tail(1),
        ]).drop_duplicates()
    expected = [-math.log10((rank + 1) / (len(data) + 1))
                for rank in range(len(data))]
    observed = data["neglog"].tolist()
    significant = data["significant"].astype(str).str.lower() == "true"

    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=expected, y=observed, mode="markers",
        marker=dict(size=4, color=CHROM_COLORS[0], line=dict(width=0)),
        name="observed",
        hovertemplate=("-log10(P) expected %{x:.3f}<br>observed %{y:.3f}"
                       "<extra></extra>"),
        customdata=list(zip(data["variant_id"], data["p_value"])),
    ))
    sig_expected = [value for value, flag in zip(expected, significant) if flag]
    sig_observed = [value for value, flag in zip(observed, significant) if flag]
    if sig_expected:
        fig.add_trace(go.Scattergl(
            x=sig_expected, y=sig_observed, mode="markers",
            marker=dict(size=5, color=SIG_COLOR, line=dict(width=0)),
            name="significant",
        ))
    axis_max = 1.05 * max(observed + expected + [1.0])
    fig.add_shape(type="line", x0=0, y0=0, x1=axis_max, y1=axis_max,
                  line=dict(dash="dash", color=GUIDE, width=1.2))
    fig.update_layout(
        title=title or "QQ plot",
        xaxis=dict(title="Expected -log10(P)", range=[0, axis_max]),
        yaxis=dict(title="Observed -log10(P)", range=[0, axis_max]),
        showlegend=False,
        height=height,
        margin=dict(l=60, r=30, t=50, b=45),
    )
    return style_figure(fig)


def plot_pca(eigenvec_path: str, *, title: str = "", height: int = 460) -> go.Figure:
    """PC1 vs PC2 scatter from a plink2 pca.eigenvec file."""
    pca = pd.read_csv(eigenvec_path, sep=r"\s+", comment=None, dtype=str)
    pca.columns = [column.lstrip("#") for column in pca.columns]
    pc_cols = [column for column in pca.columns if column.startswith("PC")][:2]
    for column in pc_cols:
        pca[column] = pd.to_numeric(pca[column], errors="coerce")
    variance_note = ""
    eigenval_path = eigenvec_path.replace("eigenvec", "eigenval")
    try:
        eigenvalues = pd.read_csv(eigenval_path, sep=r"\s+", header=None)[0].tolist()
        total = sum(value for value in eigenvalues if value > 0) or 1.0
        variance_note = "".join(
            f" ({name}: {eigenvalues[i] / total:.1%})"
            for i, name in enumerate(pc_cols) if i < len(eigenvalues))
    except Exception:
        pass

    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=pca[pc_cols[0]], y=pca[pc_cols[1]], mode="markers",
        marker=dict(size=5, color=CHROM_COLORS[0], opacity=0.75, line=dict(width=0)),
        text=pca.get("IID", ""),
        hovertemplate="<b>%{text}</b><br>%{x:.4f}, %{y:.4f}<extra></extra>",
    ))
    fig.update_layout(
        title=(title or "PCA (LD-pruned marker set)") + variance_note,
        xaxis=dict(title=pc_cols[0]),
        yaxis=dict(title=pc_cols[1]),
        showlegend=False,
        height=height,
        margin=dict(l=60, r=30, t=50, b=45),
    )
    return style_figure(fig)


def plot_kinship_heatmap(matrix_path: str, *, max_samples: int = 194,
                         title: str = "", height: int = 520) -> go.Figure:
    """Kinship heatmap for the leading N samples of the centered K matrix."""
    matrix = pd.read_csv(matrix_path, sep=r"\s+", header=None, comment="#")
    n_show = min(len(matrix), max_samples)
    block = matrix.iloc[:n_show, :n_show]

    fig = go.Figure(go.Heatmap(
        z=block.values,
        # x/y labels are required by the PDF static export path (print_panels);
        # tick labels stay hidden in the layout.
        x=[str(i + 1) for i in range(n_show)],
        y=[str(i + 1) for i in range(n_show)],
        colorbar=dict(title=dict(text="K", font=dict(size=12, color=MUTED))),
        hovertemplate="row %{y}, col %{x}<br>K = %{z:.4f}<extra></extra>",
    ))
    fig.update_layout(
        title=f"{title or 'Kinship heatmap'} (first {n_show} samples)",
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(showticklabels=False, showgrid=False, autorange="reversed"),
        height=height,
        margin=dict(l=60, r=30, t=50, b=45),
    )
    return style_figure(fig)
