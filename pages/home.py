"""CellDecipher - Home Page"""

import streamlit as st
import streamlit.components.v1 as components

# Hero Section styles
st.markdown("""
<style>
.hero-section {
    background: linear-gradient(145deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 250, 252, 0.98) 100%);
    border: 1px solid rgba(8, 145, 178, 0.3);
    border-radius: 24px;
    padding: 3rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}

.hero-glow {
    position: absolute;
    pointer-events: none;
    border-radius: 50%;
}

.hero-glow-cyan {
    top: -100px;
    right: -100px;
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, #0891b2 0%, transparent 70%);
    opacity: 0.15;
}

.hero-glow-magenta {
    bottom: -150px;
    left: -100px;
    width: 350px;
    height: 350px;
    background: radial-gradient(circle, #db2777 0%, transparent 70%);
    opacity: 0.1;
}

.hero-content {
    position: relative;
    z-index: 1;
}

.hero-subtitle {
    color: #0891b2;
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-bottom: 0.5rem;
}

.hero-title {
    font-family: 'Outfit', sans-serif;
    font-size: 3.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, #0f172a 0%, #0891b2 50%, #db2777 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 1rem 0;
    line-height: 1.1;
}

.hero-description {
    color: #475569 !important;
    font-size: 1.4rem !important;
    max-width: 600px;
    line-height: 1.6;
    margin: 0;
}

.feature-card {
    background: linear-gradient(145deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 250, 252, 0.98) 100%);
    border: 1px solid rgba(15, 23, 42, 0.1);
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 0;
    transition: all 0.25s ease;
    min-height: 220px;
    text-decoration: none;
    display: flex;
    flex-direction: column;
    cursor: pointer;
    overflow: hidden;
    box-sizing: border-box;
}

.feature-card .feature-list {
    overflow-wrap: break-word;
    word-wrap: break-word;
}

.feature-card:hover {
    border-color: rgba(8, 145, 178, 0.3);
    box-shadow: 0 0 20px rgba(8, 145, 178, 0.15);
    transform: translateY(-2px);
}

/* Style page_link inside cards as a prominent clickable title */
[data-testid="stMainBlockContainer"] [data-testid*="PageLink"] a {
    font-size: 2.0rem !important;
    font-weight: 600 !important;
    color: #0f172a !important;
    text-decoration: none !important;
    transition: color 0.2s ease !important;
}
[data-testid="stMainBlockContainer"] [data-testid*="PageLink"] a:hover {
    color: #0891b2 !important;
}

.feature-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
}

.feature-icon {
    font-size: 1.75rem;
}

.feature-title {
    font-family: 'Outfit', sans-serif;
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0;
}

.feature-title.cyan { color: #0891b2; }
.feature-title.magenta { color: #db2777; }
.feature-title.amber { color: #d97706; }
.feature-title.green { color: #16a34a; }

.feature-list {
    color: #475569;
    margin: 0;
    padding-left: 1.25rem;
    line-height: 1.8;
}

.feature-list strong {
    color: #0f172a;
}

.quick-start-list {
    color: #475569;
    line-height: 2;
    padding-left: 1.25rem;
}

.quick-start-list a {
    font-weight: 600;
    text-decoration: none;
    transition: all 0.2s ease;
}

.quick-start-list a:hover {
    text-decoration: underline;
}

.quick-start-list a.cyan { color: #0891b2; }
.quick-start-list a.magenta { color: #db2777; }
.quick-start-list a.amber { color: #d97706; }
.quick-start-list a.green { color: #16a34a; }
.quick-start-list a.white { color: #0f172a; }

.footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 0;
}

.footer p {
    color: #94a3b8;
    font-size: 0.85rem;
    margin: 0;
}
</style>
""", unsafe_allow_html=True)

