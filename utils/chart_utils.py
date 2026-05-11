"""
Grafik oluşturma yardımcıları.
Plotly ve matplotlib ile interaktif/statik grafikler.
"""
import plotly.graph_objects as go
import plotly.express as px
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

# Türkçe karakter desteği
matplotlib.rcParams['font.family'] = 'DejaVu Sans'


def create_student_trend_chart(student_name: str, exam_names: list, total_nets: list, lgs_scores: list) -> go.Figure:
    """
    Bir öğrencinin sınavlardaki net trendini gösteren çizgi grafiği.
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=exam_names,
        y=total_nets,
        mode='lines+markers+text',
        name='Toplam Net',
        text=[f"{n:.1f}" for n in total_nets],
        textposition='top center',
        line=dict(color='#1f77b4', width=3),
        marker=dict(size=10)
    ))

    if lgs_scores and any(s > 0 for s in lgs_scores):
        fig.add_trace(go.Scatter(
            x=exam_names,
            y=lgs_scores,
            mode='lines+markers+text',
            name='LGS Puan',
            text=[f"{s:.0f}" for s in lgs_scores],
            textposition='bottom center',
            line=dict(color='#ff7f0e', width=2, dash='dash'),
            marker=dict(size=8),
            yaxis='y2'
        ))

    fig.update_layout(
        title=f'{student_name} - Sinav Trendi',
        xaxis_title='Sinav',
        yaxis=dict(title='Toplam Net', side='left'),
        yaxis2=dict(title='LGS Puani', side='right', overlaying='y', showgrid=False),
        hovermode='x unified',
        height=500,
        template='plotly_white'
    )

    return fig


def create_student_subject_chart(student_name: str, exam_names: list, subject_scores: dict) -> go.Figure:
    """
    Bir öğrencinin ders bazlı net gelişimini gösteren grafik.
    
    subject_scores: {"turkce": [net1, net2, ...], "matematik": [net1, net2, ...], ...}
    """
    colors = {
        'turkce': '#1f77b4',
        'ink_tar': '#ff7f0e',
        'din_kul': '#2ca02c',
        'ingilizce': '#d62728',
        'matematik': '#9467bd',
        'fen_bil': '#8c564b'
    }

    labels = {
        'turkce': 'Turkce',
        'ink_tar': 'Ink.Tar./Sos',
        'din_kul': 'Din Kulturu',
        'ingilizce': 'Ingilizce',
        'matematik': 'Matematik',
        'fen_bil': 'Fen Bilimleri'
    }

    fig = go.Figure()

    for subject_key, scores in subject_scores.items():
        fig.add_trace(go.Bar(
            name=labels.get(subject_key, subject_key),
            x=exam_names,
            y=scores,
            marker_color=colors.get(subject_key, '#333333')
        ))

    fig.update_layout(
        title=f'{student_name} - Ders Bazli Net Gelisimi',
        barmode='group',
        xaxis_title='Sinav',
        yaxis_title='Net',
        height=500,
        template='plotly_white'
    )

    return fig


def create_class_comparison_chart(class_names: list, averages: dict) -> go.Figure:
    """
    Sınıflar arası karşılaştırma çubuk grafiği.
    
    averages: {"8A": {"turkce": 12.5, "matematik": 8.3, ...}, "8B": {...}, ...}
    """
    if not averages:
        fig = go.Figure()
        fig.update_layout(title="Veri bulunamadi")
        return fig

    subjects = list(next(iter(averages.values())).keys())
    labels = {
        'turkce': 'Turkce',
        'ink_tar': 'Ink.Tar./Sos',
        'din_kul': 'Din Kulturu',
        'ingilizce': 'Ingilizce',
        'matematik': 'Matematik',
        'fen_bil': 'Fen Bilimleri',
        'toplam_net': 'Toplam Net'
    }

    fig = go.Figure()

    for cls in class_names:
        if cls in averages:
            values = [averages[cls].get(s, 0) for s in subjects]
            fig.add_trace(go.Bar(
                name=cls,
                x=[labels.get(s, s) for s in subjects],
                y=values
            ))

    fig.update_layout(
        title='Sinif Karsilastirmasi - Ders Bazli Ortalamalar',
        barmode='group',
        xaxis_title='Ders',
        yaxis_title='Ortalama Net',
        height=500,
        template='plotly_white'
    )

    return fig


def create_exam_distribution_chart(exam_name: str, net_scores: list) -> go.Figure:
    """
    Bir sınavın net dağılım histogramı.
    """
    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=net_scores,
        nbinsx=20,
        name='Net Dagilimi',
        marker_color='#1f77b4',
        opacity=0.75
    ))

    avg = np.mean(net_scores) if net_scores else 0
    fig.add_vline(x=avg, line_dash="dash", line_color="red",
                  annotation_text=f"Ortalama: {avg:.1f}")

    fig.update_layout(
        title=f'{exam_name} - Net Dagilimi',
        xaxis_title='Toplam Net',
        yaxis_title='Ogrenci Sayisi',
        height=400,
        template='plotly_white'
    )

    return fig


def create_rank_progress_chart(student_name: str, exam_names: list, ranks: list) -> go.Figure:
    """
    Öğrencinin sıralama değişim grafiği (düşük = iyi).
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=exam_names,
        y=ranks,
        mode='lines+markers+text',
        name='Genel Sira',
        text=[str(int(r)) for r in ranks],
        textposition='top center',
        line=dict(color='#2ca02c', width=3),
        marker=dict(size=10)
    ))

    fig.update_layout(
        title=f'{student_name} - Siralama Degisimi',
        xaxis_title='Sinav',
        yaxis_title='Siralama',
        yaxis_autorange='reversed',  # Düşük sıra üstte göster
        height=400,
        template='plotly_white'
    )

    return fig
