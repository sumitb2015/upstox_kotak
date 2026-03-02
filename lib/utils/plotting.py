import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json

def create_option_3d_surface(data_list, underlying_price, surface_type="both", metric="open_interest", use_log_scale=False, theme="dark"):
    """
    Generates a Plotly 3D surface figure for options chain data.
    """
    if not data_list:
        return None

    df = pd.DataFrame(data_list)
    
    # Grid Dimensions
    strikes = sorted(df['strike'].unique())
    dtes = sorted(df['dte'].unique())
    
    # Plotly's go.Surface requires at least a 2x2 grid to render a mesh.
    # If we only have one expiry (DTE), we duplicate the data with a tiny offset
    # to "trick" Plotly into rendering a very thin ribbon-like surface.
    if len(dtes) == 1:
        extra_row = df.copy()
        extra_row['dte'] = dtes[0] + 0.01
        df = pd.concat([df, extra_row])
        dtes = sorted(df['dte'].unique())

    if len(strikes) < 2:
        return None

    is_dark = theme == "dark"
    grid_color = 'rgba(255,255,255,0.05)' if is_dark else 'rgba(0,0,0,0.05)'
    text_color = '#c9d1d9' if is_dark else '#1e293b'
    template = 'plotly_dark' if is_dark else 'plotly_white'

    fig = go.Figure()

    def get_surface_trace(opt_type):
        subset = df[df['option_type'] == opt_type]
        if subset.empty:
            return None
            
        # Robust grid generation: fill gaps to ensure a smooth surface
        pivot_df = subset.pivot_table(index='dte', columns='strike', values=metric, aggfunc='sum')
        pivot_df = pivot_df.reindex(index=dtes, columns=strikes).fillna(0)
        
        z_values = pivot_df.values
        
        # Apply Log Scale if requested
        if use_log_scale and metric in ['open_interest', 'volume']:
            z_values = np.where(z_values > 0, np.log10(z_values), 0)

        # Pre-compute tooltip data grids
        iv_pivot = subset.pivot_table(index='dte', columns='strike', values='iv', aggfunc='mean').reindex(index=dtes, columns=strikes).fillna(0).values
        vol_pivot = subset.pivot_table(index='dte', columns='strike', values='volume', aggfunc='sum').reindex(index=dtes, columns=strikes).fillna(0).values
        oi_pivot = subset.pivot_table(index='dte', columns='strike', values='open_interest', aggfunc='sum').reindex(index=dtes, columns=strikes).fillna(0).values
        
        customdata = np.stack((iv_pivot, vol_pivot, oi_pivot), axis=-1)

        # High-contrast color scales for maximum visibility
        colorscale = [
            [0, '#1e40af'], [0.2, '#3b82f6'], [0.4, '#60a5fa'], [0.7, '#93c5fd'], [1, '#ffffff']
        ] if opt_type == 'call' else [
            [0, '#991b1b'], [0.2, '#ef4444'], [0.4, '#f87171'], [0.7, '#fca5a1'], [1, '#ffffff']
        ]

        return go.Surface(
            x=strikes,
            y=dtes,
            z=z_values,
            name=opt_type.capitalize(),
            colorscale=colorscale,
            showscale=True if surface_type != "both" or opt_type == "call" else False,
            opacity=0.9 if surface_type == "both" else 1.0,
            customdata=customdata,
            connectgaps=True,
            lighting=dict(ambient=0.6, diffuse=0.8, fresnel=0.2, specular=0.1, roughness=0.5),
            hovertemplate=(
                f"<b>Strike:</b> %{{x}}<br>" +
                f"<b>DTE:</b> %{{y:.0f}}<br>" +
                f"<b>{metric.upper()} {'(Log)' if use_log_scale and metric in ['open_interest', 'volume'] else ''}:</b> %{{z}}<br>" +
                f"<b>IV:</b> %{{customdata[0]:.2f}}%<br>" +
                f"<b>Vol:</b> %{{customdata[1]:,}}<br>" +
                f"<b>OI:</b> %{{customdata[2]:,}}<br>" +
                f"<extra>{opt_type.upper()}</extra>"
            )
        )

    if surface_type in ["both", "call"]:
        trace = get_surface_trace("call")
        if trace: fig.add_trace(trace)
        
    if surface_type in ["both", "put"]:
        trace = get_surface_trace("put")
        if trace: fig.add_trace(trace)

    # ATM Marker: A prominent vertical beam at the spot price
    if underlying_price > 0:
        max_z = df[metric].max()
        if use_log_scale and metric in ['open_interest', 'volume'] and max_z > 0:
            max_z = np.log10(max_z)
            
        fig.add_trace(go.Scatter3d(
            x=[underlying_price, underlying_price],
            y=[0, max(dtes) if dtes else 0],
            z=[0, max_z * 1.1 if max_z else 0.1], # Extend slightly above surface
            mode='lines',
            name=f'ATM (₹{underlying_price:,.0f})',
            line=dict(color='#fbbf24', width=12) # Enhanced width
        ))

    fig.update_layout(
        template=template,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        scene=dict(
            xaxis=dict(title='Strike Price', gridcolor=grid_color, showspikes=False),
            yaxis=dict(title='Days to Expiry', gridcolor=grid_color, showspikes=False),
            zaxis=dict(title=metric.replace('_', ' ').upper(), gridcolor=grid_color, showspikes=False),
            camera=dict(eye=dict(x=1.8, y=1.8, z=1.2)),
            aspectmode='manual',
            aspectratio=dict(x=1.2, y=1, z=0.7)
        ),
        margin=dict(l=0, r=0, b=0, t=0),
        legend=dict(orientation='h', y=0.05, x=0.5, xanchor='center'),
        font=dict(color=text_color, family='Inter')
    )

    return fig