# Hero Section HTML (without animation)
st.markdown("""
<div class="hero-section">
    <div class="hero-glow hero-glow-cyan"></div>
    <div class="hero-glow hero-glow-magenta"></div>
    <div class="hero-content">
        <p class="hero-subtitle">Spatial Omics Analysis Platform</p>
        <h1 class="hero-title">CellDecipher</h1>
        <p class="hero-description">An all-in-one tool for EASI-FISH based spatial omics projects</p>
    </div>
</div>
""", unsafe_allow_html=True)

# Animation using components.html (allows JavaScript execution)
animation_html = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            background: transparent;
        }
        canvas {
            background: transparent;
        }
    </style>
</head>
<body>
    <canvas id="pixelUmapCanvas" width="900" height="320"></canvas>
    <script>
        const canvas = document.getElementById('pixelUmapCanvas');
        const ctx = canvas.getContext('2d');
        const width = 900;
        const height = 320;

        const numParticles = 500;
        const particles = [];

        const colors = [
            '#00d4ff', '#ff6b9d', '#4ade80',
            '#fbbf24', '#a78bfa', '#f472b6'
        ];

        // UMAP clusters (moved closer to center)
        const umapClusters = [
            { x: 620, y: 80 }, { x: 680, y: 180 }, { x: 580, y: 220 },
            { x: 720, y: 100 }, { x: 600, y: 150 }, { x: 660, y: 260 }
        ];

        // Grid on the left side (moved closer to center)
        const gridCols = 25, gridRows = 20;
        const gridStartX = 150, gridStartY = 30;
        const gridSpacingX = 10, gridSpacingY = 13;

        for (let i = 0; i < numParticles; i++) {
            const gridX = i % gridCols;
            const gridY = Math.floor(i / gridCols) % gridRows;
            const clusterIdx = Math.floor(Math.random() * umapClusters.length);
            const cluster = umapClusters[clusterIdx];

            particles.push({
                startX: gridStartX + gridX * gridSpacingX + Math.random() * 3,
                startY: gridStartY + gridY * gridSpacingY + Math.random() * 3,
                targetX: cluster.x + (Math.random() - 0.5) * 80,
                targetY: cluster.y + (Math.random() - 0.5) * 60,
                x: 0, y: 0,
                color: colors[clusterIdx],
                size: 3 + Math.random() * 2,
                delay: Math.random() * 0.3
            });
        }

        let animationProgress = 0;
        let direction = 1;
        const animationSpeed = 0.004;
        const pauseDuration = 100;
        let pauseCounter = 0;

        function easeInOutCubic(t) {
            return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        }

        function draw() {
            ctx.clearRect(0, 0, width, height);

            particles.forEach(p => {
                let prog = Math.max(0, Math.min(1, (animationProgress - p.delay) / (1 - p.delay)));
                prog = easeInOutCubic(prog);

                p.x = p.startX + (p.targetX - p.startX) * prog;
                p.y = p.startY + (p.targetY - p.startY) * prog;

                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                ctx.fillStyle = p.color;
                ctx.shadowColor = p.color;
                ctx.shadowBlur = 6;
                ctx.fill();
                ctx.shadowBlur = 0;
            });

            if (pauseCounter > 0) {
                pauseCounter--;
            } else {
                animationProgress += animationSpeed * direction;
                if (animationProgress >= 1) {
                    animationProgress = 1;
                    pauseCounter = pauseDuration;
                    direction = -1;
                } else if (animationProgress <= 0) {
                    animationProgress = 0;
                    pauseCounter = pauseDuration;
                    direction = 1;
                }
            }

            requestAnimationFrame(draw);
        }

        draw();
    </script>
</body>
</html>
"""

components.html(animation_html, height=340)

# Feature Cards
st.markdown("## Tools")

col1, col2 = st.columns(2, gap="large")

# Define card data: (page_path, icon, title, color, items)
cards_col1 = [
    ("pages/1_scrnaseq_search.py", "🔍", "scRNA-seq Search & Analysis", "cyan", [
        "Search public databases (CELLxGENE, GEO, HCA)",
        "Natural language query support",
        "Upload custom H5AD files",
        "Clustering and marker gene identification",
    ]),
    ("pages/3_pipeline_monitor.py", "⚙️", "Pipeline Assistant", "amber", [
        "AI assistant for pipeline parameters",
        "Troubleshoot errors",
        "Check your Seqera runs",
    ]),
]

cards_col2 = [
    ("pages/2_probe_design.py", "🧬", "Probe Design", "magenta", [
        "<strong>HCR3.0 Probes:</strong> Split-initiator design (B1-B5 hairpins)",
        "<strong>BarFISH Probes:</strong> Barcode multiplexed probes (10,000+ barcodes)",
        "IDT-compatible output for direct ordering",
    ]),
    ("pages/4_expression_analysis.py", "📊", "Expression Analysis", "green", [
        "Log transform, scale, PCA, and UMAP",
        "Interactive visualizations",
        "Quality control filtering",
        "Export results in multiple formats",
    ]),
]

def render_card(page_path, icon, title, color, items):
    """Render a feature card with the title as a clickable st.page_link."""
    items_html = "".join(f"<li>{item}</li>" for item in items)
    with st.container(border=True):
        st.page_link(page_path, label=f"{icon} **{title}**")
        st.markdown(f'<ul class="feature-list">{items_html}</ul>', unsafe_allow_html=True)

with col1:
    for card in cards_col1:
        render_card(*card)

with col2:
    for card in cards_col2:
        render_card(*card)

st.divider()

# Quick Start Guide
st.markdown("## Quick Start Guide")

tab1, tab2, tab3, tab4 = st.tabs([
    "scRNA-seq Search",
    "Probe Design",
    "Pipeline Assistant",
    "Expression Analysis"
])

with tab1:
    st.markdown("""
    <div style="padding: 1rem 0;">
        <ol class="quick-start-list">
            <li>Navigate to <a href="/scrnaseq-search" target="_self" class="cyan">scRNA-seq Search</a> in the sidebar</li>
            <li>Enter a natural language query (e.g., "T cells from lung cancer patients")</li>
            <li>Or upload your own H5AD file</li>
            <li>Run analysis and explore results</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)

with tab2:
    st.markdown("""
    <div style="padding: 1rem 0;">
        <ol class="quick-start-list">
            <li>Navigate to <a href="/probe-design" target="_self" class="magenta">Probe Design</a> in the sidebar</li>
            <li>Choose <a href="/probe-design" target="_self" class="white">HCR3.0</a> or <a href="/probe-design" target="_self" class="white">BarFISH</a> mode</li>
            <li>Enter gene names or RefSeq accessions</li>
            <li>Configure channel assignments</li>
            <li>Download IDT-compatible probe sequences</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)

with tab3:
    st.markdown("""
    <div style="padding: 1rem 0;">
        <ol class="quick-start-list">
            <li>Navigate to <a href="/pipeline-assistant" target="_self" class="amber">Pipeline Assistant</a> in the sidebar</li>
            <li>Ask the AI assistant about pipeline parameters</li>
            <li>Troubleshoot errors with context-aware help</li>
            <li>Connect to Seqera to check your runs</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)

with tab4:
    st.markdown("""
    <div style="padding: 1rem 0;">
        <ol class="quick-start-list">
            <li>Navigate to <a href="/expression-analysis" target="_self" class="green">Expression Analysis</a> in the sidebar</li>
            <li>Upload an Excel, CSV, or TXT file with gene expression data</li>
            <li>Configure QC and analysis parameters</li>
            <li>Generate visualizations and export results</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)

# Footer
st.divider()

st.markdown("""
<div class="footer">
    <p>CellDecipher v1.0</p>
    <p>Built for spatial omics research</p>
</div>
""", unsafe_allow_html=True)
